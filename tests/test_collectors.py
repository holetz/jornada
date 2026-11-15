import json

import pytest

from jornada import db, events, settings
from jornada.collectors import gdbus_call, idle, lock, safe_poll
from jornada.settings import Settings


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


def test_idle_read_chama_o_idlemonitor():
    chamadas = []

    def call(*a):
        chamadas.append(a)
        return "(uint64 2000,)"

    assert idle.read(call) == 2.0
    assert chamadas[0][2] == "org.gnome.Mutter.IdleMonitor.GetIdletime"


def test_lock(con):
    poll = lock.make(lambda *a: "(true,)\n")
    poll(con, 100)
    poll(con, 105)
    assert spans_de(con, "lock") == [("locked", 100, 105)]
    assert lock.make(lambda *a: "(false,)\n")(con, 110) is False
    assert spans_de(con, "lock")[-1][0] == "unlocked"


def test_lock_saida_desconhecida_nao_grava(con):
    lock.make(lambda *a: "?")(con, 100)
    assert spans_de(con, "lock") == []


def test_safe_poll_captura(con, caplog):
    def quebra(c, n):
        raise RuntimeError("x")

    erro = safe_poll("t", quebra, con, 1)
    assert "falhou" in caplog.text
    assert isinstance(erro, RuntimeError)
    assert safe_poll("t", lambda c, n: None, con, 1) is None


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


class FakeTray:
    def __init__(self):
        self.paused = False
        self.active = False
        self.hoje = None

    def set_today(self, texto, desde=None):
        self.hoje = (texto, desde)


class Ambiente:
    """gdbus, pw-dump e /proc falsos; `ultima` é o instante da última entrada."""

    def __init__(self, tmp_path):
        self.ultima = 0.0
        self.agora = 0.0
        self.bloqueada = False
        self.app = "code"
        self.mic = False
        self.pw_chamadas = 0
        self.proc = tmp_path / "proc"
        self.proc.mkdir()

    def call(self, dest, path, method):
        if "GetIdletime" in method:
            return f"(uint64 {int((self.agora - self.ultima) * 1000)},)"
        if "GetActive" in method:
            return "(true,)" if self.bloqueada else "(false,)"
        return f'(\'{{"wm_class":"{self.app}","title":"t"}}\',)'

    def pw_dump(self):
        self.pw_chamadas += 1
        estado = "running" if self.mic else "suspended"
        return json.dumps(
            [{"info": {"state": estado, "props": {"media.class": "Stream/Input/Audio"}}}]
        )


@pytest.fixture
def coleta(tmp_path):
    from jornada.collectors import Collector

    amb = Ambiente(tmp_path)
    tray = FakeTray()
    c = Collector(tmp_path / "c.db", tray, amb.call, amb.pw_dump, amb.proc)
    c._con = db.connect(tmp_path / "c.db")

    def tick(agora, ultima=None):
        amb.agora = agora
        if ultima is not None:
            amb.ultima = ultima
        c.tick(agora)

    yield c, amb, tray, tick
    c._con.close()


def mensagens(con, kind=None):
    return [e["message"] for e in reversed(events.query(con, kind=kind))]


def test_coleta_ignora_esbarrao_e_confirma_atividade_continua(coleta):
    c, _amb, tray, tick = coleta
    tick(1000, 1000)
    tick(1005)
    tick(1010)
    tick(1015)
    assert tray.active is False
    assert any("esbarrão" in m for m in mensagens(c._con, "filter"))
    for t in range(1020, 1040, 5):
        tick(t, t - 1)
    assert tray.active is True
    assert c.live["reasons"] == ["teclado/mouse"]
    assert c.live["input"]["state"] == "contando"


def test_coleta_aplica_regras_do_banco_a_quente(coleta):
    c, _amb, tray, tick = coleta
    settings.save(c._con, Settings(min_streak_seconds=0))
    tick(1000, 1000)
    assert tray.active is True
    assert c.live["settings"]["input.minStreakSeconds"] == 0


def test_regras_corrompidas_caem_nos_padroes_com_um_evento(coleta):
    c, _amb, _tray, tick = coleta
    c._con.execute("INSERT INTO meta VALUES ('detection', '{quebrado')")
    c._con.commit()
    tick(1000, 900)
    tick(1005)
    assert c.settings == Settings()
    assert len(mensagens(c._con, "error")) == 1
    assert c.live["settingsError"]


def test_eventos_de_foco_bloqueio_e_pausa(coleta):
    c, amb, tray, tick = coleta
    tick(1000, 900)
    amb.app = "firefox"
    amb.bloqueada = True
    tray.paused = True
    tick(1005)
    assert mensagens(c._con, "state") == ["foco: code", "foco: firefox", "tela bloqueada"]
    assert mensagens(c._con, "control") == ["rastreio pausado"]
    assert c.live["paused"] is True and c.live["counting"] is False


def test_microfone_e_camera_dividem_um_pw_dump(coleta):
    c, amb, _tray, tick = coleta
    settings.save(c._con, Settings(camera_enabled=True))
    amb.mic = True
    tick(1000, 900)
    assert amb.pw_chamadas == 1
    assert c.live["reasons"] == ["microfone"]
    tick(1005)
    assert amb.pw_chamadas == 1  # mic e câmera só a cada 15 s


def test_microfone_desligado_nas_regras_nao_le(coleta):
    c, amb, _tray, tick = coleta
    settings.save(c._con, Settings(mic_enabled=False))
    amb.mic = True
    tick(1000, 900)
    assert amb.pw_chamadas == 0
    assert c.live["mic"]["enabled"] is False


def test_camera_pelo_proc(coleta):
    c, amb, _tray, tick = coleta
    settings.save(c._con, Settings(camera_enabled=True))
    pasta = amb.proc / "42"
    (pasta / "fd").mkdir(parents=True)
    (pasta / "comm").write_text("zoom\n")
    (pasta / "fd" / "3").symlink_to("/dev/video0")
    tick(1000, 900)
    assert c.live["camera"]["holders"] == ["zoom"]
    assert c.live["reasons"] == ["câmera"]
    assert "câmera em uso" in mensagens(c._con, "state")[-1]


def test_falha_repetida_gera_um_evento_por_janela(coleta):
    c, _amb, _tray, tick = coleta

    def quebra(*a):
        raise OSError("sem barramento")

    c._call = quebra
    for t in range(1000, 1100, 5):
        tick(t)
    erros = [m for m in mensagens(c._con, "error") if "input" in m]
    assert len(erros) == 1
    tick(1000 + 400)
    assert len([m for m in mensagens(c._con, "error") if "input" in m]) == 2


def test_expurgo_horario_dos_eventos(coleta):
    c, _amb, _tray, tick = coleta
    events.emit(c._con, 0, "app", "control", "muito antigo")
    tick(30 * 86400, 0)
    assert "muito antigo" not in mensagens(c._con)
