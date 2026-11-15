"""Componente de capturas: uma imagem reduzida da tela a cada intervalo, só local.

Pula a captura com a tela bloqueada, o rastreio pausado ou "Pausar capturas" marcado; lê o
bloqueio do banco, gravado pelo coletor `lock` (sem segunda leitura de D-Bus). Sem permissão do
portal, para de tentar por `REFUSAL_BACKOFF` e mostra o aviso no menu. `gi` só entra em `start()`.
"""

import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from jornada import db, spans
from jornada.capture import portal, store

log = logging.getLogger("jornada.capture")

PURGE_SECONDS = 3600
REFUSAL_BACKOFF = 3600.0
NO_PERMISSION = "Capturas: sem permissão"


def _purge(root: Path, now: float, retention_days: int) -> None:
    hoje = datetime.fromtimestamp(now).astimezone().date()
    try:
        for dia in store.purge(root, hoje, retention_days):
            log.info("capturas de %s apagadas pela retenção", dia)
    except OSError:
        log.exception("limpeza das capturas falhou")


class Capture:
    def __init__(
        self,
        root: Path,
        db_path: Path,
        tray,
        interval: int = 60,
        width: int = 640,
        retention_days: int = 30,
        grab: Callable[[], bytes] = portal.grab,
    ) -> None:
        self._root = root
        self._db_path = db_path
        self._tray = tray
        self._interval = interval
        self._width = width
        self._retention_days = retention_days
        self._grab = grab
        self._con: sqlite3.Connection | None = None
        self._sources: list[int] = []
        self._blocked_until = 0.0
        self._last_purge = float("-inf")

    def start(self) -> None:
        from gi.repository import GLib

        self._con = db.connect(self._db_path)
        store.ensure_dir(self._root)
        self.tick(time.time())
        self._sources.append(GLib.timeout_add_seconds(self._interval, self._on_timer))

    def stop(self) -> None:
        if self._sources:
            from gi.repository import GLib

            for fonte in self._sources:
                GLib.source_remove(fonte)
            self._sources.clear()
        if self._con is not None:
            self._con.close()
            self._con = None

    def _on_timer(self) -> bool:
        self.tick(time.time())
        return True

    def locked(self) -> bool:
        ultimo = spans.last(self._con, "lock") if self._con is not None else None
        return ultimo is not None and ultimo[1] == "locked"

    def tick(self, now: float) -> bool:
        """Um ciclo: limpeza a cada hora e, se nada pausa, uma captura. Devolve se gravou."""
        if now - self._last_purge >= PURGE_SECONDS:
            self._last_purge = now
            self.purge(now)
        if (
            self._tray.paused
            or self._tray.capture_paused
            or self.locked()
            or now < self._blocked_until
        ):
            return False
        try:
            png = self._grab()
        except portal.Refused as e:
            log.warning("captura recusada, nova tentativa em 1 h: %s", e)
            self._blocked_until = now + REFUSAL_BACKOFF
            self._tray.set_capture_status(NO_PERMISSION)
            return False
        try:
            store.save(self._root, png, datetime.fromtimestamp(now).astimezone(), self._width)
        except Exception:
            log.exception("gravar a captura falhou")
            return False
        if self._tray.capture_status:
            self._tray.set_capture_status(None)
        return True

    def purge(self, now: float) -> None:
        _purge(self._root, now, self._retention_days)


class Retention:
    """Só a limpeza por retenção, para quando a captura está desligada.

    Apaga os dias com mais de `retention_days` dias na subida e a cada `PURGE_SECONDS`.
    """

    def __init__(self, root: Path, retention_days: int = 30) -> None:
        self._root = root
        self._retention_days = retention_days
        self._source: int | None = None

    def start(self) -> None:
        from gi.repository import GLib

        self.purge(time.time())
        self._source = GLib.timeout_add_seconds(PURGE_SECONDS, self._on_timer)

    def stop(self) -> None:
        if self._source is not None:
            from gi.repository import GLib

            GLib.source_remove(self._source)
            self._source = None

    def _on_timer(self) -> bool:
        self.purge(time.time())
        return True

    def purge(self, now: float) -> None:
        _purge(self._root, now, self._retention_days)
