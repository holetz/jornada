import io
import stat
from datetime import UTC, date, datetime

import pytest
from PIL import Image

from jornada.capture import store


def png(largura=1920, altura=1080):
    img = Image.effect_noise((largura, altura), 40).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_reduce_limita_largura_e_mantem_proporcao():
    dados = store.reduce(png(1920, 1080), 640)
    with Image.open(io.BytesIO(dados)) as img:
        assert img.format == "WEBP"
        assert img.size == (640, 360)


def test_reduce_nao_amplia():
    with Image.open(io.BytesIO(store.reduce(png(400, 300), 640))) as img:
        assert img.size == (400, 300)


def test_save_nome_por_dia_e_horario(tmp_path):
    destino = store.save(tmp_path, png(800, 450), datetime(2026, 11, 3, 9, 5, 7, tzinfo=UTC), 640)
    assert destino == tmp_path / "2026-11-03" / "090507.webp"
    assert destino.is_file()


def test_permissoes_0700_e_0600(tmp_path):
    raiz = tmp_path / "capturas"
    destino = store.save(raiz, png(800, 450), datetime(2026, 11, 3, 9, 5, 7, tzinfo=UTC), 640)
    assert stat.S_IMODE(raiz.stat().st_mode) == 0o700
    assert stat.S_IMODE(destino.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(destino.stat().st_mode) == 0o600


def test_permissao_e_corrigida_em_diretorio_existente(tmp_path):
    raiz = tmp_path / "capturas"
    raiz.mkdir(mode=0o755)
    store.save(raiz, png(800, 450), datetime(2026, 11, 3, 9, 0, 0, tzinfo=UTC), 640)
    assert stat.S_IMODE(raiz.stat().st_mode) == 0o700


def test_list_day_ordena_e_ignora_estranhos(tmp_path):
    for h in (10, 9):
        store.save(tmp_path, png(800, 450), datetime(2026, 11, 3, h, 0, 0, tzinfo=UTC), 640)
    (tmp_path / "2026-11-03" / "nota.txt").write_text("x")
    assert store.list_day(tmp_path, "2026-11-03") == ["090000.webp", "100000.webp"]
    assert store.list_day(tmp_path, "2026-11-04") == []
    assert store.list_day(tmp_path, "../x") == []


@pytest.mark.parametrize(
    ("dia", "apagado"),
    [("2026-10-02", True), ("2026-10-03", True), ("2026-10-04", False), ("2026-11-03", False)],
)
def test_purge_respeita_a_retencao(tmp_path, dia, apagado):
    y, m, d = map(int, dia.split("-"))
    store.save(tmp_path, png(800, 450), datetime(y, m, d, 12, 0, 0, tzinfo=UTC), 640)
    removidos = store.purge(tmp_path, date(2026, 11, 3), 30)
    assert (dia in removidos) is apagado
    assert (tmp_path / dia).exists() is not apagado


def test_purge_ignora_o_que_nao_e_dia_e_raiz_ausente(tmp_path):
    (tmp_path / "outro").mkdir()
    assert store.purge(tmp_path, date(2026, 11, 3), 30) == []
    assert (tmp_path / "outro").exists()
    assert store.purge(tmp_path / "nao-existe", date(2026, 11, 3), 30) == []


def test_tamanho_tipico_abaixo_de_60kb(tmp_path):
    img = Image.new("RGB", (1920, 1080), (30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    assert len(store.reduce(buf.getvalue(), 640)) < 60_000
