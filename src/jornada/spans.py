"""Gravação de spans com fusão por heartbeat.

Um span é um intervalo `[start, end]` de uma fonte num estado. Cada leitura estende o span
anterior da fonte quando o estado e os dados são os mesmos e a lacuna cabe na tolerância;
uma lacuna maior (suspensão, serviço parado) nunca é preenchida: abre-se outro span.
"""

import json
import sqlite3
from typing import Any

TICK_SECONDS = 5.0
GAP_TICKS = 3


def _encode(data: dict[str, Any] | None) -> str | None:
    return None if data is None else json.dumps(data, sort_keys=True, ensure_ascii=False)


def last(con: sqlite3.Connection, source: str) -> tuple[int, str, str | None, float, float] | None:
    """O span mais recente da fonte: (id, state, data, start, end)."""
    return con.execute(
        "SELECT id, state, data, start, end FROM span WHERE source = ? ORDER BY end DESC, id DESC "
        "LIMIT 1",
        (source,),
    ).fetchone()


def record(
    con: sqlite3.Connection,
    source: str,
    state: str,
    now: float,
    data: dict[str, Any] | None = None,
    *,
    max_gap: float = GAP_TICKS * TICK_SECONDS,
    start: float | None = None,
) -> None:
    """Estende o span anterior (mesmo estado e dados, lacuna ≤ `max_gap`) ou abre um novo.

    `start` só vale para um span novo (a ociosidade retroativa abre o `idle` no passado).
    """
    codificado = _encode(data)
    anterior = last(con, source)
    with con:
        if (
            anterior is not None
            and anterior[1] == state
            and anterior[2] == codificado
            and 0 <= now - anterior[4] <= max_gap
        ):
            con.execute("UPDATE span SET end = ? WHERE id = ?", (now, anterior[0]))
            return
        inicio = now if start is None else min(start, now)
        con.execute(
            "INSERT INTO span (source, state, data, start, end) VALUES (?, ?, ?, ?, ?)",
            (source, state, codificado, inicio, now),
        )


def cut(con: sqlite3.Connection, source: str, state: str, at: float) -> None:
    """Corta o span mais recente da fonte em `at` se ele estiver em `state` e passar de `at`.

    Nunca antes do início do próprio span.
    """
    anterior = last(con, source)
    if anterior is None or anterior[1] != state or anterior[4] <= at:
        return
    with con:
        con.execute("UPDATE span SET end = ? WHERE id = ?", (max(at, anterior[3]), anterior[0]))
