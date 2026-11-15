"""Log de eventos dos detectores para depuração; `ts` em epoch UTC, `data` JSON ou nulo."""

import json
import sqlite3

KINDS = ("state", "filter", "reading", "config", "control", "error")


def emit(
    con: sqlite3.Connection,
    ts: float,
    source: str,
    kind: str,
    message: str,
    data: dict | None = None,
) -> None:
    """Grava um evento com tipo válido e dados opcionais em JSON."""
    if kind not in KINDS:
        raise ValueError(f"Tipo de evento inválido: {kind}")
    dados = json.dumps(data, sort_keys=True, ensure_ascii=False) if data is not None else None
    with con:
        con.execute(
            "INSERT INTO event (ts, source, kind, message, data) VALUES (?, ?, ?, ?, ?)",
            (ts, source, kind, message, dados),
        )


def query(
    con: sqlite3.Connection,
    *,
    limit: int = 200,
    source: str | None = None,
    kind: str | None = None,
    before: float | None = None,
    since: float | None = None,
) -> list[dict]:
    """Consulta eventos do mais recente ao mais antigo, combinando os filtros."""
    filtros = []
    parametros = []
    for condicao, valor in (
        ("source = ?", source),
        ("kind = ?", kind),
        ("ts < ?", before),
        ("ts > ?", since),
    ):
        if valor is not None:
            filtros.append(condicao)
            parametros.append(valor)
    sql = "SELECT id, ts, source, kind, message, data FROM event"
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY ts DESC, id DESC LIMIT ?"
    parametros.append(max(1, min(limit, 5000)))
    return [
        {
            "id": id_,
            "ts": ts,
            "source": origem,
            "kind": tipo,
            "message": mensagem,
            "data": json.loads(dados) if dados is not None else None,
        }
        for id_, ts, origem, tipo, mensagem, dados in con.execute(sql, parametros)
    ]


def purge(con: sqlite3.Connection, now: float, retention_days: int) -> int:
    """Apaga eventos anteriores ao período de retenção e retorna a contagem."""
    with con:
        cursor = con.execute("DELETE FROM event WHERE ts < ?", (now - retention_days * 86400,))
    return cursor.rowcount
