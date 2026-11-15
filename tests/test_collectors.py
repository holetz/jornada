import pytest

from jornada import db
from jornada.collectors import gdbus_call, idle, lock, safe_poll


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "j.db")
    yield c
    c.close()


def spans_de(con, source):
    return con.execute(
        "SELECT state, start, end FROM span WHERE source=? ORDER BY id", (source,)
    ).fetchall()


def test_parse_idletime():
    assert idle.parse_idletime("(uint64 1500,)\n") == 1.5
    assert idle.parse_idletime("lixo") is None


def test_idle_ativo_estende(con):
    idle.apply(con, 100, 2)
    idle.apply(con, 105, 0.5)
    assert spans_de(con, "input") == [("active", 100, 105)]


def test_idle_corte_retroativo(con):
    for t in (100, 105, 110):
        idle.apply(con, t, 1)
    # ocioso há 180 s no instante 290: o último movimento foi em 110
    idle.apply(con, 290, 180)
    assert spans_de(con, "input") == [("active", 100, 110), ("idle", 110, 290)]
    idle.apply(con, 295, 185)
    assert spans_de(con, "input")[-1] == ("idle", 110, 295)


def test_idle_volta_a_ativo(con):
    idle.apply(con, 100, 1)
    idle.apply(con, 300, 200)
    idle.apply(con, 305, 0.1)
    assert [s[0] for s in spans_de(con, "input")] == ["active", "idle", "active"]


def test_lock(con):
    poll = lock.make(lambda *a: "(true,)\n")
    poll(con, 100)
    poll(con, 105)
    assert spans_de(con, "lock") == [("locked", 100, 105)]
    lock.make(lambda *a: "(false,)\n")(con, 110)
    assert spans_de(con, "lock")[-1][0] == "unlocked"


def test_lock_saida_desconhecida_nao_grava(con):
    lock.make(lambda *a: "?")(con, 100)
    assert spans_de(con, "lock") == []


def test_safe_poll_captura(con, caplog):
    def quebra(c, n):
        raise RuntimeError("x")

    safe_poll("t", quebra, con, 1)
    assert "falhou" in caplog.text


def test_gdbus_call_ausente(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr("subprocess.run", boom)
    with pytest.raises(FileNotFoundError):
        gdbus_call("a", "/b", "c.d")


@pytest.mark.desktop
def test_desktop_leitores_reais():
    saida = gdbus_call(
        "org.gnome.Mutter.IdleMonitor",
        "/org/gnome/Mutter/IdleMonitor/Core",
        "org.gnome.Mutter.IdleMonitor.GetIdletime",
    )
    assert idle.parse_idletime(saida) is not None
    saida = gdbus_call(
        "org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.GetActive"
    )
    assert lock.parse_active(saida) is not None
