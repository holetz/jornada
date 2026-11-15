import json
import shutil
import subprocess
from pathlib import Path

import pytest

DEBUG_JS = Path(__file__).parent.parent / "src" / "jornada" / "web" / "static" / "debug.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="precisa do node")

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const [, , debugJs] = process.argv;

class Elemento {
  constructor(tag) {
    this.tag = tag; this.children = []; this.style = {}; this.hidden = false;
    this.textContent = ""; this.className = ""; this.value = ""; this.checked = false;
    this.handlers = {}; this.tBodies = [];
  }
  append(...filhos) { this.children.push(...filhos); }
  replaceChildren(...filhos) { this.children = [...filhos]; }
  addEventListener(ev, fn) { this.handlers[ev] = fn; }
}
const elementos = {};
const document = {
  cookie: "jornada_token=t0k",
  getElementById: (id) => {
    if (!elementos[id]) {
      elementos[id] = new Elemento(id);
      if (id === "eventos") elementos[id].tBodies = [new Elemento("tbody")];
    }
    return elementos[id];
  },
  createElement: (tag) => new Elemento(tag),
};

const regras = {
  settings: { "input.idleSeconds": 180, "input.ignoreApps": [], "mic.enabled": true },
  defaults: { "input.idleSeconds": 180, "input.ignoreApps": [], "mic.enabled": true },
  fields: {
    "input.idleSeconds": { type: "int", min: 30, max: 3600 },
    "input.ignoreApps": { type: "list", min: null, max: null },
    "mic.enabled": { type: "bool", min: null, max: null },
  },
  error: null,
};
const vivo = {
  ts: 1759734000, paused: false, counting: true, reasons: ["teclado/mouse"],
  input: { state: "contando", idletime: 2.4, streakSeconds: null },
  lock: { locked: false }, window: { app: "code", title: "x" },
  mic: { enabled: true, on: false, counting: false, since: null },
  camera: { enabled: false, on: false, counting: false, since: null, holders: [] },
};
const eventosApi = [
  { id: 2, ts: 1759734005, source: "input", kind: "filter",
    message: "esbarrão ignorado", data: null },
  { id: 1, ts: 1759734000, source: "mic", kind: "state",
    message: "microfone em uso", data: { a: 1 } },
];
const chamadas = [];
async function fetch(caminho, opcoes) {
  const token = opcoes.headers["X-Jornada-Token"];
  chamadas.push({ caminho, metodo: opcoes.method, corpo: opcoes.body, token });
  let corpo = {};
  if (caminho.startsWith("/api/settings")) {
    corpo = opcoes.method === "PUT" ? { ...regras, settings: JSON.parse(opcoes.body) } : regras;
  }
  else if (caminho.startsWith("/api/live")) corpo = vivo;
  else if (caminho.startsWith("/api/events")) corpo = eventosApi;
  return { ok: true, status: 200, statusText: "ok", json: async () => corpo };
}

const contexto = vm.createContext({
  document, fetch, Option: class { constructor(t, v) { this.text = t; this.value = v; } },
  URLSearchParams, Date, Promise, JSON, Math, Number, String, Error, Object, Boolean, Array,
  console, setTimeout, setInterval: () => 0,
});
vm.runInContext(fs.readFileSync(debugJs, "utf8"), contexto);

(async () => {
  await new Promise((resolve) => setTimeout(resolve, 50));
  const form = elementos["regras"].children;
  const entrada = (nome) => form.find((l) => l.children[1].name === nome).children[1];
  entrada("input.idleSeconds").value = "120";
  entrada("input.ignoreApps").value = "spotify, , Slack";
  entrada("mic.enabled").checked = false;
  elementos["salvar-regras"].handlers.click();
  await new Promise((resolve) => setTimeout(resolve, 50));
  const put = chamadas.find((c) => c.metodo === "PUT");

  let erroInvalido = null;
  entrada("input.idleSeconds").value = "1.5";
  const campo = { "input.idleSeconds": entrada("input.idleSeconds") };
  try { contexto.lerFormulario(campo, { "input.idleSeconds": { type: "int" } }); }
  catch (e) { erroInvalido = e.message; }

  console.log(JSON.stringify({
    regras: form.length,
    put: put && JSON.parse(put.corpo),
    token: put && put.token,
    agora: elementos["agora"].children.map((c) => c.children.map((x) => x.textContent)),
    eventos: elementos["eventos"].tBodies[0].children
      .map((tr) => tr.children.map((td) => td.textContent).slice(1)),
    eventosUrl: chamadas.find((c) => c.caminho.startsWith("/api/events")).caminho,
    semColeta: contexto.linhasAgora({ available: false }),
    erroInvalido,
    status: elementos["regras-status"].textContent.startsWith("Salvo"),
    bannerErro: elementos["erro"].hidden === false,
  }));
})();
"""


@pytest.fixture(scope="module")
def pagina(tmp_path_factory):
    script = tmp_path_factory.mktemp("debug") / "harness.js"
    script.write_text(HARNESS)
    saida = subprocess.run(
        ["node", str(script), str(DEBUG_JS)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(saida.stdout.strip().splitlines()[-1])


def test_monta_o_formulario_e_salva_com_os_tipos_certos(pagina):
    assert pagina["regras"] == 3
    assert pagina["put"] == {
        "input.idleSeconds": 120,
        "input.ignoreApps": ["spotify", "Slack"],
        "mic.enabled": False,
    }
    assert pagina["token"] == "t0k"  # noqa: S105
    assert pagina["status"] is True
    assert pagina["bannerErro"] is False


def test_inteiro_invalido_e_recusado_antes_de_enviar(pagina):
    assert "número inteiro" in pagina["erroInvalido"]


def test_estado_ao_vivo_e_eventos(pagina):
    assert ["Contando agora", "sim — teclado/mouse"] in pagina["agora"]
    assert ["Teclado/mouse", "contando · ocioso há 2 s"] in pagina["agora"]
    assert ["Câmera", "desligado nas regras"] in pagina["agora"]
    assert pagina["eventos"] == [
        ["input", "filtro", "esbarrão ignorado"],
        ["mic", "estado", "microfone em uso"],
    ]
    assert pagina["eventosUrl"] == "/api/events?limit=200"
    assert pagina["semColeta"] == [["Serviço", "sem leitura (coleta parada?)"]]
