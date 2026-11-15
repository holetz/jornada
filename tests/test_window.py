import pytest

from jornada import db
from jornada.collectors import window


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "j.db")
    yield c
    c.close()


def spans_de(con):
    return con.execute("SELECT state, data, start, end FROM span WHERE source='window'").fetchall()


SAIDA = '(\'{"title":"README — jornada","wm_class":"code"}\',)\n'


def test_parse():
    assert window.parse(SAIDA) == {"app": "code", "title": "README — jornada"}
    assert window.parse("lixo") is None
    assert window.parse("('{quebrado}',)") is None
    assert window.parse('(\'{"title":"x"}\',)') == {"app": "desconhecida", "title": "x"}


def test_poll_com_extensao_funde(con):
    poll = window.make(lambda *a: SAIDA)
    assert poll(con, 100.0) == {"app": "code", "title": "README — jornada"}
    poll(con, 105.0)
    linhas = spans_de(con)
    assert len(linhas) == 1 and linhas[0][2:] == (100.0, 105.0)


def test_sem_extensao_degrada_e_funde(con):
    def falha(*a):
        raise OSError("sem extensão")

    poll = window.make(falha)
    poll(con, 100.0)
    poll(con, 105.0)
    linhas = spans_de(con)
    assert len(linhas) == 1
    assert "desconhecida" in linhas[0][1]


def test_extensao_volta(con):
    estado = {"ok": False}

    def call(*a):
        if not estado["ok"]:
            raise OSError("fora")
        return SAIDA

    poll = window.make(call)
    poll(con, 100.0)
    estado["ok"] = True
    poll(con, 105.0)
    assert [s for s, *_ in spans_de(con)] == ["focus", "focus"]
