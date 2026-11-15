"""Leitura dos sinais de atividade; cada leitura roda isolada e nunca derruba o loop.

As regras de detecção (`jornada.settings`) são relidas do banco a cada tick, e cada decisão dos
detectores vira um evento (`jornada.events`) para depuração. O estado ao vivo fica em
`Collector.live`, um dicionário trocado inteiro a cada tick, que o servidor web lê de outra thread.
"""

import logging
import sqlite3
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from jornada import __version__, db, events, metrics, settings, spans
from jornada.collectors import camera, idle, lock, mic, window
from jornada.detect import InputDetector, Sustained
from jornada.settings import Settings

log = logging.getLogger("jornada.collectors")

TICK_SECONDS = 5.0
MIC_SECONDS = 15.0
TODAY_SECONDS = 30.0
PURGE_SECONDS = 3600.0
ERROR_REPEAT_SECONDS = 300.0
PAUSE_SOURCE = "pause"

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


def safe_poll(nome: str, poll: Poll, con: sqlite3.Connection, now: float) -> Exception | None:
    """Executa o coletor capturando a falha (tenta de novo no próximo tick); devolve o erro."""
    try:
        poll(con, now)
    except Exception as e:
        log.exception("coletor %s falhou", nome)
        return e
    return None


class Collector:
    """Componente de coleta: um tick de 5 s lê janela, entrada e bloqueio; microfone e câmera a
    cada 15 s; grava a pausa; a cada 30 s atualiza a bandeja com o total de hoje e a cada hora
    expurga os eventos antigos. `gi` só entra em `start()`."""

    def __init__(
        self,
        db_path: Path,
        tray,
        call: Callable[..., str] = gdbus_call,
        pw_dump: Callable[[], str] = mic.run_pw_dump,
        proc_root: Path = camera.PROC,
    ) -> None:
        self._db_path = db_path
        self._tray = tray
        self._call = call
        self._run_pw_dump = pw_dump
        self._proc_root = proc_root
        self._con: sqlite3.Connection | None = None
        self._source_id: int | None = None
        self._window = window.make(call)
        self._lock = lock.make(call)
        self._polls: list[tuple[str, Poll, float]] = [
            ("window", self._poll_window, TICK_SECONDS),
            ("input", self._poll_input, TICK_SECONDS),
            ("lock", self._poll_lock, TICK_SECONDS),
            ("mic", self._poll_mic, MIC_SECONDS),
            ("camera", self._poll_camera, MIC_SECONDS),
        ]
        self._last: dict[str, float] = {}
        self._last_today = float("-inf")
        self._last_purge = float("-inf")
        self._errors: dict[str, tuple[str, float]] = {}
        self._pw_cache: tuple[float, str] | None = None
        self._now = 0.0
        self._paused: bool | None = None
        self._settings_error: str | None = None
        self.settings = Settings()
        self.input = InputDetector()
        self.mic = Sustained(mic.SOURCE, "microfone")
        self.camera = Sustained(camera.SOURCE, "câmera")
        self.focus: dict[str, str] | None = None
        self.locked: bool | None = None
        self.idletime: float | None = None
        self.camera_holders: list[str] = []
        self.live: dict = {}

    def start(self) -> None:
        from gi.repository import GLib

        self._con = db.connect(self._db_path)
        self._emit(time.time(), "app", "control", f"coleta iniciada (jornada {__version__})")
        self.tick(time.time())
        self._source_id = GLib.timeout_add_seconds(int(TICK_SECONDS), self._on_timer)

    def stop(self) -> None:
        if self._source_id is not None:
            from gi.repository import GLib

            GLib.source_remove(self._source_id)
            self._source_id = None
        if self._con is not None:
            self._emit(time.time(), "app", "control", "coleta encerrada")
            self._con.close()
            self._con = None

    def _on_timer(self) -> bool:
        self.tick(time.time())
        return True

    def _emit(self, now, source, kind, message, data=None) -> None:
        if self._con is None:
            return
        try:
            events.emit(self._con, now, source, kind, message, data)
        except Exception:
            log.exception("evento não gravado: %s", message)

    def _load_settings(self, con: sqlite3.Connection, now: float) -> None:
        try:
            self.settings = settings.load(con)
            self._settings_error = None
        except ValueError as e:
            self.settings = Settings()
            if self._settings_error != str(e):
                self._settings_error = str(e)
                self._emit(now, "settings", "error", f"regras inválidas; valendo os padrões: {e}")

    def tick(self, now: float) -> None:
        con = self._con
        if con is None:
            return
        self._now = now
        self._load_settings(con, now)
        s = self.settings
        for nome, poll, intervalo in self._polls:
            if now - self._last.get(nome, float("-inf")) >= intervalo:
                self._last[nome] = now
                erro = safe_poll(nome, poll, con, now)
                if erro is not None:
                    self._report_error(nome, erro, now)
        self._track_pause(now)
        if self._tray.paused:
            safe_poll(PAUSE_SOURCE, record_pause, con, now)
        if now - self._last_purge >= PURGE_SECONDS:
            self._last_purge = now
            safe_poll("events", lambda c, n: events.purge(c, n, s.events_retention_days), con, now)
        if now - self._last_today >= TODAY_SECONDS:
            self._last_today = now
            self.refresh_tray(now)
        self.live = self.snapshot(now)
        self._tray.active = bool(self.live["reasons"])  # a pausa já tem ícone próprio

    def _report_error(self, nome: str, erro: Exception, now: float) -> None:
        """Um evento por mensagem nova, ou a cada 5 min enquanto a mesma falha se repete."""
        texto = f"{type(erro).__name__}: {erro}"
        anterior = self._errors.get(nome)
        if anterior and anterior[0] == texto and now - anterior[1] < ERROR_REPEAT_SECONDS:
            return
        self._errors[nome] = (texto, now)
        self._emit(now, nome, "error", f"coletor {nome} falhou: {texto}")

    def _track_pause(self, now: float) -> None:
        pausado = bool(self._tray.paused)
        if self._paused is not None and pausado != self._paused:
            self._emit(now, PAUSE_SOURCE, "control", "rastreio pausado" if pausado else "retomado")
        self._paused = pausado

    def _poll_window(self, con: sqlite3.Connection, now: float) -> None:
        foco = self._window(con, now)
        anterior = self.focus
        self.focus = foco
        if anterior is None or anterior["app"] != foco["app"]:
            self._emit(now, window.SOURCE, "state", f"foco: {foco['app']}", foco)
        elif self.settings.events_verbose and anterior != foco:
            self._emit(now, window.SOURCE, "reading", f"título: {foco['title']}", foco)

    def _poll_input(self, con: sqlite3.Connection, now: float) -> None:
        idletime = idle.read(self._call)
        self.idletime = idletime
        if idletime is not None:
            app = self.focus["app"] if self.focus else None
            self.input.step(con, now, idletime, self.settings, app)

    def _poll_lock(self, con: sqlite3.Connection, now: float) -> None:
        bloqueada = self._lock(con, now)
        if bloqueada is not None and self.locked is not None and bloqueada != self.locked:
            texto = "tela bloqueada" if bloqueada else "tela desbloqueada"
            self._emit(now, lock.SOURCE, "state", texto)
        if bloqueada is not None:
            self.locked = bloqueada

    def _pw_dump(self) -> str:
        """Uma chamada ao `pw-dump` por tick, dividida entre microfone e câmera."""
        if self._pw_cache is None or self._pw_cache[0] != self._now:
            self._pw_cache = (self._now, self._run_pw_dump())
        return self._pw_cache[1]

    def _poll_mic(self, con: sqlite3.Connection, now: float) -> None:
        s = self.settings
        if not s.mic_enabled:
            self.mic.disable(con, now)
            return
        ligado = mic.is_active(self._pw_dump)
        self.mic.step(con, now, ligado, s.mic_min_seconds, mic.MAX_GAP, s.events_verbose)

    def _poll_camera(self, con: sqlite3.Connection, now: float) -> None:
        s = self.settings
        if not s.camera_enabled:
            self.camera.disable(con, now)
            self.camera_holders = []
            return
        ligada, quem = camera.read(self._pw_dump, self._proc_root)
        self.camera_holders = quem
        self.camera.step(con, now, ligada, s.camera_min_seconds, camera.MAX_GAP, s.events_verbose)

    def snapshot(self, now: float) -> dict:
        """O estado ao vivo: o que cada detector leu e se o tempo está contando agora."""
        pausado = bool(self._tray.paused)
        motivos = []
        if self.input.counting and not self.locked:
            motivos.append("teclado/mouse")
        if self.mic.counting:
            motivos.append("microfone")
        if self.camera.counting:
            motivos.append("câmera")
        return {
            "ts": now,
            "paused": pausado,
            "counting": bool(motivos) and not pausado,
            "reasons": motivos,
            "input": self.input.status(now, self.idletime),
            "lock": {"locked": self.locked},
            "window": self.focus,
            "mic": {**self.mic.status(), "enabled": self.settings.mic_enabled},
            "camera": {
                **self.camera.status(),
                "enabled": self.settings.camera_enabled,
                "holders": self.camera_holders,
            },
            "settings": settings.to_dict(self.settings),
            "settingsError": self._settings_error,
        }

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
