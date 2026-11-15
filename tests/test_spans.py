import json

import pytest

from jornada import db, spans


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "j.db")
    yield c
    c.close()


def linhas(con, source="input"):
    return con.execute(
        "SELECT state, data, start, end FROM span WHERE source = ? ORDER BY id", (source,)
    ).fetchall()


def test_migracao_2_cria_span_e_indice(con):
    assert db.user_version(con) >= 2
    indices = [r[1] for r in con.execute("PRAGMA index_list(span)")]
    assert "span_source_start" in indices


def test_primeira_leitura_abre_span(con):
    spans.record(con, "input", "active", 100.0)
    assert linhas(con) == [("active", None, 100.0, 100.0)]


def test_heartbeat_estende_o_span(con):
    for t in (100.0, 105.0, 110.0):
        spans.record(con, "input", "active", t)
    assert linhas(con) == [("active", None, 100.0, 110.0)]


def test_lacuna_maior_que_3_ticks_abre_novo(con):
    spans.record(con, "input", "active", 100.0)
    spans.record(con, "input", "active", 115.0)  # exatamente 3 ticks: funde
    spans.record(con, "input", "active", 131.0)  # 16 s: suspensão, não preenche
    assert linhas(con) == [("active", None, 100.0, 115.0), ("active", None, 131.0, 131.0)]


def test_estado_diferente_abre_novo(con):
    spans.record(con, "input", "active", 100.0)
    spans.record(con, "input", "idle", 105.0)
    assert [r[0] for r in linhas(con)] == ["active", "idle"]


def test_dados_diferentes_abrem_novo_e_iguais_fundem(con):
    foco = {"app": "x", "title": "á"}
    spans.record(con, "window", "focus", 100.0, foco)
    spans.record(con, "window", "focus", 105.0, {"title": "á", "app": "x"})
    spans.record(con, "window", "focus", 110.0, {"app": "y", "title": "á"})
    rs = linhas(con, "window")
    assert len(rs) == 2
    assert json.loads(rs[0][1]) == foco
    assert rs[0][3] == 105.0


def test_fontes_sao_independentes(con):
    spans.record(con, "input", "active", 100.0)
    spans.record(con, "lock", "unlocked", 101.0)
    spans.record(con, "input", "active", 105.0)
    assert linhas(con) == [("active", None, 100.0, 105.0)]


def test_max_gap_proprio(con):
    spans.record(con, "mic", "active", 100.0, max_gap=45)
    spans.record(con, "mic", "active", 130.0, max_gap=45)
    assert len(linhas(con, "mic")) == 1


def test_start_retroativo_so_em_span_novo(con):
    spans.record(con, "input", "idle", 200.0, start=150.0)
    assert linhas(con) == [("idle", None, 150.0, 200.0)]


def test_cut_corta_o_span_do_estado(con):
    for t in (100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0):
        spans.record(con, "input", "active", t)
    spans.cut(con, "input", "active", 110.0)
    assert linhas(con) == [("active", None, 100.0, 110.0)]


def test_cut_nao_vai_antes_do_inicio_nem_toca_outro_estado(con):
    spans.record(con, "input", "active", 100.0)
    spans.cut(con, "input", "active", 50.0)
    assert linhas(con) == [("active", None, 100.0, 100.0)]
    spans.record(con, "input", "idle", 105.0)
    spans.cut(con, "input", "active", 90.0)
    assert linhas(con)[1] == ("idle", None, 105.0, 105.0)


def test_cut_sem_span_e_noop(con):
    spans.cut(con, "input", "active", 1.0)
    assert linhas(con) == []
