import xml.etree.ElementTree as ET
from datetime import date

import pytest

from jornada import db, ledger, tray


def test_label():
    assert tray.label(paused=True) == "pausado"
    assert tray.label(paused=False) == "—"
    assert tray.label(paused=False, today="6h12") == "6h12"


def test_icon_name():
    assert tray.icon_name(True) == "jornada-pausado"
    assert tray.icon_name(False, active=True) == "jornada-ativo"
    assert tray.icon_name(False) == "jornada-ocioso"


@pytest.mark.parametrize("nome", ["ativo", "ocioso", "pausado"])
def test_svgs_empacotados_sao_validos(nome):
    arq = tray.ICON_DIR / f"jornada-{nome}.svg"
    assert ET.parse(arq).getroot().tag.endswith("svg")  # noqa: S314 — arquivo nosso


def test_set_paused_sem_gtk():
    t = tray.Tray(on_quit=lambda: None)
    t.set_paused(True)
    assert t.paused is True


@pytest.mark.desktop
def test_start_cria_indicador():
    t = tray.Tray(on_quit=lambda: None)
    t.start()
    assert t._indicator is not None
    t.stop()


def test_balance_text_sem_banco_e_sem_dias(tmp_path):
    assert tray.balance_text(tmp_path / "nao.db") == "Saldo: —"
    db.connect(tmp_path / "j.db").close()
    assert tray.balance_text(tmp_path / "j.db") == "Saldo: —"


def test_balance_text_com_dias(tmp_path, monkeypatch):
    db.connect(tmp_path / "j.db").close()
    dia = ledger.Day(date(2025, 10, 6), 0, 750, 0, 750, 750, ledger.Override())
    monkeypatch.setattr(ledger, "compute", lambda con: [dia])
    assert tray.balance_text(tmp_path / "j.db") == "Saldo: +12h30 (1,6 dia)"


def test_tray_aceita_a_url_de_depuracao_sem_gtk():
    t = tray.Tray(on_quit=lambda: None, debug_url=lambda: "http://127.0.0.1:1/debug.html?t=x")
    assert t._debug_url().endswith("debug.html?t=x")
