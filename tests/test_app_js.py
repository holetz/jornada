import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).parent.parent / "src" / "jornada" / "web" / "static" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="precisa do node")

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const [, , appJs, capturasStatus] = process.argv;

class Elemento {
  constructor(tag) {
    this.tag = tag; this.children = []; this.style = {}; this.hidden = false;
    this.textContent = ""; this.className = ""; this.cells = [];
  }
  append(...filhos) { this.children.push(...filhos); }
  replaceChildren(...filhos) { this.children = [...filhos]; }
  addEventListener() {}
  showModal() {}
  close() {}
}
const elementos = {};
const document = {
  cookie: "",
  getElementById: (id) => (elementos[id] ??= new Elemento(id)),
  createElement: (tag) => new Elemento(tag),
};

const detalhe = {
  spans: [{ start: 1759734000, end: 1759737600 }],
  windows: [{ app: "firefox", title: "Docs", minutes: 42 }],
};
async function fetch(caminho) {
  const cap = caminho.startsWith("/api/captures");
  const corpo = cap
    ? (capturasStatus === "200" ? [] : { error: "token inválido" })
    : caminho.endsWith("/detail") ? detalhe : [];
  const status = cap ? Number(capturasStatus) : 200;
  return { ok: status < 400, status, statusText: "x", json: async () => corpo };
}

const contexto = vm.createContext({
  document, fetch, Option: class {}, Date, Promise, JSON, Math, Number, String, Error,
  console, setTimeout,
});
vm.runInContext(fs.readFileSync(appJs, "utf8") + "\nglobalThis.detalhe = detalhe;", contexto);

(async () => {
  await new Promise((resolve) => setTimeout(resolve, 50));
  document.getElementById("erro").hidden = true;
  let erro = null;
  try { await contexto.detalhe("2025-10-06"); } catch (e) { erro = String(e.message); }
  const textos = (id) => (elementos[id]?.children ?? []).map((c) => c.textContent);
  console.log(JSON.stringify({
    erro,
    janelas: textos("janelas"),
    barras: elementos["linha-do-tempo"].children.length,
    faixa: textos("capturas"),
    bannerErro: elementos["erro"]?.hidden === false,
  }));
})();
"""


def rodar_detalhe(tmp_path, status_capturas):
    script = tmp_path / "harness.js"
    script.write_text(HARNESS)
    saida = subprocess.run(
        ["node", str(script), str(APP_JS), str(status_capturas)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(saida.stdout.strip().splitlines()[-1])


def test_detalhe_mostra_as_janelas_quando_as_capturas_respondem_403(tmp_path):
    r = rodar_detalhe(tmp_path, 403)
    assert r["erro"] is None
    assert r["janelas"] == ["firefox — Docs: 42 min"]
    assert r["barras"] == 1
    assert r["faixa"] == ["Capturas indisponíveis."]
    assert r["bannerErro"] is False


def test_detalhe_com_capturas_ok_mostra_janelas_e_faixa_vazia(tmp_path):
    r = rodar_detalhe(tmp_path, 200)
    assert r["erro"] is None
    assert r["janelas"] == ["firefox — Docs: 42 min"]
    assert r["faixa"] == ["Sem capturas neste dia."]
