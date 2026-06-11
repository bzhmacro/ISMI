/* Inflation Shock Momentum — interactive explorer (zero-build, static).
   Reads data/ism.json (precomputed by scripts/export_web_data.py) and lets the
   user switch the price gauge (PCE / CPI backbone), AR order, run-length,
   weighting and display options. All the heavy modelling is precomputed; this
   file only selects + plots + correlates. */

const STATE = { backbone: "pce", ar: 1, k: 3, scheme: "extensive", startIdx: 0,
                author: true, components: false, headline: true };
let DATA = null;
let X = [];           // Date objects for the x-axis of the active backbone

const PLOT_BG = "#171e26", GRID = "#243240", INK = "#e6edf3", MUTED = "#8b98a5";
const POS = "#f5a623", NEG = "#4c9aff";
// Headline-inflation overlay colour, chosen per backbone so the two gauges read
// distinctly when a user flips between them.
const HEADLINE_COLOR = { pce: "#d05ce3", cpi: "#2dd4bf" };

init();

async function init() {
  try {
    const res = await fetch("data/ism.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    DATA = await res.json();
  } catch (e) {
    document.getElementById("chart").innerHTML =
      `<div style="padding:24px;color:#f0d28a">Could not load <code>data/ism.json</code>.
       Run <code>python scripts/export_web_data.py</code> to generate it, then redeploy. (${e})</div>`;
    return;
  }

  // Default backbone (v2 schema). Legacy flat files fall back to "pce".
  STATE.backbone = (DATA.meta && DATA.meta.default_backbone) || "pce";

  const asof = (DATA.meta.generated_utc || "").slice(0, 10);
  const b = backbone();
  const lastMonth = b.dates[b.dates.length - 1];
  document.getElementById("asof").textContent =
    `● Data through ${lastMonth} · generated ${asof} · auto-refreshes monthly`;

  if ((b.note || DATA.meta.note || "").toUpperCase().includes("DEMO")) {
    const ban = document.getElementById("demo-banner");
    ban.hidden = false;
    ban.textContent = "⚠ Showing DEMO synthetic data. Run scripts/export_web_data.py on real data to replace it.";
  }

  buildBackboneSegment();
  buildSegments();
  setupToggles();
  applyBackbone();          // sets X, range, labels for the active backbone
  setupDownload();
  render();
}

/* ---- the active backbone object, with backward-compat for the flat schema ---- */
function backbone() {
  if (DATA.backbones) return DATA.backbones[STATE.backbone];
  return {                                   // legacy flat ism.json
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

function buildBackboneSegment() {
  const host = document.getElementById("backbone");
  if (!host) return;
  const names = (DATA.meta && DATA.meta.backbones) || ["pce"];
  if (names.length < 2) { host.closest(".control").hidden = true; return; }
  const label = n => (DATA.backbones && DATA.backbones[n] && DATA.backbones[n].label) || n.toUpperCase();
  segment("backbone", names, STATE.backbone, label, n => {
    STATE.backbone = n;
    applyBackbone();
    render();
  });
}

function buildSegments() {
  segment("ar", DATA.meta.ar_orders, STATE.ar, v => `AR(${v})`, v => { STATE.ar = v; render(); });
  segment("k", DATA.meta.run_lengths, STATE.k, v => `k=${v}`, v => { STATE.k = v; render(); });
  segment("scheme", DATA.meta.schemes, STATE.scheme, v => v, v => { STATE.scheme = v; render(); });
}

function segment(id, values, current, label, onPick) {
  const host = document.getElementById(id);
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

function setupToggles() {
  const map = { "t-author": "author", "t-components": "components", "t-pce": "headline" };
  for (const [id, key] of Object.entries(map)) {
    const el = document.getElementById(id);
    el.checked = STATE[key];
    el.onchange = () => { STATE[key] = el.checked; render(); };
  }
}

/* Re-point everything that depends on which backbone is active. Called on load
   and whenever the gauge toggle flips. */
function applyBackbone() {
  const b = backbone();
  X = b.dates.map(d => new Date(d + "-01"));

  // Author overlay only exists for PCE (the paper's gauge). Disable + uncheck
  // the control when the active backbone has no author series.
  const authEl = document.getElementById("t-author");
  const hasAuthor = !!b.author;
  authEl.disabled = !hasAuthor;
  const authLabel = authEl.closest(".chk");
  if (authLabel) {
    authLabel.style.opacity = hasAuthor ? "" : ".4";
    authLabel.title = hasAuthor ? "" : `No author series for the ${b.label} backbone`;
  }
  if (!hasAuthor) authEl.checked = false;
  STATE.author = authEl.checked;

  // Headline-inflation toggle label tracks the gauge (PCE vs CPI).
  const span = document.getElementById("t-headline-text");
  if (span) span.textContent = shortHeadlineLabel(b);

  // Range slider: default to first month with a computed index for THIS gauge.
  const r = document.getElementById("start");
  r.min = 0; r.max = b.dates.length - 1;
  const base = (b.combos["AR1|k3|extensive"] || Object.values(b.combos)[0]).ISM;
  let first = base.findIndex(v => v != null);
  if (first < 0) first = 0;
  STATE.startIdx = first; r.value = first;
  r.oninput = () => { STATE.startIdx = +r.value; render(); };

  // Dynamic copy: category count + footer + explainer.
  const lastMonth = b.dates[b.dates.length - 1];
  document.getElementById("meta").textContent =
    `${b.n_categories} categories · ${b.dates[0]}–${lastMonth}`;
  const cnt = document.getElementById("cat-count");
  if (cnt) cnt.textContent =
    STATE.backbone === "cpi" ? "~70 BLS CPI item strata" : "~130 disaggregated PCE categories";
  const foot = document.getElementById("foot-source");
  if (foot) foot.textContent = backboneFooter(b);
  const wnote = document.getElementById("weight-note");
  if (wnote) wnote.textContent = b.weight_note || "";
}

function shortHeadlineLabel(b) {
  return STATE.backbone === "cpi" ? "CPI inflation (12m)" : "PCE inflation (12m)";
}

function backboneFooter(b) {
  if (STATE.backbone === "cpi") {
    return "CPI backbone: BLS CPI-U item strata (CUUR0000*, NSA); weights = Dec-2023 relative importance, renormalised monthly. No author overlay (the paper uses PCE).";
  }
  return "PCE backbone: BEA Underlying Detail + FRED. Index correlates ~0.99 with the authors' series.";
}

function comboKey() { return `AR${STATE.ar}|k${STATE.k}|${STATE.scheme}`; }
function currentCombo() { return backbone().combos[comboKey()]; }
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

function render() {
  const b = backbone();
  document.getElementById("start-label").textContent = b.dates[STATE.startIdx];
  const combo = currentCombo();
  const x = sliceFrom(X);
  const ism = sliceFrom(combo.ISM);
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
    traces.push({ x, y: sliceFrom(combo.S_pos), name: "S⁺ positive", type: "scatter", mode: "lines",
                  line: { color: POS, width: 1 }, yaxis: "y" });
    traces.push({ x, y: sliceFrom(combo.S_neg), name: "S⁻ negative", type: "scatter", mode: "lines",
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

  renderReadout(combo);
  renderRecentBars(combo);
  renderDrivers();
}

function renderReadout(combo) {
  const b = backbone();
  const ism = sliceFrom(combo.ISM);
  const corr = b.author ? pearson(ism, sliceFrom(b.author.ISM)) : NaN;
  const latest = [...combo.ISM].reverse().find(v => v != null);
  const stats = [
    ["Correlation w/ author", isNaN(corr) ? "—" : corr.toFixed(3)],
    ["Latest ISM", latest == null ? "—" : latest.toFixed(3)],
    ["Spec", `${b.label} · AR(${STATE.ar}) · k=${STATE.k} · ${STATE.scheme}`],
    ["Sample", `${b.dates[STATE.startIdx]}–${b.dates[b.dates.length-1]}`],
  ];
  document.getElementById("readout").innerHTML = stats
    .map(([s, val]) => `<div class="stat"><b>${val}</b><span>${s}</span></div>`).join("");
}

/* ---- Bar chart of the last 22 ISM prints (always full series, not trimmed) ---- */
function renderRecentBars(combo) {
  const b = backbone();
  const N = 22;
  const pairs = [];
  for (let i = b.dates.length - 1; i >= 0 && pairs.length < N; i--) {
    if (combo.ISM[i] != null) pairs.push([b.dates[i], combo.ISM[i]]);
  }
  pairs.reverse();
  const xs = pairs.map(p => p[0]), ys = pairs.map(p => p[1]);
  const colors = ys.map(v => v >= 0 ? POS : NEG);
  const layout = {
    paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 11 },
    margin: { l: 40, r: 10, t: 6, b: 60 },
    xaxis: { tickangle: -60, gridcolor: "transparent" },
    yaxis: { title: "ISM", gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
  };
  Plotly.react("bars",
    [{ x: xs, y: ys, type: "bar", marker: { color: colors }, hovertemplate: "%{x}: %{y:.3f}<extra></extra>" }],
    layout, { responsive: true, displayModeBar: false });
}

/* ---- Top drivers of the latest index value for the selected combo ---- */
function renderDrivers() {
  const b = backbone();
  const host = "drivers";
  const dd = b.drivers ? b.drivers[comboKey()] : null;
  const dateEl = document.getElementById("drivers-date");
  if (!dd || !dd.contrib || dd.contrib.length === 0 || !b.categories) {
    dateEl.textContent = "";
    Plotly.react(host, [], { paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG,
      font: { color: MUTED }, margin: { t: 10 },
      annotations: [{ text: "no active drivers this month", showarrow: false,
        font: { color: MUTED }, x: 0.5, y: 0.5, xref: "paper", yref: "paper" }] },
      { displayModeBar: false });
    return;
  }
  dateEl.textContent = `(${dd.date})`;
  const top = dd.contrib.slice(0, 15).reverse();   // already sorted by |value| desc
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
  document.getElementById("download").onclick = () => {
    const b = backbone();
    const combo = currentCombo();
    const head = b.headline ? b.headline.series : null;
    const headCol = STATE.backbone === "cpi" ? "cpi_yoy" : "pce_yoy";
    const rows = [["date", "ISM", "S_pos", "S_neg", "author_ISM", headCol]];
    for (let i = STATE.startIdx; i < b.dates.length; i++) {
      rows.push([b.dates[i], combo.ISM[i], combo.S_pos[i], combo.S_neg[i],
                 b.author ? b.author.ISM[i] : "", head ? head[i] : ""]);
    }
    const csv = rows.map(r => r.map(v => v == null ? "" : v).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `ism_${STATE.backbone}_AR${STATE.ar}_k${STATE.k}_${STATE.scheme}.csv`;
    a.click();
  };
}
