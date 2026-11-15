import json
import subprocess

from jornada.collectors import camera


def processo(raiz, pid, comm, alvos):
    pasta = raiz / str(pid)
    (pasta / "fd").mkdir(parents=True)
    (pasta / "comm").write_text(comm + "\n")
    for i, alvo in enumerate(alvos):
        (pasta / "fd" / str(i)).symlink_to(alvo)


def pw(estado, classe="Video/Source"):
    return json.dumps([{"info": {"state": estado, "props": {"media.class": classe}}}])


def test_holders_acha_quem_abriu_a_camera(tmp_path):
    processo(tmp_path, 10, "firefox", ["/dev/null", "/dev/video0", "/dev/video2"])
    processo(tmp_path, 11, "bash", ["/dev/pts/1"])
    processo(tmp_path, 12, "zoom", ["/dev/video1"])
    (tmp_path / "self").mkdir()
    assert camera.holders(tmp_path) == ["firefox", "zoom"]


def test_holders_sem_proc_legivel(tmp_path):
    (tmp_path / "13").mkdir()  # sem fd/ (outro usuário)
    assert camera.holders(tmp_path) == []
    assert camera.holders(tmp_path / "nao-existe") == []


def test_pw_dump_video_source_running():
    assert camera.running_in_pw_dump(pw("running")) is True
    assert camera.running_in_pw_dump(pw("suspended")) is False
    assert camera.running_in_pw_dump(pw("running", "Audio/Source")) is False


def test_read_prefere_proc_e_cai_no_pipewire(tmp_path):
    processo(tmp_path, 10, "bash", ["/dev/null"])
    assert camera.read(lambda: pw("suspended"), tmp_path) == (False, [])
    assert camera.read(lambda: pw("running"), tmp_path) == (True, ["pipewire"])
    processo(tmp_path, 20, "chrome", ["/dev/video0"])
    assert camera.read(lambda: pw("suspended"), tmp_path) == (True, ["chrome"])


def test_read_tolera_pw_dump_quebrado(tmp_path):
    def falha():
        raise OSError("sem pw-dump")

    def lento():
        raise subprocess.TimeoutExpired("pw-dump", 5)

    assert camera.read(falha, tmp_path) == (False, [])
    assert camera.read(lento, tmp_path) == (False, [])
    assert camera.read(lambda: "lixo", tmp_path) == (False, [])
    assert camera.read(None, tmp_path) == (False, [])
