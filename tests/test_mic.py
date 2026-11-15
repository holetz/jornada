import subprocess
from pathlib import Path

from jornada.collectors import mic

FIX = Path(__file__).parent / "fixtures"


def le(nome):
    return (FIX / nome).read_text(encoding="utf-8")


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
