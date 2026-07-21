// Buster web UI. Vanilla JS, self-contained. Talks to the Core API + SSE.
const $ = (s, r = document) => r.querySelector(s);
const api = (p, opts) => fetch("/api" + p, opts).then(r => r.json());
const esc = s => String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// ---- theme / mode persistence ----
const root = document.documentElement;
function applyPrefs() {
  root.dataset.theme = localStorage.getItem("buster.theme") || "system";
  root.dataset.mode = localStorage.getItem("buster.mode") || "modern";
  $("#theme-select").value = root.dataset.theme;
  $("#mode-select").value = root.dataset.mode;
}
$("#theme-select").addEventListener("change", e => {
  localStorage.setItem("buster.theme", e.target.value); applyPrefs();
});
$("#mode-select").addEventListener("change", e => {
  localStorage.setItem("buster.mode", e.target.value); applyPrefs();
});

// ---- activity stream (SSE) ----
function startEvents() {
  const src = new EventSource("/api/events");
  const stream = $("#activity");
  src.onmessage = () => {};
  src.onerror = () => setStatus("warn", "reconnecting…");
  const handle = e => {
    let data = {}; try { data = JSON.parse(e.data); } catch (_) {}
    const div = document.createElement("div");
    div.className = "evt";
    div.innerHTML = `<div class="type">${esc(data.type || e.type)}</div>` +
      `<div>${esc(data.title || "")}</div>` +
      `<div class="t">${esc((data.timestamp || "").replace("T", " "))}</div>`;
    stream.prepend(div);
    while (stream.children.length > 100) stream.lastChild.remove();
  };
  ["assistant.status","task.created","task.started","task.completed","task.failed",
   "model.selected","context.loaded","research.started","research.source_found",
   "research.source_saved","research.report_updated","tool.started","tool.completed",
   "tool.failed","permission.requested","permission.approved","permission.denied",
   "action.started","action.verified","alert.created","service.discovered",
   "node.discovered","runtime.discovered","message.completed"].forEach(t => src.addEventListener(t, handle));
}

function setStatus(cls, text) {
  $("#status-dot").className = "dot " + cls;
  $("#status-text").textContent = text;
}

async function refreshStatus() {
  try {
    const s = await api("/status");
    const model = (s.models[0] && s.models[0].name) || "no model";
    setStatus("ok", `${model} · ${s.trusted_nodes} node(s)`);
  } catch (_) { setStatus("crit", "offline"); }
}

// ---- section rendering ----
const sections = {
  chat: renderChat,
  research: renderResearch,
  reports: renderReports,
  system: () => renderChecks("system", "/system/check"),
  network: () => renderChecks("network", "/network/check"),
  actions: renderActions,
  alerts: renderAlerts,
  memory: renderMemory,
  nodes: renderNodes,
  agents: renderAgents,
  tools: renderTools,
  prompts: renderPrompts,
  settings: renderSettings,
};

async function load(section) {
  $("#section-title").textContent = section[0].toUpperCase() + section.slice(1);
  const panel = $("#panel");
  panel.innerHTML = `<div class="muted">Loading…</div>`;
  try { await (sections[section] || renderChat)(panel); }
  catch (e) { panel.innerHTML = `<div class="card crit">Error: ${esc(e.message)}</div>`; }
}

