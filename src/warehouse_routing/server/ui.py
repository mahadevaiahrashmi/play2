# agent-notes: { ctx: "standalone /ui route: SVG grid viewer for the warehouse environment", deps: [src/warehouse_routing/server/app.py], state: active, last: "sato@2026-04-14" }
"""Self-contained HTML + vanilla JS grid visualizer.

Mounted at ``/ui`` on the FastAPI app. No Gradio, no new deps — just a
``HTMLResponse`` that polls ``/state`` and calls ``/reset`` / ``/step``
via ``fetch``. The openenv default Gradio interface at ``/web`` is left
untouched.

Why a custom UI: the default Gradio interface renders Observations as
raw JSON. Warehouse-routing is a spatial task, so we render the grid
with robot, warehouse, SKUs (unvisited + visited), and obstacles.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>warehouse-routing — grid viewer</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {
    --bg: #0d1117;
    --panel: #161b22;
    --border: #30363d;
    --fg: #c9d1d9;
    --muted: #8b949e;
    --accent: #58a6ff;
    --good: #3fb950;
    --bad: #f85149;
    --warn: #d29922;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    background: var(--bg); color: var(--fg);
  }
  h1 { margin: 0 0 4px 0; font-size: 20px; }
  .sub { color: var(--muted); font-size: 12px; margin-bottom: 16px; }
  .wrap { display: grid; grid-template-columns: auto 320px; gap: 24px; align-items: start; }
  .panel {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }
  .grid-panel { padding: 12px; }
  svg { display: block; }
  .cell { stroke: var(--border); stroke-width: 1; }
  .empty     { fill: #0d1117; }
  .warehouse { fill: #1f6feb; }
  .sku       { fill: #d29922; }
  .visited   { fill: #3fb950; }
  .obstacle  { fill: #30363d; }
  .trail     { fill: #1f6feb; fill-opacity: 0.25; }
  .robot     { fill: #f85149; stroke: #fff; stroke-width: 1.5; }
  text.label { font-size: 10px; fill: #fff; text-anchor: middle; dominant-baseline: middle; pointer-events: none; }

  .row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
  .k { color: var(--muted); }
  .v { font-weight: 600; }
  .v.done-true  { color: var(--good); }
  .v.done-false { color: var(--warn); }

  .btns { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 12px; }
  button {
    background: #21262d; color: var(--fg); border: 1px solid var(--border);
    padding: 8px 0; border-radius: 6px; font: inherit; cursor: pointer;
  }
  button.primary { background: #238636; border-color: #2ea043; color: #fff; }
  button.reset   { background: #da3633; border-color: #f85149; color: #fff; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  .dpad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 10px; }
  .dpad button { padding: 10px 0; font-weight: 700; }
  .dpad .blank { visibility: hidden; }

  .legend { font-size: 11px; color: var(--muted); margin-top: 12px; line-height: 1.7; }
  .legend span.chip {
    display: inline-block; width: 10px; height: 10px; border-radius: 2px;
    vertical-align: middle; margin-right: 6px; border: 1px solid var(--border);
  }
  .status { font-size: 12px; color: var(--muted); margin-top: 8px; min-height: 14px; }
  .err { color: var(--bad); }
</style>
</head>
<body>
  <h1>warehouse-routing · grid viewer</h1>
  <div class="sub">
    OpenEnv FastAPI shim · polls <code>/state</code>, drives
    <code>/reset</code> + <code>/step</code>. Default Gradio UI still at
    <a href="/web" style="color:var(--accent)">/web</a>.
  </div>

  <div class="wrap">
    <div class="panel grid-panel">
      <svg id="grid" width="480" height="480"></svg>
    </div>

    <div class="panel">
      <div class="row"><span class="k">tier</span><span class="v" id="tier">—</span></div>
      <div class="row"><span class="k">seed / attempt</span><span class="v" id="seed">—</span></div>
      <div class="row"><span class="k">steps / budget</span><span class="v" id="steps">—</span></div>
      <div class="row"><span class="k">visited</span><span class="v" id="visited">—</span></div>
      <div class="row"><span class="k">last action</span><span class="v" id="last-action">—</span></div>
      <div class="row"><span class="k">last reward</span><span class="v" id="reward">—</span></div>
      <div class="row"><span class="k">cumulative reward</span><span class="v" id="cum-reward">—</span></div>
      <div class="row"><span class="k">done</span><span class="v" id="done">—</span></div>
      <div class="row"><span class="k">score (on done)</span><span class="v" id="score">—</span></div>
      <div class="row"><span class="k">episode id</span><span class="v" id="ep-id" style="font-size:10px">—</span></div>
      <div class="row"><span class="k">server step#</span><span class="v" id="ep-step">—</span></div>

      <div class="btns">
        <button class="primary" id="b-reset">Reset</button>
        <button id="b-poll">Refresh</button>
        <button id="b-auto">Auto: on</button>
      </div>

      <div class="dpad">
        <span class="blank"></span>
        <button data-move="N">N</button>
        <span class="blank"></span>
        <button data-move="W">W</button>
        <span class="blank"></span>
        <button data-move="E">E</button>
        <span class="blank"></span>
        <button data-move="S">S</button>
        <span class="blank"></span>
      </div>

      <div class="legend">
        <div><span class="chip" style="background:#1f6feb"></span>warehouse</div>
        <div><span class="chip" style="background:#d29922"></span>SKU (unvisited)</div>
        <div><span class="chip" style="background:#3fb950"></span>SKU (visited)</div>
        <div><span class="chip" style="background:#30363d"></span>obstacle</div>
        <div><span class="chip" style="background:#f85149"></span>robot</div>
        <div><span class="chip" style="background:#1f6feb;opacity:0.4"></span>breadcrumb trail</div>
      </div>

      <div class="status" id="status">ready.</div>
    </div>
  </div>

<script>
const svgEl = document.getElementById("grid");
const statusEl = document.getElementById("status");
let latest = null;          // last /reset or /step response (shape: {observation, reward, done, metadata})
let trail = [];             // robot positions since last reset
let cumReward = 0;
let lastAction = null;
let autoPoll = true;
let pollTimer = null;

function setStatus(msg, bad=false) {
  statusEl.textContent = msg;
  statusEl.className = "status" + (bad ? " err" : "");
}

function renderGrid(obs) {
  if (!obs) return;
  const rows = obs.grid_rows, cols = obs.grid_cols;
  const W = 480, H = 480;
  const cell = Math.floor(Math.min(W / cols, H / rows));
  const gw = cell * cols, gh = cell * rows;
  svgEl.setAttribute("width", gw);
  svgEl.setAttribute("height", gh);

  const blocked = new Set(obs.obstacles.map(c => c.row + "," + c.col));
  const skus = obs.sku_locations.map((c, i) => ({c, visited: obs.visited[i]}));
  const skuKey = new Map(skus.map(s => [s.c.row + "," + s.c.col, s]));
  const wh = obs.warehouse.row + "," + obs.warehouse.col;
  const robot = obs.robot_pos.row + "," + obs.robot_pos.col;
  const trailSet = new Set(trail.map(p => p.row + "," + p.col));

  let parts = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const key = r + "," + c;
      const x = c * cell, y = r * cell;
      let cls = "cell empty";
      let label = "";
      if (blocked.has(key))           cls = "cell obstacle";
      else if (key === wh)            { cls = "cell warehouse"; label = "W"; }
      else if (skuKey.has(key)) {
        const s = skuKey.get(key);
        cls = "cell " + (s.visited ? "visited" : "sku");
        label = s.visited ? "✓" : "•";
      } else if (trailSet.has(key))   cls = "cell trail";
      parts.push(`<rect class="${cls}" x="${x}" y="${y}" width="${cell}" height="${cell}"/>`);
      if (label) {
        parts.push(`<text class="label" x="${x + cell/2}" y="${y + cell/2}">${label}</text>`);
      }
    }
  }
  // robot on top
  const [rr, rc] = robot.split(",").map(Number);
  const cx = rc * cell + cell / 2, cy = rr * cell + cell / 2;
  parts.push(`<circle class="robot" cx="${cx}" cy="${cy}" r="${cell*0.32}"/>`);

  svgEl.innerHTML = parts.join("");
}

function renderPanel() {
  if (!latest) return;
  const obs = latest.observation || {};
  document.getElementById("tier").textContent = obs.tier ?? "—";
  document.getElementById("seed").textContent =
    (obs.variation_seed ?? "?") + " / " + (obs.attempt ?? "?");
  document.getElementById("steps").textContent =
    (obs.steps_taken ?? "?") + " / " + (obs.step_budget ?? "?");
  const visited = (obs.visited || []);
  const hit = visited.filter(Boolean).length;
  document.getElementById("visited").textContent = hit + " / " + visited.length;
  document.getElementById("last-action").textContent = lastAction ?? "—";
  const reward = latest.reward;
  document.getElementById("reward").textContent =
    (reward === null || reward === undefined) ? "—" : Number(reward).toFixed(2);
  document.getElementById("cum-reward").textContent = cumReward.toFixed(2);
  const done = !!latest.done;
  const doneEl = document.getElementById("done");
  doneEl.textContent = done ? "true" : "false";
  doneEl.className = "v done-" + done;
  const meta = latest.metadata || {};
  const score = meta.score;
  document.getElementById("score").textContent =
    (score === null || score === undefined) ? "—" : Number(score).toFixed(3);
}

async function refresh() {
  // /state returns {episode_id, step_count} only — NOT the observation.
  // Use it for session metadata; observation comes from /reset and /step.
  try {
    const r = await fetch("/state");
    if (!r.ok) { setStatus("/state " + r.status, true); return; }
    const s = await r.json();
    document.getElementById("ep-id").textContent = (s.episode_id || "—").slice(0, 8);
    document.getElementById("ep-step").textContent = s.step_count ?? "—";
    if (latest) {
      renderPanel();
      renderGrid(latest.observation);
    }
    setStatus("ok · " + new Date().toLocaleTimeString());
  } catch (e) {
    setStatus("fetch failed: " + e, true);
  }
}

async function doReset() {
  try {
    setStatus("resetting…");
    const r = await fetch("/reset", {method: "POST", headers: {"content-type": "application/json"}, body: "{}"});
    if (!r.ok) { setStatus("/reset " + r.status, true); return; }
    latest = await r.json();
    trail = [];
    cumReward = 0;
    lastAction = null;
    if (latest.observation && latest.observation.robot_pos) {
      trail.push({row: latest.observation.robot_pos.row, col: latest.observation.robot_pos.col});
    }
    renderPanel();
    renderGrid(latest.observation);
    refresh();
    setStatus("reset ok · tier=" + (latest.observation?.tier ?? "?"));
  } catch (e) { setStatus("reset failed: " + e, true); }
}

async function doStep(move) {
  if (!latest) { await doReset(); }
  if (latest && latest.done) { setStatus("episode done — reset first", true); return; }
  try {
    setStatus("step " + move + "…");
    const r = await fetch("/step", {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({action: {move: move}}),
    });
    if (!r.ok) { setStatus("/step " + r.status, true); return; }
    latest = await r.json();
    lastAction = move;
    if (typeof latest.reward === "number") cumReward += latest.reward;
    if (latest.observation && latest.observation.robot_pos) {
      trail.push({row: latest.observation.robot_pos.row, col: latest.observation.robot_pos.col});
    }
    renderPanel();
    renderGrid(latest.observation);
    refresh();
    setStatus("step " + move + " · reward=" + Number(latest.reward ?? 0).toFixed(2) +
              (latest.done ? " · DONE" : ""));
  } catch (e) { setStatus("step failed: " + e, true); }
}

function toggleAuto() {
  autoPoll = !autoPoll;
  document.getElementById("b-auto").textContent = "Auto: " + (autoPoll ? "on" : "off");
  schedulePoll();
}
function schedulePoll() {
  if (pollTimer) clearInterval(pollTimer);
  if (autoPoll) pollTimer = setInterval(refresh, 1000);
}

document.getElementById("b-reset").addEventListener("click", doReset);
document.getElementById("b-poll").addEventListener("click", refresh);
document.getElementById("b-auto").addEventListener("click", toggleAuto);
document.querySelectorAll(".dpad button[data-move]").forEach(b => {
  b.addEventListener("click", () => doStep(b.dataset.move));
});
document.addEventListener("keydown", (e) => {
  const map = {ArrowUp:"N", ArrowDown:"S", ArrowLeft:"W", ArrowRight:"E"};
  if (map[e.key]) { e.preventDefault(); doStep(map[e.key]); }
  if (e.key === "r" || e.key === "R") doReset();
});

// Auto-reset on first load so the grid appears immediately.
doReset().then(schedulePoll);
</script>
</body>
</html>
"""


def mount_ui(app: FastAPI) -> None:
    """Attach the ``/ui`` route to a FastAPI app."""

    @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    def ui() -> str:
        return _PAGE
