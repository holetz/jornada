"""Tela bloqueada/desbloqueada pelo org.gnome.ScreenSaver."""

import sqlite3
from collections.abc import Callable

from jornada import spans

SOURCE = "lock"


def parse_active(saida: str) -> bool | None:
    s = saida.strip()
    if "true" in s:
        return True
    if "false" in s:
        return False
    return None


def make(call: Callable[..., str]):
    """Grava `locked`/`unlocked` e devolve a leitura (None quando não reconhecida)."""

    def poll(con: sqlite3.Connection, now: float) -> bool | None:
        ativo = parse_active(
            call(
                "org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.GetActive"
            )
        )
        if ativo is not None:
            spans.record(con, SOURCE, "locked" if ativo else "unlocked", now)
        return ativo

    return poll
