const $ = (id) => document.getElementById(id);
const token = () => document.cookie.split("; ").find((c) => c.startsWith("jornada_token="))?.split("=")[1] ?? "";

const FONTES = ["", "input", "mic", "camera", "lock", "window", "pause", "settings", "app"];
const TIPOS = ["", "state", "filter", "config", "control", "error", "reading"];
const NOME_TIPO = {
  state: "estado", filter: "filtro", config: "regra", control: "controle", error: "erro", reading: "leitura",
};
const ROTULOS = {
  "input.idleSeconds": ["Ociosidade de teclado/mouse (s)", "Sem entrada por esse tempo, e sem microfone/câmera, a contagem para na última entrada."],
  "input.minStreakSeconds": ["Atividade contínua mínima (s)", "Teclado/mouse só conta depois de uso contínuo por esse tempo; menos que isso é esbarrão. 0 conta na hora."],
  "input.streakGapSeconds": ["Intervalo máximo dentro da sequência (s)", "Pausa entre entradas que ainda mantém a sequência contínua."],
  "input.ignoreApps": ["Apps ignorados (wm_class)", "Separados por vírgula; com um deles em foco, teclado/mouse não conta."],
  "mic.enabled": ["Microfone conta como atividade", "Reuniões: microfone em uso soma mesmo sem teclado/mouse."],
  "mic.minSeconds": ["Uso mínimo do microfone (s)", "Usos mais curtos são ignorados."],
  "camera.enabled": ["Câmera conta como atividade", "Câmera aberta por algum processo (ou pelo PipeWire) soma como o microfone."],
  "camera.minSeconds": ["Uso mínimo da câmera (s)", "Usos mais curtos são ignorados."],
  "events.verbose": ["Eventos detalhados", "Grava também cada leitura (muitos eventos); para depurar por pouco tempo."],
  "events.retentionDays": ["Retenção dos eventos (dias)", "Eventos mais antigos são apagados a cada hora."],
};

let campos = {};
let maisAntigo = null;

