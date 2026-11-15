import json
import threading
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from jornada import db
from jornada.web import server

TOKEN = "segredo"  # noqa: S105


@pytest.fixture
def api(tmp_path):
    caminho = tmp_path / "j.db"
    con = db.connect(caminho)
    con.execute("INSERT INTO day (date, worked_override) VALUES ('2025-10-06', 500)")
    con.commit()
    con.close()
    srv = server.make_server(caminho, 0, TOKEN, tmp_path / "capturas")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def chamar(metodo, caminho_url, corpo=None, token=TOKEN, host=None, cookie=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(  # noqa: S310
            base + caminho_url, data=dados, method=metodo
        )
        if token:
            req.add_header("X-Jornada-Token", token)
        if host:
            req.add_header("Host", host)
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req) as r:  # noqa: S310
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    yield chamar
    srv.shutdown()
    srv.server_close()


def json_de(resp):
    return json.loads(resp[1])


def test_dias_calculam_saldo(api):
    dias = json_de(api("GET", "/api/days?from=2025-10-06&to=2025-10-07"))
    assert [(d["date"], d["worked"], d["expected"], d["balance"]) for d in dias] == [
        ("2025-10-06", 500, 480, 20),
        ("2025-10-07", 0, 480, -460),
    ]


def test_corrigir_realizado_recalcula_na_hora(api):
    r = api("PUT", "/api/days/2025-10-06", {"worked": 600, "note": "extra"})
    assert json_de(r)["balance"] == 120
    dias = json_de(api("GET", "/api/days?from=2025-10-06&to=2025-10-06"))
    assert dias[0]["note"] == "extra"


def test_marcar_feriado_zera_o_previsto(api):
    api("PUT", "/api/days/2025-10-07", {"kind": "feriado"})
    dia = json_de(api("GET", "/api/days?from=2025-10-07&to=2025-10-07"))[0]
    assert (dia["expected"], dia["kind"]) == (0, "feriado")


def test_corpo_vazio_apaga_o_ajuste(api):
    api("PUT", "/api/days/2025-10-06", {})
    assert json_de(api("GET", "/api/days?from=2025-10-06&to=2025-10-06")) == []


def test_mudar_a_jornada_recalcula(api):
    novo = [
        {"start": "2025-09-22", "minutes": [480] * 5 + [0, 0]},
        {"start": "2025-10-07", "minutes": [420] * 5 + [0, 0]},
    ]
    assert api("PUT", "/api/schedule", novo)[0] == 200
    assert json_de(api("GET", "/api/schedule")) == novo
    dia = json_de(api("GET", "/api/days?from=2025-10-07&to=2025-10-07"))[0]
    assert dia["expected"] == 420


def test_escrita_sem_token_e_403(api):
    for token in (None, "errado"):
        assert api("PUT", "/api/days/2025-10-06", {"worked": 1}, token=token)[0] == 403
    assert json_de(api("GET", "/api/days?from=2025-10-06&to=2025-10-06"))[0]["worked"] == 500


def test_host_estranho_e_recusado(api):
    assert api("GET", "/api/summary", host="evil.example")[0] == 403


def test_entrada_invalida_e_400(api):
    assert api("PUT", "/api/days/2025-10-06", {"worked": -5})[0] == 400
    assert api("PUT", "/api/days/2025-10-06", {"kind": "outro"})[0] == 400
    assert api("PUT", "/api/schedule", [{"start": "2025-10-01", "minutes": [1]}])[0] == 400
    assert api("GET", "/api/days?from=ontem")[0] == 400


def test_resumo_e_exportacao(api):
    resumo = json_de(api("GET", "/api/summary"))
    assert resumo["balance_text"].startswith("Saldo: ")
    assert set(resumo) >= {"balance", "balance_days", "today", "week"}
    status, corpo, cab = api("GET", "/api/export.xlsx")
    assert status == 200 and corpo[:2] == b"PK"
    assert "spreadsheetml" in cab["Content-Type"]


def test_detalhe_do_dia_traz_janelas(api, tmp_path):
    dia = date(2025, 10, 6)
    from jornada import metrics

    ini, _ = metrics.day_bounds(dia)
    con = db.connect(tmp_path / "j.db")
    con.execute(
        "INSERT INTO span (source, state, data, start, end) VALUES "
        "('window', 'focus', ?, ?, ?), ('input', 'active', NULL, ?, ?)",
        ('{"app": "code", "title": "x"}', ini + 100, ini + 700, ini + 100, ini + 700),
    )
    con.commit()
    con.close()
    d = json_de(api("GET", "/api/days/2025-10-06/detail"))
    assert d["windows"] == [{"app": "code", "title": "x", "minutes": 10.0}]
    assert d["spans"] == [{"start": ini + 100, "end": ini + 700}]


def test_rota_inexistente_e_404(api):
    assert api("GET", "/api/nada")[0] == 404


def test_pagina_e_estaticos_com_cookie_do_token(api):
    status, corpo, cab = api("GET", f"/?t={TOKEN}")
    assert status == 200 and b"Banco de horas" in corpo
    assert (
        cab["Set-Cookie"].startswith(f"jornada_token={TOKEN}")
        and "SameSite=Strict" in cab["Set-Cookie"]
    )
    assert "Set-Cookie" not in api("GET", "/?t=errado")[2]
    assert api("GET", "/app.js")[0] == 200
    assert api("GET", "/style.css")[0] == 200


def test_estatico_nao_escapa_da_pasta(api):
    assert api("GET", "/..%2f..%2fconfig.py")[0] == 404
    assert api("GET", "/../server.py")[0] == 404


