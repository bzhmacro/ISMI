/* Inflation Shock Momentum — interactive explorer (zero-build, static).

   Since schema v3 the heavy modelling runs CLIENT-SIDE: data/ism.json ships the
   raw category inflation + weight panels, and a Web Worker (worker.js, running
   engine.js — a parity-tested port of src/ism/engine.py) recomputes the index
   whenever a control changes. Residual panels are cached in the worker keyed by
   (backbone, AR order, window W), so only AR/W changes pay for regressions —
   everything else (k, scheme, ρ̂ cap, category exclusions) re-aggregates in
   milliseconds.

   The JSON also carries ONE precomputed baseline combo (AR1|k3|extensive) so
   the page paints instantly before the worker is warm. If the worker cannot
   start (e.g. file:// or a legacy v2 ism.json), the app degrades to whatever
   precomputed combos exist in the file. */

const STATE = { backbone: "pce", ar: 1, W: 120, k: 3, scheme: "extensive", rhoCap: 0.9,
                startIdx: 0, author: true, components: false, headline: true, selectedDate: null };

let DATA = null;
let X = [];                 // Date objects for the x-axis of the active backbone
let WORKER = null, WORKER_READY = false, LIVE_BACKBONES = new Set();
let REQ = 0, REQ_KEY = "", RESULT = null;     // latest worker result
let DEB = null;             // debounce timer for compute requests
const EXCLUDED = {};        // backbone -> Set of excluded category indices

const PLOT_BG = "#171e26", GRID = "#243240", INK = "#e6edf3", MUTED = "#8b98a5";
const POS = "#f5a623", NEG = "#4c9aff";
const HEADLINE_COLOR = { pce: "#d05ce3", cpi: "#2dd4bf" };

const $ = id => document.getElementById(id);

init();

