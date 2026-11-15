"""Entrada ativa/ociosa pelo IdleMonitor do Mutter, com corte retroativo."""

import sqlite3
from collections.abc import Callable

from jornada import spans

IDLE_SECONDS = 180.0
SOURCE = "input"


def parse_idletime(saida: str) -> float | None:
    """`(uint64 1234,)` → 1.234 s; None se a saída não for reconhecida."""
    try:
        return int(saida.strip().strip("(),").split()[-1]) / 1000
    except (ValueError, IndexError):
        return None


def apply(con: sqlite3.Connection, now: float, idletime: float, idle_seconds: float = IDLE_SECONDS):
    """Grava a leitura: ativo estende `active`; ocioso corta o `active` em `now - idletime`."""
    if idletime < idle_seconds:
        spans.record(con, SOURCE, "active", now)
        return
    inicio = now - idletime
    spans.cut(con, SOURCE, "active", inicio)
    spans.record(con, SOURCE, "idle", now, start=inicio)


def make(call: Callable[..., str], idle_seconds: float = IDLE_SECONDS):
    """Coletor: `call(dest, path, method)` devolve a saída do gdbus."""

    def poll(con: sqlite3.Connection, now: float) -> None:
        saida = call(
            "org.gnome.Mutter.IdleMonitor",
            "/org/gnome/Mutter/IdleMonitor/Core",
            "org.gnome.Mutter.IdleMonitor.GetIdletime",
        )
        idletime = parse_idletime(saida)
        if idletime is not None:
            apply(con, now, idletime, idle_seconds)

    return poll
