"""SQLite em WAL com migrações numeradas por `PRAGMA user_version`.

Nunca se edita uma migração publicada: acrescente a próxima.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path


def _m1_meta(con: sqlite3.Connection) -> None:
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def _m2_span(con: sqlite3.Connection) -> None:
    """Intervalos por fonte; `start`/`end` em epoch UTC (segundos), `data` em JSON ou nulo."""
    con.execute(
        "CREATE TABLE span ("
        "id INTEGER PRIMARY KEY, source TEXT NOT NULL, state TEXT NOT NULL, data TEXT, "
        "start REAL NOT NULL, end REAL NOT NULL)"
    )
    con.execute("CREATE INDEX span_source_start ON span (source, start)")


def _m3_origin(con: sqlite3.Connection) -> None:
    """Origem do span: `jornada` (coletores), `aw` ou `work-tracking` (importados)."""
    con.execute("ALTER TABLE span ADD COLUMN origin TEXT NOT NULL DEFAULT 'jornada'")
    con.execute("CREATE INDEX span_origin_start ON span (origin, start)")


def _m4_ledger(con: sqlite3.Connection) -> None:
    """Banco de horas: jornada por período (`minutes` = JSON seg..dom) e ajustes por dia."""
    con.execute("CREATE TABLE schedule (start_date TEXT PRIMARY KEY, minutes TEXT NOT NULL)")
    con.execute(
        "CREATE TABLE day (date TEXT PRIMARY KEY, worked_override INTEGER, "
        "expected_override INTEGER, kind TEXT, note TEXT)"
    )
    con.execute("INSERT INTO schedule VALUES ('2025-09-22', '[480, 480, 480, 480, 480, 0, 0]')")


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [
    _m1_meta,
    _m2_span,
    _m3_origin,
    _m4_ledger,
]


def user_version(con: sqlite3.Connection) -> int:
    return con.execute("PRAGMA user_version").fetchone()[0]


def migrate(con: sqlite3.Connection) -> int:
    atual = user_version(con)
    for numero, passo in enumerate(MIGRATIONS, start=1):
        if numero <= atual:
            continue
        with con:
            passo(con)
            con.execute(f"PRAGMA user_version = {numero}")
    return user_version(con)


def connect(caminho: Path) -> sqlite3.Connection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA journal_mode=WAL")
    migrate(con)
    return con
