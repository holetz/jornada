"""Importa e exporta o banco de horas no layout da planilha `resumo`.

Colunas: A Data, B Realizado, C Distribuído, D Delta (Horas), E Delta (Dias), F Observação.
O Delta da planilha é previsto menos realizado; o app guarda realizado menos previsto
(positivo = a favor).
"""

import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook

from jornada import ledger

CABECALHO = ["Data", "Realizado", "Distribuído", "Delta (Horas)", "Delta (Dias)", "Observação"]
FORMATO_DATA = r"dd/mmm\ \(ddd\)"
FORMATO_HORA = "[h]:mm"


def to_minutes(valor: object) -> int:
    """Célula de hora → minutos; vazio → 0."""
    if isinstance(valor, datetime):
        valor = valor.time()
    if isinstance(valor, time):
        return valor.hour * 60 + valor.minute
    if isinstance(valor, timedelta):
        return round(valor.total_seconds() / 60)
    if isinstance(valor, int | float):
        return round(valor * 24 * 60)
    return 0


def kind_of(observacao: str | None) -> str | None:
    if not observacao:
        return None
    texto = observacao.strip().lower()
    if texto.startswith("feriado"):
        return "feriado"
    if texto.startswith("dayoff"):
        return "dayoff"
    if texto.startswith("covid"):
        return "ausencia"
    return "ajuste"


def import_sheet(con: sqlite3.Connection, caminho: Path) -> int:
    """Grava os dias da planilha como ajustes; devolve quantos dias. Idempotente."""
    ws = load_workbook(caminho, data_only=True).worksheets[0]
    linhas = [
        (r[0].value, r[1].value, r[2].value, r[5].value if len(r) > 5 else None)
        for r in ws.iter_rows(min_row=2)
        if isinstance(r[0].value, datetime | date)
    ]
    ultimo = max((i for i, (_d, b, _c, _o) in enumerate(linhas) if b is not None), default=-1)
    with con:
        for dia, realizado, distribuido, obs in linhas[: ultimo + 1]:
            dia = dia.date() if isinstance(dia, datetime) else dia
            obs = str(obs).strip() if obs not in (None, "") else None
            con.execute(
                "INSERT OR REPLACE INTO day (date, worked_override, expected_override, kind, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    dia.isoformat(),
                    to_minutes(realizado),
                    to_minutes(distribuido),
                    kind_of(obs),
                    obs,
                ),
            )
    return ultimo + 1


def export_sheet(
    con: sqlite3.Connection,
    caminho: Path,
    de: date | None = None,
    ate: date | None = None,
) -> int:
    """Escreve a planilha; devolve quantos dias. O intervalo recorta o que `compute` calcula."""
    dias = [d for d in ledger.compute(con, ate) if (de is None or d.date >= de)]
    wb = Workbook()
    ws = wb.active
    ws.append(CABECALHO)
    for n, d in enumerate(dias, start=2):
        ws.append(
            [
                datetime.combine(d.date, time.min),
                timedelta(minutes=d.worked),
                timedelta(minutes=d.expected),
                f"=-(SUM($B$2:B{n})-SUM($C$2:C{n}))*24",
                f"=D{n}/8",
                d.override.note,
            ]
        )
        ws.cell(n, 1).number_format = FORMATO_DATA
        ws.cell(n, 2).number_format = FORMATO_HORA
        ws.cell(n, 3).number_format = FORMATO_HORA
        ws.cell(n, 4).number_format = "0.00"
        ws.cell(n, 5).number_format = "0"
    wb.save(caminho)
    return len(dias)
