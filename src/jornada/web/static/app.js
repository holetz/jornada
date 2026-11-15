const $ = (id) => document.getElementById(id);
const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const TIPOS = ["", "feriado", "dayoff", "ausencia", "ajuste"];
const token = () => document.cookie.split("; ").find((c) => c.startsWith("jornada_token="))?.split("=")[1] ?? "";
let mes = new Date();
mes.setDate(1);

const hm = (min) => `${Math.floor(Math.abs(min) / 60)}:${String(Math.abs(min) % 60).padStart(2, "0")}`;
const sinal = (min) => (min < 0 ? "-" : "+") + hm(min);
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseHm = (texto) => {
  const t = texto.trim();
  if (t === "") return null;
  const m = t.match(/^(\d+):(\d{2})$/) ?? t.match(/^(\d+)$/);
  if (!m) throw new Error(`Hora inválida: ${t} (use h:mm)`);
  return Number(m[1]) * 60 + Number(m[2] ?? 0);
};

async function api(metodo, caminho, corpo) {
  const r = await fetch(caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Jornada-Token": token() },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const dados = await r.json();
  if (!r.ok) throw new Error(dados.error ?? r.statusText);
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

async function cartoes() {
  const r = await api("GET", "/api/summary");
  const caixa = $("cartoes");
  caixa.replaceChildren();
  const item = (rotulo, valor) => {
    const c = el("div", undefined, "cartao");
    c.append(el("span", rotulo), el("b", valor));
    caixa.append(c);
  };
  item("Saldo", `${sinal(r.balance)} (${r.balance_days.toString().replace(".", ",")} dia)`);
  item("Hoje", r.today ? `${hm(r.today.worked)} de ${hm(r.today.expected)}` : "—");
  item("Semana", `${hm(r.week.worked)} de ${hm(r.week.expected)}`);
}

function celulaEditavel(dia, campo, valor, aoSalvar) {
  const td = el("td", valor, "editavel");
  td.title = "Clique para corrigir; vazio remove a correção";
  td.addEventListener("click", () => {
    const campoEntrada = el("input");
    campoEntrada.value = valor;
    td.replaceChildren(campoEntrada);
    campoEntrada.focus();
    const salvar = () => aoSalvar(campoEntrada.value).catch(mostrarErro);
    campoEntrada.addEventListener("blur", salvar);
    campoEntrada.addEventListener("keydown", (ev) => ev.key === "Enter" && campoEntrada.blur());
  });
  return td;
}

async function salvarDia(d, mudancas) {
  const corpo = {
    worked: d.worked_override,
    expected: d.expected_override,
    kind: d.kind,
    note: d.note,
    ...mudancas,
  };
  mostrarErro(null);
  await api("PUT", `/api/days/${d.date}`, corpo);
  await tudo();
}

async function tabela() {
  const de = new Date(mes.getFullYear(), mes.getMonth(), 1);
  const ate = new Date(mes.getFullYear(), mes.getMonth() + 1, 0);
  $("titulo-mes").textContent = mes.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  const dias = await api("GET", `/api/days?from=${iso(de)}&to=${iso(ate)}`);
  const corpo = $("tabela").tBodies[0];
  corpo.replaceChildren();
  const hoje = iso(new Date());
  for (const d of dias) {
    const tr = el("tr");
    if (d.weekday >= 5) tr.classList.add("fim-de-semana");
    if (d.date > hoje) tr.classList.add("futuro");
    const data = el("td", d.date.slice(8) + "/" + d.date.slice(5, 7));
    data.style.cursor = "pointer";
    data.addEventListener("click", () => detalhe(d.date));
    tr.append(data, el("td", DIAS[d.weekday]), el("td", hm(d.measured)));
    tr.append(
      celulaEditavel(d, "worked", hm(d.worked), (v) => salvarDia(d, { worked: parseHm(v) })),
      celulaEditavel(d, "expected", hm(d.expected), (v) => salvarDia(d, { expected: parseHm(v) })),
    );
    tr.append(el("td", sinal(d.delta), d.delta < 0 ? "negativo" : "positivo"));
    tr.append(el("td", `${sinal(d.balance)} (${d.balance_days.toString().replace(".", ",")} d)`));
    const tipo = el("td");
    const seletor = el("select");
    for (const t of TIPOS) seletor.append(new Option(t || "—", t));
    seletor.value = d.kind ?? "";
    seletor.addEventListener("change", () => salvarDia(d, { kind: seletor.value || null }).catch(mostrarErro));
    tipo.append(seletor);
    tr.append(tipo);
    tr.append(celulaEditavel(d, "note", d.note ?? "", (v) => salvarDia(d, { note: v || null })));
    tr.cells[8].classList.add("texto");
    corpo.append(tr);
  }
  if (!dias.length) {
    const tr = el("tr");
    const td = el("td", "Sem dias lançados neste mês.");
    td.colSpan = 9;
    tr.append(td);
    corpo.append(tr);
  }
}

async function detalhe(data) {
  const r = await api("GET", `/api/days/${data}/detail`);
  $("detalhe").hidden = false;
  $("detalhe-titulo").textContent = `Detalhe de ${data}`;
  const linha = $("linha-do-tempo");
  linha.replaceChildren();
  const base = r.spans.length ? new Date(data + "T00:00:00").getTime() / 1000 : 0;
  for (const s of r.spans) {
    const barra = el("i");
    barra.style.left = `${((s.start - base) / 86400) * 100}%`;
    barra.style.width = `${Math.max(((s.end - s.start) / 86400) * 100, 0.2)}%`;
    linha.append(barra);
  }
  const lista = $("janelas");
  lista.replaceChildren();
  for (const j of r.windows) lista.append(el("li", `${j.app} — ${j.title || "(sem título)"}: ${j.minutes} min`));
  if (!r.windows.length) lista.append(el("li", "Sem janelas registradas."));
  await capturas(data);
}

async function capturas(data) {
  const faixa = $("capturas");
  faixa.replaceChildren();
  let itens;
  try {
    itens = await api("GET", `/api/captures?date=${data}`);
  } catch {
    faixa.append(el("p", "Capturas indisponíveis.", "dica"));
    return;
  }
  for (const c of itens) {
    const url = `/captures/${data}/${c.file}`;
    const fig = el("figure");
    const img = el("img");
    img.src = url;
    img.loading = "lazy";
    img.alt = `Captura das ${c.time}`;
    fig.append(img, el("figcaption", c.time.slice(0, 5)));
    fig.addEventListener("click", () => {
      $("ampliada-img").src = url;
      $("ampliada").showModal();
    });
    faixa.append(fig);
  }
  if (!itens.length) faixa.append(el("p", "Sem capturas neste dia.", "dica"));
}
$("ampliada").addEventListener("click", () => $("ampliada").close());

let periodos = [];
function jornada() {
  const t = $("jornada");
  t.replaceChildren();
  const cab = el("tr");
  for (const h of ["Desde", ...DIAS]) cab.append(el("th", h));
  t.append(cab);
  periodos.forEach((p) => {
    const tr = el("tr");
    const desde = el("input");
    desde.type = "date";
    desde.value = p.start;
    desde.addEventListener("change", () => (p.start = desde.value));
    const c = el("td");
    c.append(desde);
    tr.append(c);
    p.minutes.forEach((m, i) => {
      const entrada = el("input");
      entrada.type = "number";
      entrada.min = 0;
      entrada.value = m;
      entrada.addEventListener("change", () => (p.minutes[i] = Number(entrada.value)));
      const td = el("td");
      td.append(entrada);
      tr.append(td);
    });
    t.append(tr);
  });
}

async function tudo() {
  await Promise.all([cartoes(), tabela()]);
}

$("anterior").addEventListener("click", () => { mes.setMonth(mes.getMonth() - 1); tabela().catch(mostrarErro); });
$("proximo").addEventListener("click", () => { mes.setMonth(mes.getMonth() + 1); tabela().catch(mostrarErro); });
$("novo-periodo").addEventListener("click", () => {
  periodos.push({ start: iso(new Date()), minutes: [480, 480, 480, 480, 480, 0, 0] });
  jornada();
});
$("salvar-jornada").addEventListener("click", async () => {
  try {
    mostrarErro(null);
    periodos = await api("PUT", "/api/schedule", periodos);
    jornada();
    await tudo();
  } catch (e) {
    mostrarErro(e);
  }
});

api("GET", "/api/schedule").then((p) => { periodos = p; jornada(); }).catch(mostrarErro);
tudo().catch(mostrarErro);
