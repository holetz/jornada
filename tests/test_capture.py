import io
import time
from types import SimpleNamespace

import pytest
from PIL import Image

from jornada import config, db, spans
from jornada.capture import NO_PERMISSION, REFUSAL_BACKOFF, Capture, Retention, portal


def png():
    buf = io.BytesIO()
    Image.new("RGB", (800, 450), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


class FakeTray(SimpleNamespace):
    def set_capture_status(self, texto):
        self.capture_status = texto


@pytest.fixture
def tray():
    return FakeTray(paused=False, capture_paused=False, capture_status=None)


@pytest.fixture
def cap(tmp_path, tray):
    chamadas = []

    def grab():
        chamadas.append(1)
        return png()

    c = Capture(tmp_path / "capturas", tmp_path / "j.db", tray, grab=grab)
    c._con = db.connect(tmp_path / "j.db")
    c.chamadas = chamadas
    yield c
    c._con.close()


def arquivos(cap):
    return sorted(cap._root.glob("*/*.webp"))


def test_captura_quando_livre(cap):
    assert cap.tick(time.time()) is True
    assert len(arquivos(cap)) == 1


@pytest.mark.parametrize("atributo", ["paused", "capture_paused"])
def test_pausas_nao_capturam(cap, tray, atributo):
    setattr(tray, atributo, True)
    assert cap.tick(time.time()) is False
    assert cap.chamadas == []


def test_tela_bloqueada_nao_captura_e_desbloqueada_volta(cap):
    agora = time.time()
    spans.record(cap._con, "lock", "locked", agora)
    assert cap.tick(agora) is False
    assert cap.chamadas == []
    spans.record(cap._con, "lock", "unlocked", agora + 5)
    assert cap.tick(agora + 60) is True


def test_recusa_para_por_uma_hora_e_avisa(cap, tray):
    def recusa():
        cap.chamadas.append(1)
        raise portal.Refused("não")

    cap._grab = recusa
    agora = time.time()
    assert cap.tick(agora) is False
    assert tray.capture_status == NO_PERMISSION
    cap.tick(agora + 60)
    assert len(cap.chamadas) == 1
    cap._grab = lambda: png()
    assert cap.tick(agora + REFUSAL_BACKOFF + 1) is True
    assert tray.capture_status is None


def test_falha_ao_gravar_nao_derruba(cap):
    cap._grab = lambda: b"nao e imagem"
    assert cap.tick(time.time()) is False


def test_tick_apaga_dias_antigos(cap):
    antigo = cap._root / "2020-01-01"
    antigo.mkdir(parents=True)
    (antigo / "120000.webp").write_bytes(b"x")
    cap.tick(time.time())
    assert not antigo.exists()


def test_retencao_apaga_dias_antigos_sem_captura(tmp_path):
    raiz = tmp_path / "capturas"
    antigo = raiz / "2020-01-01"
    recente = raiz / time.strftime("%Y-%m-%d")
    for pasta in (antigo, recente):
        pasta.mkdir(parents=True)
        (pasta / "120000.webp").write_bytes(b"x")
    Retention(raiz, retention_days=30).purge(time.time())
    assert not antigo.exists()
    assert recente.exists()


def test_config_de_capturas(tmp_path):
    arq = tmp_path / "c.toml"
    arq.write_text(
        "[capture]\nenabled = true\nintervalSeconds = 30\nwidth = 320\nretentionDays = 7\n"
    )
    cfg = config.load(arq)
    assert (cfg.capture_enabled, cfg.capture_interval, cfg.capture_width) == (True, 30, 320)
    assert cfg.capture_retention_days == 7
    assert config.load(tmp_path / "nao.toml").capture_enabled is False


def test_tray_pausar_capturas_sem_gtk():
    from jornada import tray

    t = tray.Tray(on_quit=lambda: None, capture_enabled=True)
    assert t.capture_paused is False
    t.set_capture_paused(True)
    assert t.capture_paused is True
    t.set_capture_status(NO_PERMISSION)
    assert t.capture_status == NO_PERMISSION
