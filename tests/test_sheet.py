import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from jornada import db, ledger, sheet

# Planilha real de paridade, fora do repositório: aponte `JORNADA_PLANILHA_REAL` para ela.
REAL = Path(os.environ.get("JORNADA_PLANILHA_REAL", "/inexistente.xlsx")).expanduser()


def planilha(caminho, linhas):
    wb = Workbook()
    ws = wb.active
    ws.append(["Data", "Realizado", "Distribuido", "Delta (Horas)", "Delta (Dias)", None])
    for dia, b, c, obs in linhas:
        ws.append([datetime.combine(dia, time.min), b, c, None, None, obs])
    wb.save(caminho)


@pytest.fixture
def con(tmp_path):
    return db.connect(tmp_path / "j.db")


LINHAS = [
    (date(2025, 9, 22), time(8, 10), time(8, 0), None),
    (date(2025, 9, 23), None, None, "Script não rodou"),
    (date(2025, 9, 24), None, None, "Feriado"),
    (date(2025, 9, 25), time(7, 30), time(8, 0), "Dayoff manhã"),
    (date(2025, 9, 26), None, time(8, 0), "Covid"),
    (date(2025, 9, 27), time(1, 0), None, None),
    (date(2025, 9, 28), None, time(8, 0), None),  # depois do último Realizado: ignorada
]


def test_importa_com_kind_e_minutos(con, tmp_path):
    planilha(tmp_path / "a.xlsx", LINHAS)
    assert sheet.import_sheet(con, tmp_path / "a.xlsx") == 6
    linhas = con.execute("SELECT * FROM day ORDER BY date").fetchall()
    assert linhas[0] == ("2025-09-22", 490, 480, None, None)
    assert linhas[1] == ("2025-09-23", 0, 0, "ajuste", "Script não rodou")
    assert [r[3] for r in linhas[2:5]] == ["feriado", "dayoff", "ausencia"]
    assert linhas[5][1:3] == (60, 0)


def test_import_e_idempotente(con, tmp_path):
    planilha(tmp_path / "a.xlsx", LINHAS)
    sheet.import_sheet(con, tmp_path / "a.xlsx")
    sheet.import_sheet(con, tmp_path / "a.xlsx")
    assert con.execute("SELECT COUNT(*) FROM day").fetchone()[0] == 6


def test_saldo_importado_e_o_oposto_do_delta_da_planilha(con, tmp_path):
    planilha(tmp_path / "a.xlsx", LINHAS)
    sheet.import_sheet(con, tmp_path / "a.xlsx")
    dias = ledger.compute(con, date(2025, 9, 27), hoje=date(2025, 9, 27))
    realizado = 490 + 0 + 0 + 450 + 0 + 60
    previsto = 480 + 0 + 0 + 480 + 480 + 0
    assert dias[-1].balance == realizado - previsto


def test_exporta_no_layout_da_planilha(con, tmp_path):
    planilha(tmp_path / "a.xlsx", LINHAS)
    sheet.import_sheet(con, tmp_path / "a.xlsx")
    n = sheet.export_sheet(con, tmp_path / "b.xlsx", ate=date(2025, 9, 27))
    assert n == 6
    ws = load_workbook(tmp_path / "b.xlsx").worksheets[0]
    assert [c.value for c in ws[1]] == sheet.CABECALHO
    assert ws["B2"].value == timedelta(minutes=490)
    assert ws["B2"].number_format == "[h]:mm"
    assert ws["D3"].value == "=-(SUM($B$2:B3)-SUM($C$2:C3))*24"
    assert ws["E3"].value == "=D3/8"
    assert ws["F3"].value == "Script não rodou"


def test_export_recorta_o_inicio(con, tmp_path):
    planilha(tmp_path / "a.xlsx", LINHAS)
    sheet.import_sheet(con, tmp_path / "a.xlsx")
    n = sheet.export_sheet(con, tmp_path / "b.xlsx", de=date(2025, 9, 25), ate=date(2025, 9, 27))
    assert n == 3


def test_export_reimporta_sem_perder_dias(con, tmp_path):
    planilha(tmp_path / "a.xlsx", LINHAS)
    sheet.import_sheet(con, tmp_path / "a.xlsx")
    sheet.export_sheet(con, tmp_path / "b.xlsx", ate=date(2025, 9, 27))
    outro = db.connect(tmp_path / "o.db")
    sheet.import_sheet(outro, tmp_path / "b.xlsx")
    assert (
        outro.execute("SELECT * FROM day ORDER BY date").fetchall()
        == con.execute("SELECT * FROM day ORDER BY date").fetchall()
    )


@pytest.mark.desktop
@pytest.mark.skipif(not REAL.exists(), reason="planilha real ausente")
def test_paridade_com_a_planilha_real(tmp_path):
    con = db.connect(tmp_path / "j.db")
    sheet.import_sheet(con, REAL)
    ws = load_workbook(REAL, data_only=False).worksheets[0]
    linhas = [r for r in ws.iter_rows(min_row=2) if isinstance(r[0].value, datetime)]
    ultimo = max(r[0].row for r in linhas if r[1].value is not None)
    realizado = sum(sheet.to_minutes(r[1].value) for r in linhas if r[0].row <= ultimo)
    distribuido = sum(sheet.to_minutes(r[2].value) for r in linhas if r[0].row <= ultimo)
    dia = ws.cell(ultimo, 1).value.date()
    dias = ledger.compute(con, dia, hoje=dia)
    assert dias[-1].balance == realizado - distribuido


def test_cli_sheet_import_export(tmp_path, monkeypatch, capsys):
    from jornada.__main__ import main

    monkeypatch.setenv("JORNADA_HOME", str(tmp_path / "home"))
    planilha(tmp_path / "a.xlsx", LINHAS)
    assert main(["sheet", "import", str(tmp_path / "a.xlsx")]) == 0
    assert "importados 6 dias" in capsys.readouterr().out
    assert main(["sheet", "export", str(tmp_path / "b.xlsx"), "--ate", "2025-09-27"]) == 0
    assert "exportados 6 dias" in capsys.readouterr().out
    assert main(["sheet", "import", str(tmp_path / "nao-existe.xlsx")]) == 1
