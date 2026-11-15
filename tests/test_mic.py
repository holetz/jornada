import subprocess
from pathlib import Path

import pytest

from jornada import db
from jornada.collectors import mic

FIX = Path(__file__).parent / "fixtures"


def le(nome):
    return (FIX / nome).read_text(encoding="utf-8")


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "j.db")
    yield c
    c.close()


def test_running_detecta_stream_de_entrada():
    assert mic.running_in_pw_dump(le("pw-dump-mic-running.json")) is True


def test_idle_e_sink_nao_contam():
    assert mic.running_in_pw_dump(le("pw-dump-mic-idle.json")) is False


def test_proc_asound(tmp_path):
    sub = tmp_path / "card0" / "pcm0c" / "sub0"
    sub.mkdir(parents=True)
    (sub / "status").write_text("state: RUNNING\n")
    assert mic.running_in_proc(tmp_path) is True
    (sub / "status").write_text("closed\n")
    assert mic.running_in_proc(tmp_path) is False


def test_fallback_quando_pw_dump_falha():
    def falha():
        raise OSError("sem pw-dump")

    assert mic.is_active(falha, lambda: True) is True

    def lixo():
        return "não é json"

    assert mic.is_active(lixo, lambda: False) is False

    def lento():
        raise subprocess.TimeoutExpired("pw-dump", 5)

    assert mic.is_active(lento, lambda: True) is True


def test_poll_grava_e_funde(con):
    poll = mic.make(lambda: le("pw-dump-mic-running.json"), lambda: False)
    poll(con, 100.0)
    poll(con, 115.0)
    linhas = con.execute("SELECT state, start, end FROM span WHERE source='mic'").fetchall()
    assert linhas == [("active", 100.0, 115.0)]


def test_poll_inativo(con):
    mic.make(lambda: le("pw-dump-mic-idle.json"), lambda: True)(con, 100.0)
    assert con.execute("SELECT state FROM span WHERE source='mic'").fetchall() == [("inactive",)]