// ---- chat ----
let conversationId = null;
async function renderChat(panel) {
  panel.innerHTML = `
    <div class="chat-log" id="chat-log"></div>
    <div class="composer">
      <textarea id="chat-input" class="input" placeholder="Ask Buster…"></textarea>
      <button id="chat-send">Send</button>
    </div>`;
  const log = $("#chat-log"), input = $("#chat-input");
  const send = async () => {
    const text = input.value.trim(); if (!text) return;
    input.value = "";
    log.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(text)}</div>`);
    const thinking = document.createElement("div");
    thinking.className = "msg assistant"; thinking.textContent = "…";
    log.appendChild(thinking); log.scrollTop = log.scrollHeight;
    try {
      const r = await api("/ask", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: text, conversation_id: conversationId }) });
      thinking.innerHTML = esc(r.content) +
        `<div class="meta">${esc(r.model)} · ${esc(r.inference_location)} · ` +
        `data left machine: ${r.external_data_shared ? "yes" : "no"}${r.tools_used.length ? " · tools: " + esc(r.tools_used.join(", ")) : ""}</div>`;
    } catch (e) { thinking.textContent = "Error: " + e.message; }
    log.scrollTop = log.scrollHeight;
  };
  $("#chat-send").onclick = send;
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
}

// ---- research ----
async function renderResearch(panel) {
  const data = await api("/research");
  panel.innerHTML = `
    <div class="card">
      <h3>New research</h3>
      <div class="composer">
        <input type="text" id="rq" placeholder="Research question…">
        <button id="rgo">Research</button>
      </div>
    </div>
    <div class="card"><h3>Projects</h3><div id="rlist"></div></div>`;
  const list = $("#rlist");
  list.innerHTML = data.projects.length ? data.projects.map(p =>
    `<div class="row"><span class="pill">${esc(p.status)}</span> ${esc(p.question)}</div>`).join("") :
    `<div class="muted">No research projects yet.</div>`;
  $("#rgo").onclick = async () => {
    const q = $("#rq").value.trim(); if (!q) return;
    $("#rgo").textContent = "Researching…"; $("#rgo").disabled = true;
    try {
      const r = await api("/research", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }) });
      alert(`Report created: ${r.title} (${r.sources} sources)`);
      load("research");
    } catch (e) { alert("Error: " + e.message); }
  };
}

// ---- reports ----
async function renderReports(panel) {
  const data = await api("/reports");
  panel.innerHTML = `<div class="card"><h3>Reports</h3><div id="rl"></div></div>
    <div class="card" id="rview" style="display:none"></div>`;
  $("#rl").innerHTML = data.reports.length ? `<table><tr><th>Title</th><th>Updated</th><th>v</th></tr>` +
    data.reports.map(r => `<tr><td><a href="#" data-id="${r.id}">${esc(r.title)}</a></td>` +
      `<td class="muted">${esc((r.updated_at||"").replace("T"," "))}</td><td>${r.version}</td></tr>`).join("") + `</table>` :
    `<div class="muted">No reports yet.</div>`;
  panel.querySelectorAll("a[data-id]").forEach(a => a.onclick = async e => {
    e.preventDefault();
    const r = await api("/reports/" + a.dataset.id);
    const v = $("#rview"); v.style.display = "block";
    v.innerHTML = `<pre style="white-space:pre-wrap">${esc(r.markdown)}</pre>`;
  });
}

// ---- diagnostics ----
async function renderChecks(_name, path) {
  const panel = $("#panel");
  const data = await api(path);
  panel.innerHTML = `<div class="card"><button id="rerun">Run check</button></div>` +
    data.checks.map(c => `<div class="card"><span class="pill ${c.status}">${esc(c.status)}</span>
      <strong> ${esc(c.check)}</strong><div>${esc(c.summary)}</div>` +
      (c.recommendations && c.recommendations.length ?
        `<ul class="muted">${c.recommendations.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "") +
      `</div>`).join("");
  $("#rerun").onclick = () => renderChecks(_name, path);
}

// ---- actions ----
async function renderActions(panel) {
  const data = await api("/actions");
  panel.innerHTML = `<div class="card"><h3>Propose a safe action</h3>
    <div class="row">
      <button data-k="clear_buster_cache" class="secondary">Clear Buster cache (L1)</button>
      <button data-k="restart_buster" class="secondary">Restart Buster (L1)</button>
      <button data-k="restart_ollama" class="secondary">Restart Ollama (L2)</button>
    </div><div id="apreview"></div></div>
    <div class="card"><h3>History</h3>${data.actions.length ?
      `<table><tr><th>Title</th><th>Risk</th><th>Status</th></tr>` +
      data.actions.map(a => `<tr><td>${esc(a.title)}</td><td>${a.risk_level}</td><td>${esc(a.status)}</td></tr>`).join("") + `</table>` :
      `<div class="muted">No actions yet.</div>`}</div>`;
  panel.querySelectorAll("button[data-k]").forEach(b => b.onclick = async () => {
    const r = await api("/actions/propose", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ catalog_key: b.dataset.k }) });
    const pv = $("#apreview");
    pv.innerHTML = `<pre style="white-space:pre-wrap">${esc(r.preview)}</pre>
      <button id="approve">Approve & run</button> <button class="secondary" id="deny">Deny</button>`;
    $("#approve").onclick = async () => {
      const res = await api("/actions/" + r.action.id + "/approve", { method: "POST" });
      pv.innerHTML = `<div class="pill ${res.ok ? "ok" : "crit"}">${res.ok ? "verified" : "failed"}</div>
        <pre style="white-space:pre-wrap">${esc(JSON.stringify(res, null, 2))}</pre>`;
      renderActions($("#panel"));
    };
    $("#deny").onclick = () => { pv.innerHTML = `<div class="muted">Denied.</div>`; };
  });
}

