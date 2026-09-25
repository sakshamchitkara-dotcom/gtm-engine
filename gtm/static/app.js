// Dashboard: plain DOM, textContent only (lead data is untrusted input).
const $ = (id) => document.getElementById(id);
let token = new URLSearchParams(location.hash.slice(1)).get("token") || sessionStorage.getItem("gtm-token") || "";

async function api(path) {
  const r = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (r.status === 401) throw Object.assign(new Error("unauthorized"), { status: 401 });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function table(el, cols, rows) {
  el.replaceChildren();
  const head = el.insertRow();
  for (const [label, , num] of cols) {
    const th = document.createElement("th");
    th.textContent = label;
    if (num) th.className = "n";
    head.appendChild(th);
  }
  for (const row of rows) {
    const tr = el.insertRow();
    for (const [, get, num] of cols) {
      const td = tr.insertCell();
      const v = get(row);
      if (v instanceof Node) { td.appendChild(v); td.classList.add("bar-cell"); } else td.textContent = v ?? "";
      if (num) td.classList.add("n");
    }
  }
}

const money = (n) => "$" + Math.round(n).toLocaleString();
function bar(frac) {
  const d = document.createElement("div");
  d.className = "bar";
  d.style.width = `${Math.max(2, frac * 100)}%`;
  return d;
}

const LIMIT = 50;
let byTier = {}, leadsSeq = 0;

async function loadLeads() {
  const tier = $("tier").value, seq = ++leadsSeq;
  const rows = await api(`/api/leads?limit=${LIMIT}${tier ? "&tier=" + encodeURIComponent(tier) : ""}`);
  if (seq !== leadsSeq) return; // a newer filter change already won; don't paint stale rows
  const total = tier ? byTier[tier] || 0 : Object.values(byTier).reduce((a, b) => a + b, 0);
  $("lead-count").textContent = `showing ${rows.length} of ${total}`;
  table($("leads"), [
    ["Score", (r) => r.score, true], ["Tier", (r) => r.tier], ["Email", (r) => r.email],
    ["Company", (r) => r.company], ["Title", (r) => r.title], ["Owner", (r) => r.owner],
    ["Stage", (r) => r.stage], ["Intent", (r) => r.intent, true], ["Blocked", (r) => r.blocked],
  ], rows);
}

async function load() {
  try {
    const [rep, fc] = await Promise.all([api("/api/report"), api("/api/forecast")]);
    const total = fc.find((o) => o.owner === "TOTAL") || { weighted: 0, open_acv: 0 };
    $("kpis").replaceChildren(...[
      [rep.total, "leads"], [rep.avg_score, "avg score"],
      [money(total.open_acv), "open ACV"], [money(total.weighted), "weighted pipeline"],
    ].map(([v, label]) => {
      const d = document.createElement("div");
      d.className = "kpi";
      d.append(Object.assign(document.createElement("b"), { textContent: v }),
               Object.assign(document.createElement("span"), { textContent: label }));
      return d;
    }));
    const max = Math.max(1, ...rep.funnel.map((f) => f.count));
    table($("funnel"), [["Stage", (f) => f.stage], ["Count", (f) => f.count, true],
      ["Conv", (f) => f.conversion, true], ["", (f) => bar(f.count / max)]], rep.funnel);
    byTier = rep.by_tier;
    const tiers = Object.entries(rep.by_tier);
    table($("tiers"), [["Tier", (t) => t[0]], ["Leads", (t) => t[1], true],
      ["", (t) => bar(t[1] / Math.max(1, rep.total))]], tiers);
    table($("forecast"), [["Owner", (o) => o.owner], ["Leads", (o) => o.leads, true],
      ["Open ACV", (o) => money(o.open_acv), true], ["Weighted", (o) => money(o.weighted), true],
      ["Won", (o) => money(o.won), true]], fc);
    await loadLeads();
    $("status").textContent = `updated ${new Date().toLocaleTimeString()}`;
    $("auth").style.display = "none";
  } catch (e) {
    $("status").textContent = e.status !== 401 ? String(e) : token ? "API token rejected" : "API token required";
    if (e.status === 401) $("auth").style.display = "flex";
  }
}

$("auth").addEventListener("submit", (e) => {
  e.preventDefault();
  token = $("token").value.trim();
  sessionStorage.setItem("gtm-token", token);
  load();
});
$("tier").addEventListener("change", () => loadLeads().catch((e) => ($("status").textContent = String(e))));
load();
