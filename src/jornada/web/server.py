"""Servidor HTTP local do banco de horas: API JSON + página estática, só em 127.0.0.1.

Escritas exigem o cabeçalho `X-Jornada-Token`; o token chega à página por cookie quando a
bandeja abre `/?t=<token>`.
"""

import json
import logging
import re
import secrets
import tempfile
import threading
from collections import defaultdict
from datetime import date, timedelta
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jornada import db, ledger, metrics, paths, sheet
from jornada.capture import store as capture_store

STATIC = Path(__file__).parent / "static"
TIPOS = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".webp": "image/webp",
}
KINDS = {None, "feriado", "dayoff", "ausencia", "ajuste"}
COOKIE = "jornada_token"
log = logging.getLogger("jornada.web")


class BadRequest(Exception):
    pass


def day_json(d: ledger.Day) -> dict:
    return {
        "date": d.date.isoformat(),
        "weekday": d.date.weekday(),
        "measured": d.measured,
        "worked": d.worked,
        "expected": d.expected,
        "delta": d.delta,
        "balance": d.balance,
        "balance_days": round(d.balance_days, 2),
        "worked_override": d.override.worked,
        "expected_override": d.override.expected,
        "kind": d.override.kind,
        "note": d.override.note,
    }


def parse_date(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError as e:
        raise BadRequest(f"data inválida: {texto!r}") from e


def minutes_or_none(valor: object) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise BadRequest("minutos devem ser inteiros não negativos")
    return valor


def summary(con, hoje: date) -> dict:
    dias = ledger.compute(con, hoje, hoje)
    saldo = dias[-1].balance if dias else 0
    segunda = hoje - timedelta(days=hoje.weekday())
    hoje_dia = next((d for d in dias if d.date == hoje), None)
    semana = [d for d in dias if d.date >= segunda]
    return {
        "balance": saldo,
        "balance_days": round(saldo / ledger.DIA_MINUTOS, 2),
        "balance_text": ledger.balance_line(saldo),
        "today": {"worked": hoje_dia.worked, "expected": hoje_dia.expected} if hoje_dia else None,
        "week": {
            "worked": sum(d.worked for d in semana),
            "expected": sum(d.expected for d in semana),
        },
    }


def day_detail(con, dia: date) -> dict:
    spans = metrics.load_spans(con, dia)
    ini, fim = metrics.day_bounds(dia)
    ativos = metrics.active_intervals(spans, dia)
    tempos: dict[tuple[str, str], float] = defaultdict(float)
    linhas = con.execute(
        "SELECT data, start, end FROM span WHERE source = 'window' AND end > ? AND start < ?",
        (ini, fim),
    )
    for dados, a, b in linhas:
        info = json.loads(dados) if dados else {}
        chave = (info.get("app") or "desconhecida", info.get("title") or "")
        tempos[chave] += min(b, fim) - max(a, ini)
    top = sorted(tempos.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "date": dia.isoformat(),
        "spans": [{"start": a, "end": b} for a, b in ativos],
        "windows": [{"app": k[0], "title": k[1], "minutes": round(v / 60, 1)} for k, v in top],
    }


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, db_path: Path, token: str, captures_dir: Path, **kwargs):
        self.db_path = db_path
        self.captures_dir = captures_dir
        self.token = token
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        log.debug(format, *args)

    def _send(self, status: int, corpo: bytes, tipo: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dados, status: int = 200) -> None:
        self._send(status, json.dumps(dados).encode(), "application/json")

    def _body(self):
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(tamanho) or b"null")
        except (ValueError, json.JSONDecodeError) as e:
            raise BadRequest("corpo JSON inválido") from e

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def _dispatch(self, metodo: str) -> None:
        if not self._host_ok():
            return self._json({"error": "host"}, HTTPStatus.FORBIDDEN)
        url = urlparse(self.path)
        if metodo == "PUT" and self.headers.get("X-Jornada-Token") != self.token:
            return self._json({"error": "token"}, HTTPStatus.FORBIDDEN)
        con = db.connect(self.db_path)
        try:
            self._route(metodo, url.path, parse_qs(url.query), con, url)
        except BadRequest as e:
            self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        finally:
            con.close()

    def _read_token_ok(self) -> bool:
        """As capturas só saem com o token, pelo cookie da página ou pelo cabeçalho."""
        cookies = {
            k: v
            for k, _, v in (
                c.strip().partition("=") for c in self.headers.get("Cookie", "").split(";")
            )
        }
        enviado = cookies.get(COOKIE) or self.headers.get("X-Jornada-Token") or ""
        return secrets.compare_digest(enviado, self.token)

    def _captures(self, dia: str) -> None:
        self._json(
            [
                {"time": f"{n[0:2]}:{n[2:4]}:{n[4:6]}", "file": n}
                for n in capture_store.list_day(self.captures_dir, dia)
            ]
        )

    def _capture_file(self, dia: str, nome: str) -> None:
        if not (capture_store.valid_day(dia) and capture_store.valid_file(nome)):
            return self._json({"error": "não encontrado"}, HTTPStatus.NOT_FOUND)
        arquivo = self.captures_dir / dia / nome
        try:
            corpo = arquivo.read_bytes()
        except OSError:
            return self._json({"error": "não encontrado"}, HTTPStatus.NOT_FOUND)
        self._send(200, corpo, "image/webp", {"Cache-Control": "private, max-age=3600"})

    def _route(self, metodo, caminho, query, con, url) -> None:
        hoje = date.today()  # noqa: DTZ011 - dia local
        capturas = caminho == "/api/captures" or caminho.startswith("/captures/")
        if capturas and metodo == "GET" and not self._read_token_ok():
            return self._json({"error": "token"}, HTTPStatus.FORBIDDEN)
        if metodo == "GET" and caminho == "/api/captures":
            return self._captures(query.get("date", [""])[0])
        if metodo == "GET" and (m := re.fullmatch(r"/captures/([^/]+)/([^/]+)", caminho)):
            return self._capture_file(m[1], m[2])
        if metodo == "GET" and not caminho.startswith("/api/"):
            return self._static(caminho, query)
        if metodo == "GET" and caminho == "/api/days":
            de = parse_date(query["from"][0]) if "from" in query else hoje.replace(day=1)
            ate = parse_date(query["to"][0]) if "to" in query else hoje
            dias = [day_json(d) for d in ledger.compute(con, ate, hoje) if d.date >= de]
            return self._json(dias)
        if m := re.fullmatch(r"/api/days/(\d{4}-\d{2}-\d{2})/detail", caminho):
            return self._json(day_detail(con, parse_date(m[1])))
        m = re.fullmatch(r"/api/days/(\d{4}-\d{2}-\d{2})", caminho)
        if m and metodo == "PUT":
            return self._put_day(con, parse_date(m[1]))
        if caminho == "/api/schedule":
            if metodo == "GET":
                return self._json(
                    [{"start": d.isoformat(), "minutes": m} for d, m in ledger.load_schedule(con)]
                )
            return self._put_schedule(con)
        if metodo == "GET" and caminho == "/api/summary":
            return self._json(summary(con, hoje))
        if metodo == "GET" and caminho == "/api/export.xlsx":
            return self._export(con)
        self._json({"error": "não encontrado"}, HTTPStatus.NOT_FOUND)

    def _put_day(self, con, dia: date) -> None:
        corpo = self._body()
        if not isinstance(corpo, dict):
            raise BadRequest("esperado um objeto")
        worked = minutes_or_none(corpo.get("worked"))
        expected = minutes_or_none(corpo.get("expected"))
        kind = corpo.get("kind") or None
        note = corpo.get("note") or None
        if kind not in KINDS:
            raise BadRequest(f"kind inválido: {kind!r}")
        with con:
            if worked is None and expected is None and kind is None and note is None:
                con.execute("DELETE FROM day WHERE date = ?", (dia.isoformat(),))
            else:
                con.execute(
                    "INSERT OR REPLACE INTO day VALUES (?, ?, ?, ?, ?)",
                    (dia.isoformat(), worked, expected, kind, note),
                )
        achado = [d for d in ledger.compute(con, dia, date.today()) if d.date == dia]  # noqa: DTZ011
        self._json(day_json(achado[0]) if achado else {"date": dia.isoformat()})

    def _put_schedule(self, con) -> None:
        corpo = self._body()
        if not isinstance(corpo, list) or not corpo:
            raise BadRequest("esperada uma lista de períodos")
        linhas = []
        for item in corpo:
            minutos = item.get("minutes") if isinstance(item, dict) else None
            if (
                not isinstance(minutos, list)
                or len(minutos) != 7
                or any(minutes_or_none(x) is None for x in minutos)
            ):
                raise BadRequest("cada período precisa de 7 valores em minutos")
            linhas.append((parse_date(str(item.get("start"))).isoformat(), json.dumps(minutos)))
        with con:
            con.execute("DELETE FROM schedule")
            con.executemany("INSERT OR REPLACE INTO schedule VALUES (?, ?)", linhas)
        self._json([{"start": s, "minutes": json.loads(m)} for s, m in sorted(linhas)])

    def _export(self, con) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "banco-de-horas.xlsx"
            sheet.export_sheet(con, arquivo)
            corpo = arquivo.read_bytes()
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        self._send(
            200,
            corpo,
            tipo,
            {"Content-Disposition": 'attachment; filename="banco-de-horas.xlsx"'},
        )

    def _static(self, caminho: str, query) -> None:
        nome = "index.html" if caminho == "/" else caminho.lstrip("/")
        arquivo = (STATIC / nome).resolve()
        if STATIC.resolve() not in arquivo.parents or not arquivo.is_file():
            return self._json({"error": "não encontrado"}, HTTPStatus.NOT_FOUND)
        extra = {}
        if caminho == "/" and query.get("t", [None])[0] == self.token:
            extra["Set-Cookie"] = f"{COOKIE}={self.token}; Path=/; SameSite=Strict"
        tipo = TIPOS.get(arquivo.suffix, "application/octet-stream")
        self._send(200, arquivo.read_bytes(), f"{tipo}; charset=utf-8", extra)


def make_server(
    db_path: Path, port: int, token: str, captures_dir: Path | None = None
) -> ThreadingHTTPServer:
    handler = partial(
        Handler,
        db_path=db_path,
        token=token,
        captures_dir=captures_dir or paths.captures_dir(),
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


class WebServer:
    """Componente do app: o servidor numa thread do processo."""

    def __init__(self, db_path: Path, port: int, captures_dir: Path | None = None) -> None:
        self._captures_dir = captures_dir
        self.token = secrets.token_urlsafe(24)
        self._db_path = db_path
        self._port = port
        self._server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        porta = self._server.server_address[1] if self._server else self._port
        return f"http://127.0.0.1:{porta}/?t={self.token}"

    def start(self) -> None:
        try:
            self._server = make_server(self._db_path, self._port, self.token, self._captures_dir)
        except OSError:
            log.exception(
                "porta %s indisponível; a tela do banco de horas fica desligada", self._port
            )
            return
        threading.Thread(target=self._server.serve_forever, daemon=True, name="jornada-web").start()
        log.info("banco de horas em http://127.0.0.1:%s/", self._server.server_address[1])

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