// ---- alerts ----
async function renderAlerts(panel) {
  const data = await api("/alerts");
  panel.innerHTML = `<div class="card"><h3>Alerts</h3>${data.alerts.length ?
    data.alerts.map(a => `<div class="row"><span class="pill ${a.severity === "critical" ? "crit" : "warn"}">${esc(a.severity)}</span>
      <strong>${esc(a.title)}</strong> <span class="muted">${esc(a.detail)}</span>
      <button class="secondary" data-id="${a.id}">Ack</button></div>`).join("") :
    `<div class="muted">No open alerts. 🎉</div>`}</div>`;
  panel.querySelectorAll("button[data-id]").forEach(b => b.onclick = async () => {
    await api("/alerts/" + b.dataset.id + "/ack", { method: "POST" }); renderAlerts($("#panel"));
  });
}

// ---- memory ----
async function renderMemory(panel) {
  panel.innerHTML = `<div class="card"><div class="composer">
    <input type="text" id="mq" placeholder="Search memory…"><button id="mgo">Search</button></div>
    <div id="mres"></div></div>`;
  const run = async () => {
    const q = $("#mq").value.trim(); if (!q) return;
    const r = await api("/memory/search?q=" + encodeURIComponent(q));
    $("#mres").innerHTML = r.hits.length ? r.hits.map(h =>
      `<div class="card"><div class="muted">${esc(h.heading_path || h.path)}</div>${esc(h.text)}</div>`).join("") :
      `<div class="muted">No matches.</div>`;
  };
  $("#mgo").onclick = run;
  $("#mq").addEventListener("keydown", e => { if (e.key === "Enter") run(); });
}

// ---- nodes / services / network graph ----
async function renderNodes(panel) {
  const [nodes, services, graph] = await Promise.all([api("/nodes"), api("/services"), api("/network/graph")]);
  panel.innerHTML = `
    <div class="card"><h3>Network</h3>
      <svg id="graph" viewBox="0 0 600 300" style="width:100%;height:280px"></svg></div>
    <div class="card"><h3>Buster nodes</h3>${tableTrust(nodes.nodes, "nodes")}</div>
    <div class="card"><h3>Services</h3>${tableTrust(services.services, "services")}</div>`;
  drawGraph(graph);
  wireTrust(panel);
}
function tableTrust(items, kind) {
  if (!items.length) return `<div class="muted">None discovered.</div>`;
  return `<table><tr><th>Name</th><th>Trust</th><th></th></tr>` + items.map(n =>
    `<tr><td>${esc(n.name)}</td><td><span class="pill">${esc(n.trust)}</span></td>
     <td><button class="secondary" data-kind="${kind}" data-id="${esc(n.id)}" data-trust="trusted">Trust</button>
     <button class="secondary" data-kind="${kind}" data-id="${esc(n.id)}" data-trust="ignored">Ignore</button></td></tr>`).join("") + `</table>`;
}
function wireTrust(panel) {
  panel.querySelectorAll("button[data-kind]").forEach(b => b.onclick = async () => {
    await api(`/${b.dataset.kind}/${b.dataset.id}/trust`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ trust: b.dataset.trust }) });
    renderNodes($("#panel"));
  });
}
function drawGraph(graph) {
  const svg = $("#graph"); if (!svg) return;
  const cx = 300, cy = 150, R = 110;
  const others = graph.nodes.filter(n => !n.self);
  let html = "";
  others.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(others.length, 1);
    const x = cx + R * Math.cos(a), y = cy + R * Math.sin(a);
    n._x = x; n._y = y;
    html += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--border)" stroke-width="2"/>`;
  });
  const nodeSvg = n => `<g><circle cx="${n._x || cx}" cy="${n._y || cy}" r="22"
     fill="${n.self ? "var(--accent)" : "var(--surface-2)"}" stroke="var(--border)"/>
     <text x="${n._x || cx}" y="${(n._y || cy) + 38}" text-anchor="middle" font-size="10"
     fill="var(--text)">${esc((n.label || "").slice(0, 16))}</text></g>`;
  html += others.map(nodeSvg).join("") + nodeSvg(graph.nodes.find(n => n.self) || { self: true, label: "Buster" });
  svg.innerHTML = html;
}

