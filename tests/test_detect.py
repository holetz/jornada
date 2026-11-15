import pytest

from jornada import db, events
from jornada.detect import InputDetector, Sustained
from jornada.settings import Settings

PADRAO = Settings()  # 10 s contínuos, intervalo de 10 s, ocioso em 180 s


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "j.db")
    yield c
    c.close()


def spans_de(con, source="input"):
    return con.execute(
        "SELECT state, start, end FROM span WHERE source=? ORDER BY id", (source,)
    ).fetchall()


def ativos(con, source="input"):
    return [(a, b) for st, a, b in spans_de(con, source) if st == "active"]


def tipos(con, kind):
    return [e["message"] for e in reversed(events.query(con, kind=kind))]


def rodar(det, con, leituras, s=PADRAO, app=None):
    """`leituras`: (agora, instante da última entrada)."""
    for agora, ultima in leituras:
        det.step(con, agora, agora - ultima, s, app)


def test_esbarrao_isolado_nao_conta_e_vira_evento(con):
    det = InputDetector()
    rodar(det, con, [(1000, 1000), (1005, 1000), (1010, 1000), (1015, 1000)])
    assert ativos(con) == []
    assert det.counting is False
    assert len(tipos(con, "filter")) == 1
    assert "esbarrão ignorado" in tipos(con, "filter")[0]


def test_atividade_continua_conta_desde_o_inicio_da_sequencia(con):
    det = InputDetector()
    rodar(det, con, [(1000, 999), (1005, 1004), (1010, 1009), (1015, 1014)])
    assert det.counting is True
    # confirmou em 1010 (1009 - 999 = 10 s) e conta desde 999
    assert ativos(con) == [(999, 1015)]
    assert "atividade confirmada" in tipos(con, "state")[0]


def test_intervalo_maior_que_o_tolerado_quebra_a_sequencia(con):
    det = InputDetector()
    # 1000 e 1004, pausa de 12 s, depois 1016: duas sequências curtas
    rodar(det, con, [(1000, 1000), (1005, 1004), (1010, 1004), (1017, 1016)])
    assert ativos(con) == []
    assert len(tipos(con, "filter")) == 1
    assert det.streak_start == 1016


def test_ociosidade_corta_na_ultima_entrada(con):
    s = Settings(idle_seconds=120)
    det = InputDetector()
    # entrada contínua até 1050, depois nada; ticks de 5 s
    leituras = [(t, min(t - 1, 1050)) for t in range(1000, 1170, 5)]
    rodar(det, con, leituras, s)
    assert det.counting is True
    det.step(con, 1170, 1170 - 1050, s)  # 120 s sem entrada
    assert det.counting is False
    assert ativos(con) == [(999, 1050)]
    assert spans_de(con)[-1] == ("idle", 1050, 1170)
    assert "contagem parou às" in tipos(con, "state")[-1]


def test_sequencia_minima_zero_conta_na_primeira_entrada(con):
    det = InputDetector()
    s = Settings(min_streak_seconds=0)
    rodar(det, con, [(1000, 1000), (1005, 1000)], s)
    assert ativos(con) == [(1000, 1005)]


def test_primeira_leitura_antiga_nao_abre_sequencia(con):
    det = InputDetector()
    rodar(det, con, [(1000, 900), (1005, 900), (1020, 900)])
    assert det.streak_start is None
    assert tipos(con, "filter") == []


def test_app_ignorado_nao_conta_e_para_a_contagem(con):
    s = Settings(ignore_apps=("Spotify",), min_streak_seconds=0)
    det = InputDetector()
    rodar(det, con, [(1000, 1000), (1005, 1004)], s, app="code")
    assert det.counting is True
    rodar(det, con, [(1010, 1009), (1015, 1014)], s, app="spotify")
    assert det.counting is False
    assert det.status(1015)["state"] == "ignorado"
    assert ativos(con) == [(1000, 1005)]
    assert spans_de(con)[-1][0] == "ignored"
    assert len(tipos(con, "filter")) == 1
    rodar(det, con, [(1020, 1019)], s, app="code")
    assert det.counting is True


def test_modo_detalhado_grava_cada_leitura(con):
    det = InputDetector()
    rodar(det, con, [(1000, 999), (1005, 1004)], Settings(events_verbose=True))
    assert len(tipos(con, "reading")) == 2


def test_status_da_sequencia_em_andamento(con):
    det = InputDetector()
    rodar(det, con, [(1000, 1000), (1005, 1004)])
    st = det.status(1005, 1)
    assert st["state"] == "confirmando"
    assert st["streakSeconds"] == 4


def test_sustentado_minimo_zero_conta_na_hora(con):
    mic = Sustained("mic", "microfone")
    mic.step(con, 100, True, 0, 45)
    mic.step(con, 115, True, 0, 45)
    assert ativos(con, "mic") == [(100, 115)]
    assert "microfone em uso" in tipos(con, "state")[0]


def test_sustentado_curto_e_ignorado(con):
    mic = Sustained("mic", "microfone")
    for agora, ligado in ((100, True), (115, True), (130, False)):
        mic.step(con, agora, ligado, 60, 45)
    assert ativos(con, "mic") == []
    assert "uso curto de microfone ignorado" in tipos(con, "filter")[0]


def test_sustentado_longo_conta_desde_a_primeira_leitura(con):
    cam = Sustained("camera", "câmera")
    for agora in (100, 115, 130, 145, 160):
        cam.step(con, agora, True, 60, 45)
    assert cam.counting is True
    assert ativos(con, "camera") == [(100, 160)]
    cam.step(con, 175, False, 60, 45)
    assert "câmera livre" in tipos(con, "state")[-1]
    assert spans_de(con, "camera")[-1][0] == "inactive"


def test_sustentado_desligado_nas_regras(con):
    mic = Sustained("mic", "microfone")
    mic.step(con, 100, True, 0, 45)
    mic.disable(con, 110)
    assert mic.counting is False
    assert tipos(con, "config") == ["microfone desligado nas regras"]
