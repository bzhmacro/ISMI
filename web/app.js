/* Inflation Shock Momentum — interactive explorer (zero-build, static).
   Reads data/ism.json (precomputed by scripts/export_web_data.py) and lets the
   user switch AR order / run-length / weighting and display options. All the
   heavy modelling is precomputed; this file only selects + plots + correlates. */

const STATE = { ar: 1, k: 3, scheme: "extensive", startIdx: 0,
                author: true, components: false, pce: true };
let DATA = null;
let X = [];           // Date objects for the x-axis

const PLOT_BG = "#171e26", GRID = "#243240", INK = "#e6edf3", MUTED = "#8b98a5";

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
  X = DATA.dates.map(d => new Date(d + "-01"));

  // demo banner
  if ((DATA.meta.note || "").toUpperCase().includes("DEMO")) {
    const b = document.getElementById("demo-banner");
    b.hidden = false;
    b.textContent = "⚠ Showing DEMO synthetic data. Run scripts/export_web_data.py on real BEA data to replace it.";
  }
  document.getElementById("meta").textContent =
    `${DATA.meta.n_categories} categories · ${DATA.dates[0]}–${DATA.dates[DATA.dates.length-1]} · generated ${(DATA.meta.generated_utc||"").slice(0,10)}`;

  buildSegments();
  setupToggles();
  setupRange();
  setupDownload();
  render();
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
  const map = { "t-author": "author", "t-components": "components", "t-pce": "pce" };
  for (const [id, key] of Object.entries(map)) {
    const el = document.getElementById(id);
    el.checked = STATE[key];
    el.onchange = () => { STATE[key] = el.checked; render(); };
  }
}

function setupRange() {
  const r = document.getElementById("start");
  r.min = 0; r.max = DATA.dates.length - 1; r.value = 0;
  r.oninput = () => { STATE.startIdx = +r.value; render(); };
}

function currentCombo() { return DATA.combos[`AR${STATE.ar}|k${STATE.k}|${STATE.scheme}`]; }

function sliceFrom(arr) { return arr.slice(STATE.startIdx); }

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
  document.getElementById("start-label").textContent = DATA.dates[STATE.startIdx];
  const combo = currentCombo();
  const x = sliceFrom(X);
  const ism = sliceFrom(combo.ISM);

  const traces = [];
  traces.push({ x, y: ism, name: "ISM (replicated)", type: "scatter", mode: "lines",
                line: { color: "#4c9aff", width: 1.8 }, yaxis: "y" });

  if (STATE.author && DATA.author) {
    traces.push({ x, y: sliceFrom(DATA.author.ISM), name: "ISM (author)", type: "scatter",
                  mode: "lines", line: { color: "#e6edf3", width: 1.2, dash: "dot" }, yaxis: "y" });
  }
  if (STATE.components) {
    traces.push({ x, y: sliceFrom(combo.S_pos), name: "S⁺ positive", type: "scatter", mode: "lines",
                  line: { color: "#f5a623", width: 1 }, yaxis: "y" });
    traces.push({ x, y: sliceFrom(combo.S_neg), name: "S⁻ negative", type: "scatter", mode: "lines",
                  line: { color: "#3fb950", width: 1 }, yaxis: "y" });
  }
  if (STATE.pce && DATA.pce_yoy) {
    traces.push({ x, y: sliceFrom(DATA.pce_yoy), name: "PCE inflation (12m, %)", type: "scatter",
                  mode: "lines", line: { color: "#d05ce3", width: 1 }, yaxis: "y2" });
  }

  const layout = {
    paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
    margin: { l: 50, r: 55, t: 10, b: 36 },
    legend: { orientation: "h", y: 1.12, font: { size: 11 } },
    xaxis: { gridcolor: GRID, zeroline: false },
    yaxis: { title: "ISM index", gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
    yaxis2: { title: "PCE inflation (12m, %)", overlaying: "y", side: "right", gridcolor: "transparent", showgrid: false },
    shapes: [{ type: "line", x0: x[0], x1: x[x.length-1], y0: 0, y1: 0, yref: "y",
               line: { color: "#3a4b5c", width: 1 } }],
  };
  Plotly.react("chart", traces, layout, { responsive: true, displayModeBar: false });
  renderReadout(combo);
}

function renderReadout(combo) {
  const ism = sliceFrom(combo.ISM);
  const corr = DATA.author ? pearson(ism, sliceFrom(DATA.author.ISM)) : NaN;
  const latest = [...ism].reverse().find(v => v != null);
  const stats = [
    ["Correlation w/ author", isNaN(corr) ? "—" : corr.toFixed(3)],
    ["Latest ISM", latest == null ? "—" : latest.toFixed(3)],
    ["Spec", `AR(${STATE.ar}) · k=${STATE.k} · ${STATE.scheme}`],
    ["Sample", `${DATA.dates[STATE.startIdx]}–${DATA.dates[DATA.dates.length-1]}`],
  ];
  document.getElementById("readout").innerHTML = stats
    .map(([s, b]) => `<div class="stat"><b>${b}</b><span>${s}</span></div>`).join("");
}

function setupDownload() {
  document.getElementById("download").onclick = () => {
    const combo = currentCombo();
    const rows = [["date", "ISM", "S_pos", "S_neg", "author_ISM", "pce_yoy"]];
    for (let i = STATE.startIdx; i < DATA.dates.length; i++) {
      rows.push([DATA.dates[i], combo.ISM[i], combo.S_pos[i], combo.S_neg[i],
                 DATA.author ? DATA.author.ISM[i] : "", DATA.pce_yoy ? DATA.pce_yoy[i] : ""]);
    }
    const csv = rows.map(r => r.map(v => v == null ? "" : v).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `ism_AR${STATE.ar}_k${STATE.k}_${STATE.scheme}.csv`;
    a.click();
  };
}