async function init() {
  try {
    const res = await fetch("data/ism.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    DATA = await res.json();
  } catch (e) {
    $("chart").innerHTML =
      `<div style="padding:24px;color:#f0d28a">Could not load <code>data/ism.json</code>.
       Run <code>python scripts/export_web_data.py</code> to generate it, then redeploy. (${e})</div>`;
    return;
  }

  STATE.backbone = (DATA.meta && DATA.meta.default_backbone) || "pce";
  const u = ui();
  STATE.W = u.window.default;
  STATE.k = u.k.default;
  STATE.rhoCap = u.rho_cap.default;

  const asof = (DATA.meta.generated_utc || "").slice(0, 10);
  const b = backbone();
  const lastMonth = b.dates[b.dates.length - 1];
  $("asof").textContent =
    `● Data through ${lastMonth} · generated ${asof} · index recomputed live in your browser`;

  if ((b.note || DATA.meta.note || "").toUpperCase().includes("DEMO")) {
    const ban = $("demo-banner");
    ban.hidden = false;
    ban.textContent = "⚠ Showing DEMO synthetic data. Run scripts/export_web_data.py on real data to replace it.";
  }

  setupWorker();
  buildBackboneSegment();
  setupToggles();
  setupSliders();
  setupCatButtons();
  applyBackbone();          // builds param controls + category list, sets X/range
  setupDownload();
  requestCompute(0);
}

/* ------------------------------- helpers -------------------------------- */
function backbone() {
  if (DATA.backbones) return DATA.backbones[STATE.backbone];
  return {                                   // legacy flat ism.json (v1)
    label: "PCE",
    source_note: "BEA Underlying Detail",
    weight_note: "monthly nominal PCE shares (BEA 2.4.5U)",
    dates: DATA.dates,
    categories: DATA.categories,
    author: DATA.author,
    combos: DATA.combos,
    drivers: DATA.drivers,
    n_categories: DATA.meta.n_categories,
    note: DATA.meta.note || "",
    headline: { label: "PCE inflation (12m, %)", series: DATA.pce_yoy },
  };
}

function ui() {
  const m = (DATA.meta && DATA.meta.ui) || {};
  return {
    ar_orders: m.ar_orders || (DATA.meta && DATA.meta.ar_orders) || [1, 3, 12],
    window: m.window || { min: 60, max: 240, step: 6, default: 120 },
    k: m.k || { min: 2, max: 8, default: 3 },
    schemes: m.schemes || (DATA.meta && DATA.meta.schemes) || ["extensive"],
    rho_cap: m.rho_cap || { min: 0.5, max: 0.99, step: 0.01, default: 0.9 },
  };
}

function exSet() {
  if (!EXCLUDED[STATE.backbone]) EXCLUDED[STATE.backbone] = new Set();
  return EXCLUDED[STATE.backbone];
}

function baseKey() { return (DATA.meta && DATA.meta.baseline) || "AR1|k3|extensive"; }

/* live = this backbone ships raw panels AND the worker is up (or booting) */
function liveUI() { return !!(WORKER && backbone().panel); }
function liveReady() { return !!(WORKER && WORKER_READY && LIVE_BACKBONES.has(STATE.backbone)); }

function paramsKey() {
  const ex = [...exSet()].sort((a, b) => a - b).join(".");
  const rc = STATE.scheme === "stickiness" ? STATE.rhoCap : "-";
  return `${STATE.backbone}|AR${STATE.ar}|W${STATE.W}|k${STATE.k}|${STATE.scheme}|rc${rc}|x${ex}`;
}

/* do the current params coincide with a precomputed combo in the JSON? */
function precomputedFor(params) {
  const b = backbone();
  if (!b.combos) return null;
  const u = ui();
  if (STATE.W !== u.window.default || exSet().size ||
      (STATE.scheme === "stickiness" && STATE.rhoCap !== 0.9)) return null;
  const key = `AR${STATE.ar}|k${STATE.k}|${STATE.scheme}`;
  const c = b.combos[key];
  if (!c) return null;
  return { key: "precomputed", backbone: STATE.backbone,
           ISM: c.ISM, S_pos: c.S_pos, S_neg: c.S_neg,
           driversEntry: b.drivers ? b.drivers[key] : null };
}

/* Pick what to display NOW: fresh worker result > matching precomputed combo
   > stale-but-right-backbone fallback (a fresh compute is already on its way). */
function currentResult() {
  const pre = precomputedFor();
  if (RESULT && RESULT.backbone === STATE.backbone && RESULT.key === paramsKey())
    return { res: RESULT, fresh: true };
  if (pre) return { res: pre, fresh: true };
  if (RESULT && RESULT.backbone === STATE.backbone) return { res: RESULT, fresh: false };
  const b = backbone();
  const first = b.combos && Object.keys(b.combos)[0];
  if (first) {
    const c = b.combos[first];
    return { res: { key: "fallback", backbone: STATE.backbone, ISM: c.ISM, S_pos: c.S_pos,
                    S_neg: c.S_neg, driversEntry: b.drivers ? b.drivers[first] : null },
             fresh: false };
  }
  return { res: null, fresh: false };
}

function setStatus(text, warn) {
  const el = $("status");
  el.textContent = text || "";
  el.classList.toggle("warn", !!warn);
}

/* ------------------------------ web worker ------------------------------ */
function setupWorker() {
  if (typeof Worker === "undefined" || !DATA.backbones) return;
  const panels = {};
  for (const [name, b] of Object.entries(DATA.backbones)) if (b.panel) panels[name] = b.panel;
  if (!Object.keys(panels).length) return;
  try { WORKER = new Worker("worker.js"); } catch (e) { WORKER = null; return; }

  WORKER.onerror = () => {
    WORKER = null; WORKER_READY = false;
    setStatus("live compute unavailable — showing the precomputed baseline", true);
    buildParamControls(); updateModeUI(); render();
  };
  WORKER.onmessage = e => {
    const m = e.data;
    if (m.type === "ready") {
      WORKER_READY = true;
      LIVE_BACKBONES = new Set(m.backbones);
      updateModeUI();
      requestCompute(0);
      return;
    }
    if (m.type === "error") { setStatus(`compute error: ${m.message}`, true); return; }
    if (m.type === "result") {
      if (m.id !== REQ) return;                       // superseded request
      RESULT = { key: REQ_KEY, backbone: m.backbone, ISM: m.ISM, S_pos: m.S_pos,
                 S_neg: m.S_neg, driversEntry: workerDrivers(m), ms: m.ms };
      setStatus(`computed in your browser · ${m.ms} ms`);
      render();
    }
  };
  WORKER.postMessage({ type: "init", panels });
}

function workerDrivers(m) {
  const dates = DATA.backbones[m.backbone].dates;
  const history = m.drivers.map(d => ({ date: dates[d.t], contrib: d.contrib }));
  const last = history[history.length - 1] || { date: null, contrib: [] };
  return { date: last.date, contrib: last.contrib, history };
}

function requestCompute(delay = 150) {
  if (!liveReady()) { render(); return; }
  const key = paramsKey();
  if (RESULT && RESULT.backbone === STATE.backbone && RESULT.key === key) { render(); return; }
  if (precomputedFor()) { render(); }                 // instant paint while computing
  clearTimeout(DEB);
  DEB = setTimeout(() => {
    REQ += 1;
    REQ_KEY = paramsKey();
    WORKER.postMessage({
      type: "compute", id: REQ, backbone: STATE.backbone,
      params: { ar: STATE.ar, W: STATE.W, k: STATE.k, scheme: STATE.scheme,
                rhoCap: STATE.rhoCap, excluded: [...exSet()] },
    });
    setStatus("computing…");
  }, delay);
  render();
}

/* ------------------------------- controls ------------------------------- */
function buildBackboneSegment() {
  const host = $("backbone");
  if (!host) return;
  const names = (DATA.meta && DATA.meta.backbones) || ["pce"];
  if (names.length < 2) { host.closest(".control").hidden = true; return; }
  const label = n => (DATA.backbones && DATA.backbones[n] && DATA.backbones[n].label) || n.toUpperCase();
  segment("backbone", names, STATE.backbone, label, n => {
    STATE.backbone = n;
    STATE.selectedDate = null;
    applyBackbone();
    requestCompute(0);
  });
}

/* AR / k / scheme options depend on the mode: live -> full ranges from meta.ui;
   legacy -> whatever combos exist in the JSON. */
function legacyOptions() {
  const keys = Object.keys(backbone().combos || {});
  const num = (re, k) => { const m = k.match(re); return m ? +m[1] : null; };
  return {
    ars: [...new Set(keys.map(k => num(/^AR(\d+)/, k)).filter(v => v != null))].sort((a, b) => a - b),
    ks: [...new Set(keys.map(k => num(/\|k(\d+)\|/, k)).filter(v => v != null))].sort((a, b) => a - b),
    schemes: [...new Set(keys.map(k => k.split("|")[2]).filter(Boolean))],
  };
}

function buildParamControls() {
  const live = liveUI();
  const u = ui();
  const opts = live ? { ars: u.ar_orders, ks: null, schemes: u.schemes } : legacyOptions();

  if (!opts.ars.includes(STATE.ar)) STATE.ar = opts.ars[0];
  segment("ar", opts.ars, STATE.ar, v => `AR(${v})`,
          v => { STATE.ar = v; STATE.selectedDate = null; requestCompute(0); });

  if (!opts.schemes.includes(STATE.scheme)) STATE.scheme = opts.schemes[0];
  segment("scheme", opts.schemes, STATE.scheme, v => v, v => {
    STATE.scheme = v; STATE.selectedDate = null;
    $("rho-ctl").hidden = !(liveUI() && v === "stickiness");
    requestCompute(0);
  });

  if (!live) {
    const ks = opts.ks.length ? opts.ks : [STATE.k];
    if (!ks.includes(STATE.k)) STATE.k = ks[0];
    segment("k", ks, STATE.k, v => `k=${v}`,
            v => { STATE.k = v; STATE.selectedDate = null; requestCompute(0); });
  }
  $("k-label").textContent = STATE.k;
  updateModeUI();
}

function updateModeUI() {
  const live = liveUI();
  $("W-ctl").hidden = !live;
  $("k-slider").hidden = !live;
  $("k").hidden = live;
  $("rho-ctl").hidden = !(live && STATE.scheme === "stickiness");
  $("cats-ctl").hidden = !live;
  if (!live && WORKER === null && backbone().panel === undefined)
    setStatus("this data file has no raw panels — showing precomputed combos only", true);
}

function segment(id, values, current, label, onPick) {
  const host = $(id);
  host.innerHTML = "";
  values.forEach(v => {
    const btn = document.createElement("button");
    btn.textContent = label(v);
    btn.setAttribute("aria-pressed", String(v === current));
    btn.onclick = () => {
      [...host.children].forEach(c => c.setAttribute("aria-pressed", "false"));
      btn.setAttribute("aria-pressed", "true");
      onPick(v);
    };
    host.appendChild(btn);
  });
}

function setupSliders() {
  const u = ui();
  const W = $("W");
  W.min = u.window.min; W.max = u.window.max; W.step = u.window.step; W.value = STATE.W;
  $("W-label").textContent = STATE.W;
  W.oninput = () => {
    STATE.W = +W.value;
    $("W-label").textContent = STATE.W;
    STATE.selectedDate = null;
    requestCompute(180);
  };

  const K = $("k-slider");
  K.min = u.k.min; K.max = u.k.max; K.value = STATE.k;
  $("k-label").textContent = STATE.k;
  K.oninput = () => {
    STATE.k = +K.value;
    $("k-label").textContent = STATE.k;
    STATE.selectedDate = null;
    requestCompute(120);
  };

  const R = $("rho");
  R.min = u.rho_cap.min; R.max = u.rho_cap.max; R.step = u.rho_cap.step; R.value = STATE.rhoCap;
  $("rho-label").textContent = STATE.rhoCap.toFixed(2);
  R.oninput = () => {
    STATE.rhoCap = +R.value;
    $("rho-label").textContent = STATE.rhoCap.toFixed(2);
    requestCompute(120);
  };
}

function setupToggles() {
  const map = { "t-author": "author", "t-components": "components", "t-pce": "headline" };
  for (const [id, key] of Object.entries(map)) {
    const el = $(id);
    el.checked = STATE[key];
    el.onchange = () => { STATE[key] = el.checked; render(); };
  }
}

/* --------------------------- category exclusion -------------------------- */
function buildCatList() {
  const b = backbone();
  const host = $("catlist");
  host.innerHTML = "";
  if (!b.categories) { updateCatSummary(); return; }
  const ex = exSet();
  b.categories.forEach((c, i) => {
    const row = document.createElement("label");
    row.className = "catrow";
    row.title = c.label;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !ex.has(i);
    cb.dataset.idx = i;
    cb.onchange = () => {
      if (cb.checked) ex.delete(i); else ex.add(i);
      updateCatSummary();
      requestCompute(250);
    };
    const span = document.createElement("span");
    span.textContent = c.label;
    row.appendChild(cb);
    row.appendChild(span);
    host.appendChild(row);
  });
  const search = $("cat-search");
  search.value = "";
  search.oninput = () => {
    const q = search.value.trim().toLowerCase();
    [...host.children].forEach(row =>
      row.classList.toggle("hidden", q !== "" && !row.title.toLowerCase().includes(q)));
  };
  updateCatSummary();
}

function updateCatSummary() {
  const b = backbone();
  const total = b.categories ? b.categories.length : 0;
  const inc = total - exSet().size;
  $("cat-summary").textContent = total ? `${inc}/${total} included` : "";
}

function setupCatButtons() {
  $("cat-all").onclick = () => {
    exSet().clear();
    [...$("catlist").querySelectorAll("input")].forEach(cb => { cb.checked = true; });
    updateCatSummary();
    requestCompute(150);
  };
  $("cat-none").onclick = () => {       // exclude only the rows visible under the filter
    const ex = exSet();
    [...$("catlist").children].forEach(row => {
      if (row.classList.contains("hidden")) return;
      const cb = row.querySelector("input");
      cb.checked = false;
      ex.add(+cb.dataset.idx);
    });
    updateCatSummary();
    requestCompute(150);
  };
}

/* ----------------------- backbone switch / re-point ---------------------- */
function applyBackbone() {
  const b = backbone();
  X = b.dates.map(d => new Date(d + "-01"));

  const authEl = $("t-author");
  const hasAuthor = !!b.author;
  authEl.disabled = !hasAuthor;
  const authLabel = authEl.closest(".chk");
  if (authLabel) {
    authLabel.style.opacity = hasAuthor ? "" : ".4";
    authLabel.title = hasAuthor ? "" : `No author series for the ${b.label} backbone`;
  }
  if (!hasAuthor) authEl.checked = false;
  STATE.author = authEl.checked;

  const span = $("t-headline-text");
  if (span) span.textContent = shortHeadlineLabel(b);

  // Range slider: default to the first month with a computed baseline index.
  const r = $("start");
  r.min = 0; r.max = b.dates.length - 1;
  const base = (b.combos && (b.combos[baseKey()] || Object.values(b.combos)[0])) || null;
  let first = base ? base.ISM.findIndex(v => v != null) : 0;
  if (first < 0) first = 0;
  STATE.startIdx = first; r.value = first;
  r.oninput = () => { STATE.startIdx = +r.value; render(); };

  const lastMonth = b.dates[b.dates.length - 1];
  $("meta").textContent = `${b.n_categories} categories · ${b.dates[0]}–${lastMonth}`;
  const cnt = $("cat-count");
  if (cnt) cnt.textContent =
    STATE.backbone === "cpi" ? "~70 BLS CPI item strata" : "~130 disaggregated PCE categories";
  const foot = $("foot-source");
  if (foot) foot.textContent = backboneFooter(b);
  const wnote = $("weight-note");
  if (wnote) wnote.textContent = b.weight_note || "";

  buildParamControls();
  buildCatList();
}

function shortHeadlineLabel(b) {
  return STATE.backbone === "cpi" ? "CPI inflation (12m)" : "PCE inflation (12m)";
}

function backboneFooter(b) {
  if (STATE.backbone === "cpi") {
    return "CPI backbone: BLS CPI-U item strata (CUUR0000*, NSA); weights = Dec-2023 relative importance, renormalised monthly. No author overlay (the paper uses PCE).";
  }
  return "PCE backbone: BEA Underlying Detail + FRED. Baseline index correlates ~0.99 with the authors' series.";
}

function sliceFrom(arr) { return arr ? arr.slice(STATE.startIdx) : []; }

function pearson(a, b) {
  const xs = [], ys = [];
  for (let i = 0; i < a.length; i++) {
    if (a[i] == null || b[i] == null) continue;
    xs.push(a[i]); ys.push(b[i]);
  }
  const n = xs.length; if (n < 3) return NaN;
  const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i]-mx, dy = ys[i]-my; sxy += dx*dy; sxx += dx*dx; syy += dy*dy; }
  return sxy / Math.sqrt(sxx * syy);
}

