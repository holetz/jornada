"""Janela em foco pela extensão focused-window-dbus; sem ela, `app="desconhecida"`."""

import json
import sqlite3
from collections.abc import Callable

from jornada import spans

SOURCE = "window"
DESCONHECIDA = {"app": "desconhecida", "title": ""}


def parse(saida: str) -> dict[str, str] | None:
    """`('{json}',)` → {"app", "title"}; None quando não há payload JSON."""
    ini, fim = saida.find("{"), saida.rfind("}")
    if ini < 0 or fim < ini:
        return None
    try:
        dados = json.loads(saida[ini : fim + 1])
    except ValueError:
        return None
    return {"app": dados.get("wm_class") or "desconhecida", "title": dados.get("title") or ""}


def make(call: Callable[..., str]):
    """Falha da chamada (extensão fora, tela bloqueada) é estado normal: não loga a cada tick."""

    def poll(con: sqlite3.Connection, now: float) -> None:
        try:
            dados = parse(
                call(
                    "org.gnome.Shell",
                    "/org/gnome/shell/extensions/FocusedWindow",
                    "org.gnome.shell.extensions.FocusedWindow.Get",
                )
            )
        except OSError:
            dados = None
        spans.record(con, SOURCE, "focus", now, DESCONHECIDA if dados is None else dados)

    return poll
