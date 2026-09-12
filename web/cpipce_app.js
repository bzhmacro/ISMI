/* CPI -> PCE — the fourth model in the interactive site.

   Two questions on one page, both driven by the concordance in
   config/cpi_pce_concordance.csv:

     Gap    why the two gauges print different numbers, as an exact identity:
            formula, weight, price-measure, scope, coverage and a reported
            residual, summing to the wedge month by month (Eqs. C1-C6 of
            src/ism/cpi_pce.py).
     Bridge what a CPI print implies for PCE, group by group, with the
            historical distribution of the mapping's own errors.
     Groups the 28 common groups side by side: CPI weight, PCE weight, and the
            pass-through slope — the row where a slope sits far below 1 is the
            row where the two gauges are not measuring the same thing.

   Unlike the other three models nothing is recomputed in the browser here: the
   decomposition is an accounting identity and the bridge is a rolling
   regression over the full panels, both of which are cheap to ship and
   pointless to make interactive — there is no parameter a reader would want to
   drag. data/trim.json carries the finished series. */

(() => {
  const D = { view: "gap", startIdx: 0, smooth: false, inited: false };
  let DATA = null, C = null, X = [];
  const $ = id => document.getElementById(id);

  const PLOT_BG = "#171e26", GRID = "#243240", INK = "#e6edf3";
  const GAP = "#e6edf3";
  /* One colour per component, warm where the term pushes CPI above PCE. */
  const COLORS = {
    price: "#f5605a", weight: "#f5a623", formula: "#c9b458",
    scope: "#4c9aff", coverage: "#7b6cff", residual: "#8b98a5",
  };
  const NAMES = {
    price: "Price measure", weight: "Weights", formula: "Formula (fixed vs Fisher)",
    scope: "Scope (PCE-only spending)", coverage: "Coverage (CPI-only lines)",
    residual: "Rebuild residual",
  };

  async function init() {
    D.inited = true;
    try {
      const res = await fetch("data/trim.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      DATA = await res.json();
      C = DATA.cpipce;
      if (!C) throw new Error("payload has no cpipce block");
    } catch (e) {
      $("x-chart").innerHTML =
        `<div style="padding:24px;color:#f0d28a">Could not load the CPI→PCE data from
         <code>data/trim.json</code>. Run <code>python scripts/export_trim_data.py</code>,
         then redeploy. (${e})</div>`;
      return;
    }
    X = C.dates.map(d => new Date(d + "-01"));
    D.startIdx = Math.max(0, C.dates.length - 12 * 26);   // open on 2000-
    buildControls();
    render();
  }

  function buildControls() {
    seg("x-view", ["gap", "bridge", "groups"], D.view,
        v => ({ gap: "Why they differ", bridge: "CPI → PCE nowcast",
                groups: "Group by group" }[v]),
        v => { D.view = v; render(); });

    const start = $("x-start");
    if (start) {
      start.max = String(C.dates.length - 1);
      start.value = String(D.startIdx);
      start.oninput = () => { D.startIdx = +start.value; render(); };
    }
    const sm = $("x-smooth");
    if (sm) { sm.checked = D.smooth; sm.onchange = () => { D.smooth = sm.checked; render(); }; }

    const dl = $("x-download");
    if (dl) dl.onclick = downloadCsv;

    const notes = $("x-notes");
    if (notes) notes.innerHTML = (C.notes || []).map(n => `<div>${n}</div>`).join("")
      + `<div class="muted">CPI side: ${C.cpi_scope}. Bridge window ${C.bridge.window} months; `
      + `its own monthly RMSE is ${C.bridge.rmse == null ? "—" : C.bridge.rmse.toFixed(3)}pp.</div>`;
  }

  function seg(id, values, current, label, onPick) {
    const host = $(id); if (!host) return; host.innerHTML = "";
    values.forEach(v => {
      const b = document.createElement("button");
      b.textContent = label(v);
      b.setAttribute("aria-pressed", String(v === current));
      b.onclick = () => {
        [...host.children].forEach(c => c.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true"); onPick(v);
      };
      host.appendChild(b);
    });
  }

  const sliceFrom = a => (a ? a.slice(D.startIdx) : a);

  /* A 12-month mean over an already-12-month series is only for reading the
     stack: the monthly wiggle in the components is real but hides the level. */
  function smooth(a) {
    if (!D.smooth || !a) return a;
    const out = new Array(a.length).fill(null), W = 12;
    for (let i = W - 1; i < a.length; i++) {
      let s = 0, n = 0;
      for (let j = i - W + 1; j <= i; j++) if (a[j] != null) { s += a[j]; n++; }
      if (n === W) out[i] = s / W;
    }
    return out;
  }

  function render() {
    const lab = $("x-start-label"); if (lab) lab.textContent = C.dates[D.startIdx];
    if (D.view === "gap") renderGap();
    else if (D.view === "bridge") renderBridge();
    else renderGroups();
    renderReadout();
  }

  // ---- view 1: the gap -----------------------------------------------------
  function renderGap() {
    show("x-chart", true); show("x-table", false); show("x-bridge-panels", false);
    const x = sliceFrom(X);
    const traces = C.components.map(k => ({
      x, y: sliceFrom(smooth(C.table[k])), name: NAMES[k] || k,
      type: "bar", marker: { color: COLORS[k] || "#8b98a5" },
    }));
    traces.push({
      x, y: sliceFrom(smooth(C.table.gap)), name: "CPI − PCE (12m, pp)",
      type: "scatter", mode: "lines", line: { color: GAP, width: 1.8 },
    });
    Plotly.react("x-chart", traces, {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
      barmode: "relative",
      margin: { l: 52, r: 16, t: 10, b: 36 },
      legend: { orientation: "h", y: 1.15, font: { size: 10 } },
      xaxis: { gridcolor: GRID },
      yaxis: { title: "contribution to the CPI − PCE gap (pp)", gridcolor: GRID,
               zeroline: true, zerolinecolor: "#3a4b5c" },
    }, { responsive: true, displayModeBar: false });
  }

  // ---- view 2: the bridge --------------------------------------------------
  function renderBridge() {
    show("x-chart", true); show("x-table", false); show("x-bridge-panels", true);
    const x = sliceFrom(X), b = C.bridge;
    const err = b.yoy.implied.map((v, i) =>
      (v == null || b.yoy.actual[i] == null) ? null : v - b.yoy.actual[i]);
    const sd = stdev(err);

    const band = (mult, name, color) => ({
      x, y: sliceFrom(b.yoy.implied.map(v => v == null ? null : v + mult * sd)),
      name, type: "scatter", mode: "lines", line: { width: 0 },
      fill: mult < 0 ? "tonexty" : "none", fillcolor: "rgba(245,166,35,0.14)",
      showlegend: false, hoverinfo: "skip",
    });

    Plotly.react("x-chart", [
      band(1, "", "#f5a623"), band(-1, "", "#f5a623"),
      { x, y: sliceFrom(b.yoy.implied), name: "PCE implied by CPI (12m)",
        type: "scatter", mode: "lines", line: { color: "#f5a623", width: 1.8 } },
      { x, y: sliceFrom(b.yoy.actual), name: "PCE actual (12m)",
        type: "scatter", mode: "lines", line: { color: "#4c9aff", width: 1.6 } },
    ], {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
      margin: { l: 52, r: 16, t: 10, b: 36 },
      legend: { orientation: "h", y: 1.13, font: { size: 11 } },
      xaxis: { gridcolor: GRID },
      yaxis: { title: "12-month PCE inflation (%)", gridcolor: GRID,
               zeroline: true, zerolinecolor: "#3a4b5c" },
    }, { responsive: true, displayModeBar: false });

    renderContributions();
  }

  function renderContributions() {
    const rows = (C.bridge.contributions || []).slice(0, 14);
    const el = $("x-bars-date");
    if (el) el.textContent = C.bridge.latest_month || "";
    Plotly.react("x-bars", [{
      type: "bar", orientation: "h",
      y: rows.map(r => r.group).reverse(),
      x: rows.map(r => r.contribution).reverse(),
      marker: { color: rows.map(r => r.role === "scope" ? "#7b6cff" : "#f5a623").reverse() },
      hovertemplate: "%{y}<br>contribution %{x:.3f}pp<extra></extra>",
    }], {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 10 },
      margin: { l: 150, r: 10, t: 6, b: 30 },
      xaxis: { title: "implied contribution to the month (pp)", gridcolor: GRID,
               zeroline: true, zerolinecolor: "#3a4b5c" },
      yaxis: { tickfont: { size: 9 } },
    }, { responsive: true, displayModeBar: false });
  }

  // ---- view 3: the groups --------------------------------------------------
  function renderGroups() {
    show("x-chart", false); show("x-table", true); show("x-bridge-panels", false);
    const host = $("x-table"); if (!host) return;
    const rows = [...C.groups].sort((a, b) => (b.w_pce || 0) - (a.w_pce || 0));
    const fmt = (v, dp = 2) => v == null ? "—" : v.toFixed(dp);
    /* A scope group has no counterpart on the other side, so its cell is empty
       rather than zero — print a dash without a stray unit after it. */
    const pct = v => v == null ? "—" : `${v.toFixed(2)}%`;
    host.innerHTML =
      `<table class="tbl"><thead><tr>
         <th>Group</th><th>Role</th><th>CPI weight</th><th>PCE weight</th>
         <th>Pass-through</th><th>CPI 12m</th><th>PCE 12m</th></tr></thead><tbody>`
      + rows.map(r => {
          const cpi = lastOf(r.cpi_yoy), pce = lastOf(r.pce_yoy);
          const slope = r.slope;
          const cls = slope == null ? "" : (slope < 0.6 ? "low" : (slope > 1.15 ? "high" : ""));
          return `<tr>
            <td title="CPI: ${esc(r.cpi_members)}&#10;PCE: ${esc(r.pce_members)}">${r.group}</td>
            <td class="muted">${r.role}</td>
            <td>${pct(r.w_cpi)}</td><td>${pct(r.w_pce)}</td>
            <td class="${cls}">${slope == null ? "—" : fmt(slope)}</td>
            <td>${pct(cpi)}</td><td>${pct(pce)}</td></tr>`;
        }).join("")
      + `</tbody></table>`;
  }

  function renderReadout() {
    const t = C.table, i = lastIdx(t.gap);
    if (i < 0) { $("x-readout").innerHTML = ""; return; }
    const parts = C.components
      .map(k => [NAMES[k] || k, t[k][i]])
      .filter(([, v]) => v != null)
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    const biggest = parts[0];
    const stats = [
      ["CPI (12m)", fmtPct(t.cpi[i])],
      ["PCE (12m)", fmtPct(t.pce[i])],
      ["Gap", fmtPct(t.gap[i], true)],
      [biggest ? `Biggest term — ${biggest[0].toLowerCase()}` : "Biggest term",
       biggest ? `${biggest[1] >= 0 ? "+" : ""}${biggest[1].toFixed(2)}pp` : "—"],
      [`as of ${C.dates[i]}`, C.table.ccpi_proxy[i] == null ? "—"
        : `${C.table.ccpi_proxy[i].toFixed(2)}pp`],
    ];
    $("x-readout").innerHTML = stats.map(([k, v]) =>
      `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
    const last = $("x-readout").lastElementChild;
    if (last) last.querySelector("span").textContent =
      "C-CPI-U formula proxy (diagnostic)";
  }

  // ---- helpers -------------------------------------------------------------
  function show(id, on) { const el = $(id); if (el) el.hidden = !on; }
  function lastIdx(a) { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return i; return -1; }
  function lastOf(a) { const i = a ? lastIdx(a) : -1; return i < 0 ? null : a[i]; }
  function fmtPct(v, signed) {
    if (v == null) return "—";
    return `${signed && v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
  }
  function esc(s) { return String(s || "").replace(/"/g, "&quot;").replace(/</g, "&lt;"); }
  function stdev(a) {
    let n = 0, s = 0, ss = 0;
    for (const v of a) if (v != null) { n++; s += v; ss += v * v; }
    return n < 3 ? 0 : Math.sqrt(Math.max(0, ss / n - (s / n) ** 2));
  }

  function downloadCsv() {
    const cols = ["cpi", "pce", "gap"].concat(C.components).concat(["ccpi_proxy"]);
    const rows = [["date"].concat(cols).concat(["bridge_implied_yoy", "bridge_actual_yoy"])];
    for (let i = D.startIdx; i < C.dates.length; i++) {
      rows.push([C.dates[i]]
        .concat(cols.map(c => C.table[c] ? C.table[c][i] : ""))
        .concat([C.bridge.yoy.implied[i], C.bridge.yoy.actual[i]]));
    }
    const csv = rows.map(r => r.map(v => v == null ? "" : v).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "cpi_pce_gap.csv";
    a.click();
  }

  // ---- register ------------------------------------------------------------
  window.CpiPceApp = { init };
  if (typeof ModelBar !== "undefined") {
    ModelBar.register({
      key: "cpipce",
      label: "CPI → PCE",
      viewId: "cpipce-view",
      sub: "Why CPI and PCE inflation differ — formula, weights, price sources "
         + "and scope, as an exact monthly identity — and what a CPI print "
         + "implies for the PCE print that follows it.",
      init,
    });
  }
})();
