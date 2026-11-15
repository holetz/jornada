import time
from datetime import date

import pytest

from jornada import __version__, app, db
from jornada.__main__ import main


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("JORNADA_HOME", str(tmp_path))
    monkeypatch.delenv("JORNADA_CONFIG", raising=False)


def test_version(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_status_sem_banco(capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "banco ainda não criado" in out
    assert "dados:" in out


def test_status_com_banco(capsys, tmp_path):
    db.connect(tmp_path / "data" / "jornada.db").close()
    main(["status"])
    assert f"user_version: {len(db.MIGRATIONS)}" in capsys.readouterr().out


def test_subcomando_obrigatorio():
    with pytest.raises(SystemExit):
        main([])


def test_app_inicia_e_para_em_ordem_inversa_tolerando_falha():
    eventos = []

    class C:
        def __init__(self, nome, falha=False):
            self.nome, self.falha = nome, falha

        def start(self):
            eventos.append(("start", self.nome))

        def stop(self):
            eventos.append(("stop", self.nome))
            if self.falha:
                raise RuntimeError

    a = app.App()
    a.register(C("a"))
    a.register(C("b", falha=True))
    a.start()
    a.stop()
    assert eventos == [("start", "a"), ("start", "b"), ("stop", "b"), ("stop", "a")]


def test_today_sem_banco(capsys):
    assert main(["today"]) == 0
    assert "banco ainda não criado" in capsys.readouterr().out


def test_today_com_spans(capsys, tmp_path):
    import time

    con = db.connect(tmp_path / "data" / "jornada.db")
    agora = time.time()
    con.execute(
        "INSERT INTO span (source, state, data, start, end) VALUES ('input','active',NULL,?,?)",
        (agora - 3600, agora),
    )
    con.commit()
    con.close()
    main(["today"])
    assert "Hoje: " in capsys.readouterr().out


def test_collector_tick_grava_pausa_e_atualiza_bandeja(tmp_path):
    from jornada import tray
    from jornada.collectors import Collector

    class FakeTray:
        paused = True
        active = False
        hoje = None

        def set_today(self, texto, desde=None):
            self.hoje = (texto, desde)

    def call(dest, path, method):
        if "GetIdletime" in method:
            return "(uint64 0,)"
        if "GetActive" in method:
            return "(false,)"
        raise OSError("sem extensão")

    caminho = tmp_path / "c.db"
    t = FakeTray()
    c = Collector(caminho, t, call)
    c._con = db.connect(caminho)
    c._polls = [p for p in c._polls if p[0] not in ("mic", "camera")]
    agora = time.time()
    for i in range(3):  # idletime 0 em três ticks: 10 s de atividade contínua confirmam
        c.tick(agora + 5 * i)
    fontes = {r[0] for r in c._con.execute("SELECT source FROM span")}
    assert {"input", "lock", "window", "pause"} <= fontes
    assert t.hoje is not None and t.active is True
    assert tray.today_line("1h00", "08:03") == "Hoje: 1h00 · ativo desde 08:03"
    c._con.close()


def test_ledger_sem_banco(capsys):
    assert main(["ledger"]) == 0
    assert "banco ainda não criado" in capsys.readouterr().out


def test_ledger_com_dias(capsys, tmp_path):
    con = db.connect(tmp_path / "data" / "jornada.db")
    hoje = date.today()  # noqa: DTZ011
    con.execute(
        "INSERT INTO day (date, worked_override, expected_override) VALUES (?, 500, 480)",
        (hoje.isoformat(),),
    )
    con.commit()
    con.close()
    assert main(["ledger"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Saldo: +0h20")
    assert f"{hoje:%Y-%m-%d}   8h20  8h00  +0h20" in out


def test_events_sem_banco(capsys):
    assert main(["events"]) == 0
    assert "banco ainda não criado" in capsys.readouterr().out


def test_events_lista_do_mais_antigo_ao_mais_recente(capsys, tmp_path):
    from jornada import events

    con = db.connect(tmp_path / "data" / "jornada.db")
    events.emit(con, 1000, "input", "filter", "esbarrão ignorado")
    events.emit(con, 2000, "mic", "state", "microfone em uso")
    con.close()
    assert main(["events"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert "esbarrão ignorado" in linhas[0] and "microfone em uso" in linhas[1]
    main(["events", "--source", "mic", "-n", "5"])
    assert "esbarrão" not in capsys.readouterr().out
    main(["events", "--kind", "error"])
    assert "Nenhum evento" in capsys.readouterr().out


def test_settings_mostra_altera_e_restaura(capsys, tmp_path):
    from jornada import events, settings

    assert main(["settings"]) == 0
    assert "input.idleSeconds = 180\n" in capsys.readouterr().out + "\n"
    assert main(["settings", "--set", "input.idleSeconds=120", "--set", "camera.enabled=true"]) == 0
    out = capsys.readouterr().out
    assert "input.idleSeconds = 120   (padrão: 180)" in out
    con = db.connect(tmp_path / "data" / "jornada.db")
    assert settings.load(con).idle_seconds == 120
    assert "input.idleSeconds: 180 → 120" in events.query(con, kind="config")[0]["message"]
    con.close()
    assert main(["settings", "--set", "input.idleSeconds=1"]) == 1
    assert "entre 30 e 3600" in capsys.readouterr().err
    assert main(["settings", "--reset"]) == 0
    assert "(padrão" not in capsys.readouterr().out