@pytest.fixture
def capturas(tmp_path):
    pasta = tmp_path / "capturas" / "2025-10-06"
    pasta.mkdir(parents=True)
    (pasta / "093000.webp").write_bytes(b"RIFFwebp")
    (pasta / "090000.webp").write_bytes(b"RIFFwebp")
    (tmp_path / "segredo.txt").write_text("fora")
    return tmp_path


def test_lista_de_capturas_do_dia_em_ordem(api, capturas):
    r = json_de(api("GET", "/api/captures?date=2025-10-06"))
    assert [c["time"] for c in r] == ["09:00:00", "09:30:00"]
    assert json_de(api("GET", "/api/captures?date=2025-10-07")) == []


def test_arquivo_da_captura_e_servido_como_webp(api, capturas):
    status, corpo, cab = api("GET", "/captures/2025-10-06/090000.webp")
    assert (status, corpo, cab["Content-Type"]) == (200, b"RIFFwebp", "image/webp")


def test_capturas_exigem_o_token_pelo_cookie_ou_cabecalho(api, capturas):
    assert api("GET", "/api/captures?date=2025-10-06", token=None)[0] == 403
    assert api("GET", "/captures/2025-10-06/090000.webp", token=None)[0] == 403
    cookie = f"jornada_token={TOKEN}"
    assert api("GET", "/captures/2025-10-06/090000.webp", token=None, cookie=cookie)[0] == 200


@pytest.mark.parametrize(
    "caminho",
    [
        "/captures/2025-10-06/../segredo.txt",
        "/captures/..%2F/segredo.txt",
        "/captures/2025-10-06/segredo.txt",
        "/captures/2025-10-06/%2e%2e%2fsegredo.txt",
        "/captures/2025-10-06/999999.webp",
    ],
)
def test_captura_nao_sai_do_diretorio(api, capturas, caminho):
    assert api("GET", caminho)[0] in (400, 404)


def test_regras_padrao_e_limites(api):
    r = json_de(api("GET", "/api/settings"))
    assert r["settings"] == r["defaults"]
    assert r["settings"]["input.idleSeconds"] == 180
    assert r["fields"]["input.idleSeconds"] == {"type": "int", "min": 30, "max": 3600}
    assert r["fields"]["input.ignoreApps"]["type"] == "list"
    assert r["error"] is None


def test_salvar_regras_persiste_e_registra_evento(api, tmp_path):
    corpo = {"input.idleSeconds": 120, "camera.enabled": True, "input.ignoreApps": ["spotify"]}
    r = json_de(api("PUT", "/api/settings", corpo))
    assert r["settings"]["input.idleSeconds"] == 120
    assert r["settings"]["camera.enabled"] is True
    assert r["settings"]["mic.enabled"] is True  # ausente volta ao padrão
    assert json_de(api("GET", "/api/settings"))["settings"] == r["settings"]
    ev = json_de(api("GET", "/api/events?kind=config"))
    assert "input.idleSeconds: 180 → 120" in ev[0]["message"]
    r = json_de(api("PUT", "/api/settings", {"reset": True}))
    assert r["settings"] == r["defaults"]


def test_regras_invalidas_sao_400_e_sem_token_403(api):
    assert api("PUT", "/api/settings", {"input.idleSeconds": 5})[0] == 400
    assert api("PUT", "/api/settings", {"nada": 1})[0] == 400
    assert api("PUT", "/api/settings", [1])[0] == 400
    assert api("PUT", "/api/settings", {"input.idleSeconds": 120}, token=None)[0] == 403
    assert api("GET", "/api/settings", token=None)[0] == 403


def test_eventos_exigem_token_e_filtram(api, tmp_path):
    from jornada import events

    con = db.connect(tmp_path / "j.db")
    events.emit(con, 100, "input", "filter", "esbarrão ignorado")
    events.emit(con, 200, "mic", "state", "microfone em uso")
    con.close()
    assert api("GET", "/api/events", token=None)[0] == 403
    cookie = f"jornada_token={TOKEN}"
    todos = json_de(api("GET", "/api/events", token=None, cookie=cookie))
    assert [e["message"] for e in todos] == ["microfone em uso", "esbarrão ignorado"]
    assert len(json_de(api("GET", "/api/events?source=input"))) == 1
    assert len(json_de(api("GET", "/api/events?before=200"))) == 1
    assert len(json_de(api("GET", "/api/events?limit=1"))) == 1
    assert api("GET", "/api/events?kind=nada")[0] == 400
    assert api("GET", "/api/events?limit=x")[0] == 400


def test_estado_ao_vivo(tmp_path):
    caminho = tmp_path / "j.db"
    db.connect(caminho).close()
    srv = server.make_server(caminho, 0, TOKEN, tmp_path, live=lambda: {"counting": True})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/api/live"
    try:
        req = urllib.request.Request(base, headers={"X-Jornada-Token": TOKEN})
        with urllib.request.urlopen(req) as r:  # noqa: S310
            assert json.loads(r.read()) == {"counting": True}
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base)
    finally:
        srv.shutdown()
        srv.server_close()


def test_ao_vivo_sem_coletor(api):
    assert json_de(api("GET", "/api/live")) == {"available": False}


def test_pagina_de_depuracao_grava_o_cookie(api):
    status, corpo, cab = api("GET", f"/debug.html?t={TOKEN}")
    assert status == 200 and b"Regras de detec" in corpo
    assert cab["Set-Cookie"].startswith(f"jornada_token={TOKEN}")
    assert "Set-Cookie" not in api("GET", f"/debug.js?t={TOKEN}")[2]
    assert api("GET", "/debug.js")[0] == 200


def test_urls_do_servidor():
    w = server.WebServer(Path("x.db"), 8765)
    assert w.url == f"http://127.0.0.1:8765/?t={w.token}"
    assert w.debug_url == f"http://127.0.0.1:8765/debug.html?t={w.token}"
