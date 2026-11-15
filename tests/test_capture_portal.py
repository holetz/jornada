import pytest

from jornada.capture import portal


def test_grab_devolve_bytes_e_apaga_o_temporario(tmp_path):
    arq = tmp_path / "Screenshot.png"
    arq.write_bytes(b"png")
    assert portal.grab(lambda: (0, arq.as_uri())) == b"png"
    assert not arq.exists()


def test_uri_com_espaco_e_acento(tmp_path):
    arq = tmp_path / "Imagens de tela" / "Captura é.png"
    arq.parent.mkdir()
    arq.write_bytes(b"x")
    assert portal.grab(lambda: (0, arq.as_uri())) == b"x"
    assert not arq.exists()


@pytest.mark.parametrize("code", [1, 2, -1])
def test_codigo_diferente_de_zero_e_recusa(code):
    with pytest.raises(portal.Refused):
        portal.grab(lambda: (code, None))


def test_sucesso_sem_uri_e_recusa():
    with pytest.raises(portal.Refused):
        portal.grab(lambda: (0, None))


def test_falha_da_chamada_vira_recusa():
    def falha():
        raise OSError("sem barramento")

    with pytest.raises(portal.Refused):
        portal.grab(falha)


def test_arquivo_sumido_e_recusa(tmp_path):
    with pytest.raises(portal.Refused):
        portal.grab(lambda: (0, (tmp_path / "nao.png").as_uri()))


@pytest.mark.desktop
def test_portal_real_recusa_ou_captura_png():
    # de um terminal o GNOME recusa; sob systemd devolve um PNG
    try:
        dados = portal.grab()
    except portal.Refused:
        return
    assert dados.startswith(b"\x89PNG")