// ---- agents (runtimes) ----
async function renderAgents(panel) {
  const data = await api("/runtimes");
  panel.innerHTML = `<div class="card"><h3>Agent runtimes</h3><div class="grid">` +
    data.runtimes.map(r => `<div class="card">
      <strong>${esc(r.name)}</strong> <span class="pill">${esc(r.status)}</span>
      <div class="muted">type: ${esc(r.runtime_type)} · via ${esc(r.detected_via)}</div>
      <div class="muted">caps: ${esc((r.capabilities || []).join(", ") || "—")}</div>
      <div class="muted">task submission: ${r.task_submission_enabled ? "enabled" : "disabled"}</div>
    </div>`).join("") + `</div></div>`;
}

// ---- tools ----
async function renderTools(panel) {
  const data = await api("/tools");
  const byPack = {};
  data.tools.forEach(t => (byPack[t.pack] = byPack[t.pack] || []).push(t));
  panel.innerHTML = Object.entries(byPack).map(([pack, tools]) =>
    `<div class="card"><h3>${esc(pack)}</h3><table><tr><th>Tool</th><th>Risk</th><th>Desc</th></tr>` +
    tools.map(t => `<tr><td><code>${esc(t.id)}</code></td><td>${t.risk_level}</td><td>${esc(t.description)}</td></tr>`).join("") +
    `</table></div>`).join("");
}

// ---- prompts ----
async function renderPrompts(panel) {
  const data = await api("/prompts");
  panel.innerHTML = `<div class="card"><h3>Prompt library</h3>${data.prompts.length ?
    `<table><tr><th>Title</th><th>Visibility</th><th>Tags</th></tr>` +
    data.prompts.map(p => `<tr><td>${esc(p.title)}</td><td>${esc(p.visibility)}</td><td>${esc((p.tags||[]).join(", "))}</td></tr>`).join("") + `</table>` :
    `<div class="muted">No prompt records yet.</div>`}</div>`;
}

// ---- settings ----
async function renderSettings(panel) {
  const [cfg, pers] = await Promise.all([api("/config"), api("/personality")]);
  panel.innerHTML = `
    <div class="card"><h3>Personality</h3>
      <select id="prof">${Object.keys(pers.profiles).map(p =>
        `<option value="${p}" ${p === pers.profile ? "selected" : ""}>${p}</option>`).join("")}</select>
      <button id="savep">Save</button></div>
    <div class="card"><h3>Configuration</h3>
      <pre style="white-space:pre-wrap">${esc(JSON.stringify(cfg, null, 2))}</pre></div>`;
  $("#savep").onclick = async () => {
    await api("/personality", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: $("#prof").value }) });
    refreshStatus();
  };
}

// ---- nav wiring (SPA-ish; keep server routes working too) ----
document.querySelectorAll(".nav-item").forEach(a => a.addEventListener("click", e => {
  e.preventDefault();
  document.querySelectorAll(".nav-item").forEach(x => x.classList.remove("active"));
  a.classList.add("active");
  history.pushState({}, "", "/ui/" + a.dataset.section);
  load(a.dataset.section);
}));

applyPrefs();
startEvents();
refreshStatus();
setInterval(refreshStatus, 15000);
load(window.__ACTIVE__ || "chat");