async function api(metodo, caminho, corpo) {
  const r = await fetch(caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Jornada-Token": token() },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const dados = await r.json();
  if (!r.ok) throw new Error(dados.error === "token" ? "Abra esta página pelo menu da bandeja (token ausente)." : dados.error ?? r.statusText);
  return dados;
}

function mostrarErro(e) {
  $("erro").textContent = e ? e.message : "";
  $("erro").hidden = !e;
}

function el(tag, texto, classe) {
  const e = document.createElement(tag);
  if (texto !== undefined) e.textContent = texto;
  if (classe) e.className = classe;
  return e;
}

const horaDe = (ts) => new Date(ts * 1000).toLocaleTimeString("pt-BR");
const dataHora = (ts) => new Date(ts * 1000).toLocaleString("pt-BR");

function linhasAgora(v) {
  if (!v || v.available === false || v.ts === undefined) return [["Serviço", "sem leitura (coleta parada?)"]];
  const sim = (b) => (b ? "sim" : "não");
  const entrada = v.input ?? {};
  let teclado = entrada.state ?? "—";
  if (entrada.idletime !== null && entrada.idletime !== undefined) teclado += ` · ocioso há ${Math.round(entrada.idletime)} s`;
  if (entrada.streakSeconds !== null && entrada.streakSeconds !== undefined) teclado += ` · sequência de ${entrada.streakSeconds} s`;
  const fonte = (f) => (!f.enabled ? "desligado nas regras" : f.counting ? `contando desde ${horaDe(f.since)}` : f.on ? "em uso (confirmando)" : "livre");
  const camera = v.camera ?? {};
  return [
    ["Contando agora", v.paused ? "não (pausado)" : v.counting ? `sim — ${v.reasons.join(", ")}` : "não"],
    ["Teclado/mouse", teclado],
    ["Tela bloqueada", v.lock?.locked === null || v.lock?.locked === undefined ? "—" : sim(v.lock.locked)],
    ["Janela em foco", v.window ? `${v.window.app} — ${v.window.title || "(sem título)"}` : "—"],
    ["Microfone", fonte(v.mic ?? {})],
    ["Câmera", fonte(camera) + (camera.holders?.length ? ` (${camera.holders.join(", ")})` : "")],
    ["Última leitura", horaDe(v.ts)],
  ];
}

async function agora() {
  const v = await api("GET", "/api/live");
  const caixa = $("agora");
  caixa.replaceChildren();
  for (const [rotulo, valor] of linhasAgora(v)) {
    const c = el("div", undefined, "cartao");
    c.append(el("span", rotulo), el("b", valor));
    caixa.append(c);
  }
}

function lerFormulario(entradas, fields) {
  const regras = {};
  for (const [chave, meta] of Object.entries(fields)) {
    const entrada = entradas[chave];
    if (meta.type === "bool") regras[chave] = Boolean(entrada.checked);
    else if (meta.type === "list") regras[chave] = entrada.value.split(",").map((s) => s.trim()).filter(Boolean);
    else {
      const n = Number(entrada.value);
      if (entrada.value.trim() === "" || !Number.isInteger(n)) throw new Error(`${ROTULOS[chave]?.[0] ?? chave}: use um número inteiro`);
      regras[chave] = n;
    }
  }
  return regras;
}

let entradas = {};
function montarRegras(r) {
  campos = r.fields;
  entradas = {};
  const form = $("regras");
  form.replaceChildren();
  for (const [chave, meta] of Object.entries(r.fields)) {
    const [rotulo, dica] = ROTULOS[chave] ?? [chave, ""];
    const linha = el("label", undefined, "regra");
    const entrada = el("input");
    entrada.name = chave;
    const valor = r.settings[chave];
    if (meta.type === "bool") {
      entrada.type = "checkbox";
      entrada.checked = valor;
    } else if (meta.type === "list") {
      entrada.value = valor.join(", ");
    } else {
      entrada.type = "number";
      entrada.min = meta.min;
      entrada.max = meta.max;
      entrada.value = valor;
    }
    const padrao = r.defaults[chave];
    linha.append(el("span", rotulo), entrada, el("small", `${dica} Padrão: ${Array.isArray(padrao) ? padrao.join(", ") || "nenhum" : padrao}.`, "dica"));
    entradas[chave] = entrada;
    form.append(linha);
  }
  if (r.error) mostrarErro(new Error(`Regras gravadas inválidas (valendo os padrões): ${r.error}`));
}

async function salvarRegras(corpo) {
  mostrarErro(null);
  const r = await api("PUT", "/api/settings", corpo);
  montarRegras(r);
  $("regras-status").textContent = `Salvo às ${new Date().toLocaleTimeString("pt-BR")}.`;
  await eventos();
}

function filtros() {
  const p = new URLSearchParams({ limit: "200" });
  if ($("filtro-fonte").value) p.set("source", $("filtro-fonte").value);
  if ($("filtro-tipo").value) p.set("kind", $("filtro-tipo").value);
  return p;
}

function linhaEvento(e) {
  const tr = el("tr", undefined, `evento-${e.kind}`);
  tr.append(el("td", dataHora(e.ts)), el("td", e.source), el("td", NOME_TIPO[e.kind] ?? e.kind), el("td", e.message, "texto"));
  if (e.data) tr.title = JSON.stringify(e.data);
  return tr;
}

async function eventos(anteriores = false) {
  const p = filtros();
  if (anteriores && maisAntigo !== null) p.set("before", String(maisAntigo));
  const lista = await api("GET", `/api/events?${p}`);
  const corpo = $("eventos").tBodies[0];
  if (!anteriores) corpo.replaceChildren();
  for (const e of lista) corpo.append(linhaEvento(e));
  if (lista.length) maisAntigo = lista[lista.length - 1].ts;
  if (!anteriores && !lista.length) corpo.append(el("tr", "Nenhum evento com esses filtros."));
  return lista.length;
}

for (const f of FONTES) $("filtro-fonte").append(new Option(f || "todas", f));
for (const t of TIPOS) $("filtro-tipo").append(new Option(t ? NOME_TIPO[t] : "todos", t));
$("filtro-fonte").addEventListener("change", () => eventos().catch(mostrarErro));
$("filtro-tipo").addEventListener("change", () => eventos().catch(mostrarErro));
$("atualizar-eventos").addEventListener("click", () => eventos().catch(mostrarErro));
$("mais-eventos").addEventListener("click", () => eventos(true).catch(mostrarErro));
$("salvar-regras").addEventListener("click", () => {
  try {
    salvarRegras(lerFormulario(entradas, campos)).catch(mostrarErro);
  } catch (e) {
    mostrarErro(e);
  }
});
$("restaurar-regras").addEventListener("click", () => salvarRegras({ reset: true }).catch(mostrarErro));

api("GET", "/api/settings").then(montarRegras).catch(mostrarErro);
agora().catch(mostrarErro);
eventos().catch(mostrarErro);
setInterval(() => {
  agora().catch(mostrarErro);
  if ($("auto").checked) eventos().catch(mostrarErro);
}, 5000);