/* -------------------------------- render -------------------------------- */
function render() {
  const b = backbone();
  $("start-label").textContent = b.dates[STATE.startIdx];
  const { res, fresh } = currentResult();
  if (!res) return;
  if (!fresh && liveReady()) setStatus("computing…");

  const x = sliceFrom(X);
  const ism = sliceFrom(res.ISM);
  const headSeries = b.headline ? b.headline.series : null;
  const headColor = HEADLINE_COLOR[STATE.backbone] || "#d05ce3";

  const traces = [];
  traces.push({ x, y: ism, name: `ISM (${b.label})`, type: "scatter", mode: "lines",
                line: { color: NEG, width: 1.8 }, yaxis: "y" });
  if (STATE.author && b.author) {
    traces.push({ x, y: sliceFrom(b.author.ISM), name: "ISM (author)", type: "scatter",
                  mode: "lines", line: { color: INK, width: 1.2, dash: "dot" }, yaxis: "y" });
  }
  if (STATE.components) {
    traces.push({ x, y: sliceFrom(res.S_pos), name: "S⁺ positive", type: "scatter", mode: "lines",
                  line: { color: POS, width: 1 }, yaxis: "y" });
    traces.push({ x, y: sliceFrom(res.S_neg), name: "S⁻ negative", type: "scatter", mode: "lines",
                  line: { color: "#3fb950", width: 1 }, yaxis: "y" });
  }
  if (STATE.headline && headSeries) {
    traces.push({ x, y: sliceFrom(headSeries), name: shortHeadlineLabel(b), type: "scatter",
                  mode: "lines", line: { color: headColor, width: 1 }, yaxis: "y2" });
  }

  const layout = {
    paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
    margin: { l: 50, r: 55, t: 10, b: 36 },
    legend: { orientation: "h", y: 1.12, font: { size: 11 } },
    xaxis: { gridcolor: GRID, zeroline: false },
    yaxis: { title: "ISM index", gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
    yaxis2: { title: shortHeadlineLabel(b) + ", %", overlaying: "y", side: "right", showgrid: false },
    shapes: [{ type: "line", x0: x[0], x1: x[x.length-1], y0: 0, y1: 0, yref: "y",
               line: { color: "#3a4b5c", width: 1 } }],
  };
  Plotly.react("chart", traces, layout, { responsive: true, displayModeBar: false });

  renderReadout(res);
  renderRecentBars(res);
  renderDrivers(res);
}

function renderReadout(res) {
  const b = backbone();
  const ism = sliceFrom(res.ISM);
  const corr = b.author ? pearson(ism, sliceFrom(b.author.ISM)) : NaN;
  const latest = [...res.ISM].reverse().find(v => v != null);
  const exN = exSet().size;
  const spec = `${b.label} · AR(${STATE.ar}) · W=${STATE.W} · k=${STATE.k} · ${STATE.scheme}` +
               (STATE.scheme === "stickiness" ? ` (ρ̂≤${STATE.rhoCap.toFixed(2)})` : "") +
               (exN ? ` · −${exN} cats` : "");
  const stats = [
    ["Correlation w/ author", isNaN(corr) ? "—" : corr.toFixed(3)],
    ["Latest ISM", latest == null ? "—" : latest.toFixed(3)],
    ["Spec", spec],
    ["Sample", `${b.dates[STATE.startIdx]}–${b.dates[b.dates.length-1]}`],
  ];
  $("readout").innerHTML = stats
    .map(([s, val]) => `<div class="stat"><b>${val}</b><span>${s}</span></div>`).join("");
}

/* ---- Bar chart of the last 22 ISM prints (always full series, not trimmed) ---- */
function renderRecentBars(res) {
  const b = backbone();
  const N = 22;
  const pairs = [];
  for (let i = b.dates.length - 1; i >= 0 && pairs.length < N; i--) {
    if (res.ISM[i] != null) pairs.push([b.dates[i], res.ISM[i]]);
  }
  pairs.reverse();
  const xs = pairs.map(p => p[0]), ys = pairs.map(p => p[1]);

  if (STATE.selectedDate && !xs.includes(STATE.selectedDate)) STATE.selectedDate = null;

  const baseColors = ys.map(v => v >= 0 ? POS : NEG);
  const colors = xs.map((d, i) => STATE.selectedDate === d ? "#ffffff" : baseColors[i]);
  const opacity = xs.map(d => STATE.selectedDate && STATE.selectedDate !== d ? 0.45 : 1);

  const layout = {
    paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 11 },
    margin: { l: 40, r: 10, t: 6, b: 60 },
    xaxis: { tickangle: -60, gridcolor: "transparent" },
    yaxis: { title: "ISM", gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
  };
  Plotly.react("bars",
    [{ x: xs, y: ys, type: "bar",
       marker: { color: colors, opacity },
       hovertemplate: "%{x}: %{y:.3f}<extra></extra>",
       cursor: "pointer" }],
    layout, { responsive: true, displayModeBar: false });

  const el = $("bars");
  if (el.on && !el._ismClickBound) {
    el._ismClickBound = true;
    el.on("plotly_click", data => {
      const date = data.points[0].x;
      STATE.selectedDate = (STATE.selectedDate === date) ? null : date;
      const { res: cur } = currentResult();
      if (!cur) return;
      renderRecentBars(cur);    // highlight only — skip the main chart for speed
      renderDrivers(cur);
    });
  }
}

/* ---- Top drivers of the selected (or latest) index value ---- */
function renderDrivers(res) {
  const b = backbone();
  const host = "drivers";
  const entry = res.driversEntry;
  const dateEl = $("drivers-date");

  let dd = null;
  if (entry) {
    if (STATE.selectedDate && entry.history && entry.history.length) {
      dd = entry.history.find(h => h.date === STATE.selectedDate) || null;
    }
    if (!dd) dd = entry;   // fall back to latest
  }

  if (!dd || !dd.contrib || dd.contrib.length === 0 || !b.categories) {
    dateEl.textContent = "";
    Plotly.react(host, [], { paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG,
      font: { color: MUTED }, margin: { t: 10 },
      annotations: [{ text: "no active drivers this month", showarrow: false,
        font: { color: MUTED }, x: 0.5, y: 0.5, xref: "paper", yref: "paper" }] },
      { displayModeBar: false });
    return;
  }
  const isLatest = !STATE.selectedDate || STATE.selectedDate === entry.date;
  dateEl.textContent = `(${dd.date}${isLatest ? " · latest" : " · click again to deselect"})`;
  const top = dd.contrib.slice(0, 15).reverse();
  const labels = top.map(p => {
    const c = b.categories[p[0]];
    const name = c ? c.label : `cat ${p[0]}`;
    return name.length > 34 ? name.slice(0, 32) + "…" : name;
  });
  const vals = top.map(p => p[1]);
  const colors = vals.map(v => v >= 0 ? POS : NEG);
  const layout = {
    paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 11 },
    margin: { l: 180, r: 16, t: 6, b: 30 },
    xaxis: { title: "contribution to ISM", gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
    yaxis: { gridcolor: "transparent", automargin: true },
  };
  Plotly.react(host,
    [{ x: vals, y: labels, type: "bar", orientation: "h", marker: { color: colors },
       hovertemplate: "%{y}: %{x:.4f}<extra></extra>" }],
    layout, { responsive: true, displayModeBar: false });
}

function setupDownload() {
  $("download").onclick = () => {
    const b = backbone();
    const { res } = currentResult();
    if (!res) return;
    const head = b.headline ? b.headline.series : null;
    const headCol = STATE.backbone === "cpi" ? "cpi_yoy" : "pce_yoy";
    const rows = [["date", "ISM", "S_pos", "S_neg", "author_ISM", headCol]];
    for (let i = STATE.startIdx; i < b.dates.length; i++) {
      rows.push([b.dates[i], res.ISM[i], res.S_pos[i], res.S_neg[i],
                 b.author ? b.author.ISM[i] : "", head ? head[i] : ""]);
    }
    const csv = rows.map(r => r.map(v => v == null ? "" : v).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const exN = exSet().size;
    a.download = `ism_${STATE.backbone}_AR${STATE.ar}_W${STATE.W}_k${STATE.k}_${STATE.scheme}` +
                 (exN ? `_ex${exN}` : "") + ".csv";
    a.click();
  };
}
