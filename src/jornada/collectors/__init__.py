"""Leitura dos sinais de atividade; cada coletor é `poll(con, now)` e nunca derruba o loop."""

import logging
import sqlite3
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from jornada import db, metrics, spans

log = logging.getLogger("jornada.collectors")

TICK_SECONDS = 5.0
MIC_SECONDS = 15.0

Poll = Callable[[sqlite3.Connection, float], None]


def gdbus_call(dest: str, path: str, method: str) -> str:
    """Chama um método no barramento de sessão pelo `gdbus`; OSError em qualquer falha."""
    try:
        r = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                dest,
                "--object-path",
                path,
                "--method",
                method,
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise OSError(f"gdbus expirou: {method}") from e
    if r.returncode != 0:
        raise OSError(r.stderr.strip() or f"gdbus saiu com {r.returncode}")
    return r.stdout


def safe_poll(nome: str, poll: Poll, con: sqlite3.Connection, now: float) -> None:
    """Executa o coletor capturando a falha; tenta de novo no próximo tick."""
    try:
        poll(con, now)
    except Exception:
        log.exception("coletor %s falhou", nome)


TODAY_SECONDS = 30.0
PAUSE_SOURCE = "pause"


class Collector:
    """Componente de coleta: um tick de 5 s roda os coletores e grava a pausa; a cada 30 s
    atualiza a bandeja com o total de hoje. `gi` só entra em `start()`."""

    def __init__(self, db_path: Path, tray, call: Callable[..., str] = gdbus_call) -> None:
        self._db_path = db_path
        self._tray = tray
        self._con: sqlite3.Connection | None = None
        self._source_id: int | None = None
        self._polls: list[tuple[str, Poll, float]] = [
            ("input", idle.make(call), TICK_SECONDS),
            ("lock", lock.make(call), TICK_SECONDS),
            ("window", window.make(call), TICK_SECONDS),
            ("mic", mic.make(), MIC_SECONDS),
        ]
        self._last: dict[str, float] = {}
        self._last_today = float("-inf")

    def start(self) -> None:
        from gi.repository import GLib

        self._con = db.connect(self._db_path)
        self.tick(time.time())
        self._source_id = GLib.timeout_add_seconds(int(TICK_SECONDS), self._on_timer)

    def stop(self) -> None:
        if self._source_id is not None:
            from gi.repository import GLib

            GLib.source_remove(self._source_id)
            self._source_id = None
        if self._con is not None:
            self._con.close()
            self._con = None

    def _on_timer(self) -> bool:
        self.tick(time.time())
        return True

    def tick(self, now: float) -> None:
        con = self._con
        if con is None:
            return
        for nome, poll, intervalo in self._polls:
            if now - self._last.get(nome, float("-inf")) >= intervalo:
                self._last[nome] = now
                safe_poll(nome, poll, con, now)
        if self._tray.paused:
            safe_poll(PAUSE_SOURCE, record_pause, con, now)
        if now - self._last_today >= TODAY_SECONDS:
            self._last_today = now
            self.refresh_tray(now)
        ultimo = spans.last(con, "input")
        self._tray.active = ultimo is not None and ultimo[1] == "active" and now - ultimo[4] <= 15

    def refresh_tray(self, now: float) -> None:
        if self._con is None:
            return
        try:
            segundos, desde = metrics.today(self._con, now)
        except Exception:
            log.exception("total de hoje falhou")
            return
        self._tray.set_today(
            metrics.format_hm(segundos), desde.strftime("%H:%M") if desde else None
        )


def record_pause(con: sqlite3.Connection, now: float) -> None:
    spans.record(con, PAUSE_SOURCE, "paused", now)


from jornada.collectors import idle, lock, mic, window  # noqa: E402
