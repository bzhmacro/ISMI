/* CPI -> PCE — the fourth model in the interactive site.

   The question this page exists to answer: the CPI for month M is out, the PCE
   for month M is not, so what is the PCE going to print?

   Four views, in the order you would actually use them:

     Nowcast  the estimate itself — m/m and y/y, headline and core, with the
              band the estimator has actually earned recently — plus the group
              contributions that add up to it.
     Inputs   the CPI and PPI readings the estimate is built from, which are on
              the table two weeks before the PCE is.
     Gap      why the two gauges differ at all, as an exact monthly identity
              (Eqs. C1-C6 of src/ism/cpi_pce.py).
     Groups   the 28 common groups side by side: weights, m/m, y/y, the
              pass-through slope, and which PPI series feeds each one.

   Nothing is recomputed in the browser: the decomposition is an accounting
   identity and the bridge is a rolling regression over the full panels. There
   is no parameter a reader would want to drag, so data/trim.json carries the
   finished series and this file renders them. */

(() => {
  const D = { view: "nowcast", scope: "core", horizon: "mom",
              startIdx: 0, smooth: false, inited: false };
  let DATA = null, C = null, X = [];
  const $ = id => document.getElementById(id);

  // bzhmacro house tokens — see the note in app.js.
  const PLOT_BG = "#161D2C", GRID = "#2A3448", INK = "#EDE6D6";
  const IMPLIED = "#f5a623", ACTUAL = "#4c9aff", PPI_C = "#3fb950", GAPC = "#e6edf3";
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
    D.scope = (C.bridge && C.bridge.default_scope) || "core";
    D.startIdx = Math.max(0, C.dates.length - 12 * 8);   // the nowcast wants a close-up
    buildControls();
    render();
  }

  const bridge = () => C.bridge.scopes[D.scope];

  function buildControls() {
    seg("x-view", ["nowcast", "inputs", "gap", "groups"], D.view,
        v => ({ nowcast: "What will PCE print?", inputs: "The inputs (CPI & PPI)",
                gap: "Why they differ", groups: "Group by group" }[v]),
        v => { D.view = v;
               D.startIdx = (v === "gap") ? Math.max(0, C.dates.length - 12 * 26)
                                          : Math.max(0, C.dates.length - 12 * 8);
               syncStart(); render(); });

    seg("x-scope", ["core", "headline"], D.scope,
        v => v === "core" ? "Core PCE" : "Headline PCE",
        v => { D.scope = v; render(); });

    seg("x-horizon", ["mom", "yoy"], D.horizon,
        v => v === "mom" ? "Month over month" : "Year over year",
        v => { D.horizon = v; render(); });

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
  }

  function syncStart() {
    const start = $("x-start"); if (start) start.value = String(D.startIdx);
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
    show("x-scope-ctl", D.view !== "gap");
    show("x-horizon-ctl", D.view !== "gap" && D.view !== "groups");
    show("x-smooth-ctl", D.view === "gap");
    if (D.view !== "gap" && D.view !== "groups") renderAnswer();
    if (D.view === "nowcast") renderNowcast();
    else if (D.view === "inputs") renderInputs();
    else if (D.view === "gap") renderGap();
    else renderGroups();
  }

  /* The answer stays pinned while you look at what it is built from, so the
     Inputs view does not leave a stale number from the previous view. */
  function renderAnswer() {
    const b = bridge(), f = b.forecast, lp = b.last_published;
    const isMom = D.horizon === "mom";
    const stats = [];
    if (f) {
      const v = isMom ? f.mom : f.yoy;
      stats.push([`${D.scope === "core" ? "Core" : "Headline"} PCE, ${f.month} — estimate`,
                  `${v >= 0 && isMom ? "+" : ""}${v.toFixed(2)}%`, "big"]);
      stats.push([`1 s.d. band (last ${b.se_window} months)`,
                  `±${b.se.toFixed(2)}pp`, ""]);
      stats.push([`likely range`,
                  `${(v - b.se).toFixed(2)}% to ${(v + b.se).toFixed(2)}%`, ""]);
    } else if (lp && lp.month) {
      /* No pending month: the PCE for the latest CPI is already out. Rather
         than show a dash for the fortnight until the next CPI lands, show the
         month that just printed and how the estimator did on it -- the implied
         value was fitted without that month, so it is the same out-of-sample
         number the page would have shown the day before the release. */
      const a = isMom ? lp.mom : lp.yoy;
      const e = isMom ? lp.implied_mom : lp.implied_yoy;
      stats.push([`${D.scope === "core" ? "Core" : "Headline"} PCE, ${lp.month} — published`,
                  `${a >= 0 && isMom ? "+" : ""}${a.toFixed(2)}%`, "big"]);
      if (e != null) {
        stats.push([`this model's estimate for ${lp.month}`,
                    `${e >= 0 && isMom ? "+" : ""}${e.toFixed(2)}%`, ""]);
        stats.push(["miss", `${e - a >= 0 ? "+" : ""}${(e - a).toFixed(2)}pp`, ""]);
      }
      stats.push(["next estimate", "when the next CPI lands", ""]);
    } else {
      stats.push(["No pending month", "—", "big"]);
      stats.push(["PCE is as current as CPI", "", ""]);
    }
    if (f && lp && lp.month) {
      stats.push([`last published (${lp.month})`,
                  `${isMom ? (lp.mom >= 0 ? "+" : "") + lp.mom.toFixed(2)
                           : lp.yoy.toFixed(2)}%`, ""]);
    }
    if (C.cpi_latest && C.cpi_latest.month) {
      const c = isMom ? C.cpi_latest.mom : C.cpi_latest.yoy;
      stats.push([`the CPI that drives it (${C.cpi_latest.month})`,
                  `${c >= 0 && isMom ? "+" : ""}${c.toFixed(2)}%`, ""]);
    }
    $("x-readout").innerHTML = stats.map(([k, v, cls]) =>
      `<div class="stat ${cls}"><b>${v}</b><span>${k}</span></div>`).join("");
  }

  // ---- view 1: the nowcast -------------------------------------------------
  function renderNowcast() {
    show("x-chart", true); show("x-table", false); show("x-bridge-panels", true);
    const b = bridge(), f = b.forecast;
    const isMom = D.horizon === "mom";
    const x = sliceFrom(X);
    const series = isMom ? b.monthly : b.yoy;
    const sd = b.se;
    const band = mult => ({
      x, y: sliceFrom(series.implied.map(v => v == null ? null : v + mult * sd)),
      type: "scatter", mode: "lines", line: { width: 0 },
      fill: mult < 0 ? "tonexty" : "none", fillcolor: "rgba(245,166,35,0.16)",
      showlegend: false, hoverinfo: "skip",
    });
    const traces = [band(1), band(-1),
      { x, y: sliceFrom(series.implied), name: "PCE implied by CPI (+ PPI)",
        type: "scatter", mode: "lines", line: { color: IMPLIED, width: 1.8 } },
      { x, y: sliceFrom(series.actual), name: "PCE actual",
        type: "scatter", mode: "lines", line: { color: ACTUAL, width: 1.6 } },
    ];
    // mark the forecast month so it cannot be mistaken for history -- or, when
    // the PCE has caught up with the CPI, mark the month that just printed, so
    // the chart still has a point of interest rather than trailing off.
    const lp = b.last_published;
    const mark = f ? { month: f.month, y: isMom ? f.mom : f.yoy,
                       name: `estimate (${f.month})`, filled: true }
        : (lp && lp.month && (isMom ? lp.implied_mom : lp.implied_yoy) != null
            ? { month: lp.month, y: isMom ? lp.implied_mom : lp.implied_yoy,
                name: `estimate for ${lp.month} (out of sample)`, filled: false }
            : null);
    if (mark) {
      const i = C.dates.indexOf(mark.month);
      if (i >= D.startIdx) traces.push({
        x: [X[i]], y: [mark.y], name: mark.name,
        type: "scatter", mode: "markers",
        marker: { color: mark.filled ? IMPLIED : PLOT_BG, size: 11,
                  symbol: "diamond",
                  line: { color: mark.filled ? "#fff" : IMPLIED, width: 1.6 } },
      });
    }
    Plotly.react("x-chart", traces, {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
      margin: { l: 52, r: 16, t: 10, b: 36 },
      legend: { orientation: "h", y: 1.13, font: { size: 11 } },
      xaxis: { gridcolor: GRID },
      yaxis: { title: isMom ? "monthly PCE inflation (%)" : "12-month PCE inflation (%)",
               gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
    }, { responsive: true, displayModeBar: false });

    renderContributions();
    $("x-notes").innerHTML = nowcastNotes();
  }

  function nowcastNotes() {
    const b = bridge(), f = b.forecast, lp = b.last_published;
    const bits = [];
    if (f) bits.push(`The ${f.month} estimate is built from ${f.basis} for ${f.month}, `
      + `which are published about two weeks before the PCE. Each of the 28 spending `
      + `groups is fitted on the trailing ${C.bridge.window} months <em>excluding the `
      + `month being predicted</em>, so this is a nowcast and not a fit.`);
    else if (lp && lp.month) bits.push(`The PCE has caught up with the CPI, so there is `
      + `nothing left to nowcast this month. The hollow diamond is what this model said `
      + `about ${lp.month} <em>before</em> that PCE was published — each group is fitted `
      + `on the trailing ${C.bridge.window} months excluding the month being predicted, `
      + `so it is a like-for-like estimate and not a fit to the answer. A new estimate `
      + `appears as soon as the next CPI lands, about two weeks ahead of the PCE.`);
    bits.push(`Band = the estimator's own root-mean-square one-month error over the last `
      + `${b.se_window} months (±${b.se.toFixed(3)}pp). Over the whole history it is `
      + `${b.rmse.toFixed(3)}pp — the accuracy is regime-dependent, roughly 0.17pp `
      + `through the 1970s and 1980s and 0.04pp through the 2010s.`);
    bits.push(`A 12-month estimate is eleven published months plus this one estimate, `
      + `not a guess about all twelve.`);
    return bits.map(t => `<div>${t}</div>`).join("");
  }

  function renderContributions() {
    const b = bridge();
    const rows = (b.contributions || []).slice(0, 14);
    const el = $("x-bars-date");
    if (el) el.textContent = (b.contributions_month || "")
      + (b.contributions_is_forecast ? " (estimated)" : " (published)");
    Plotly.react("x-bars", [{
      type: "bar", orientation: "h",
      y: rows.map(r => r.group).reverse(),
      x: rows.map(r => r.contribution).reverse(),
      customdata: rows.map(r => [r.implied_rate, 100 * r.weight, r.inputs]).reverse(),
      marker: { color: rows.map(r => r.role === "scope" ? "#7b6cff" : IMPLIED).reverse() },
      hovertemplate: "%{y}<br>contributes %{x:.3f}pp"
        + "<br>rate %{customdata[0]:.2f}% × weight %{customdata[1]:.1f}%"
        + "<br>from: %{customdata[2]}<extra></extra>",
    }], {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 10 },
      margin: { l: 150, r: 10, t: 6, b: 34 },
      xaxis: { title: "contribution to the month (pp)", gridcolor: GRID,
               zeroline: true, zerolinecolor: "#3a4b5c" },
      yaxis: { tickfont: { size: 9 } },
    }, { responsive: true, displayModeBar: false });
  }

  // ---- view 2: the inputs --------------------------------------------------
  function renderInputs() {
    show("x-chart", true); show("x-table", true); show("x-bridge-panels", false);
    const x = sliceFrom(X);
    const traces = [{
      x, y: sliceFrom(C.mom.cpi), name: "CPI (m/m, all items)",
      type: "scatter", mode: "lines", line: { color: ACTUAL, width: 1.6 },
    }, {
      x, y: sliceFrom(C.mom.pce), name: "PCE (m/m, all items)",
      type: "scatter", mode: "lines", line: { color: "#d05ce3", width: 1.4, dash: "dot" },
    }];
    (C.ppi ? C.ppi.series : []).forEach((p, i) => traces.push({
      x, y: sliceFrom(p.mom), name: p.label, type: "scatter", mode: "lines",
      line: { width: 1, dash: "dashdot" }, visible: i < 2 ? true : "legendonly",
    }));
    Plotly.react("x-chart", traces, {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
      margin: { l: 52, r: 16, t: 10, b: 36 },
      legend: { orientation: "h", y: 1.2, font: { size: 9 } },
      xaxis: { gridcolor: GRID },
      yaxis: { title: "month-over-month (%)", gridcolor: GRID,
               zeroline: true, zerolinecolor: "#3a4b5c" },
    }, { responsive: true, displayModeBar: false });

    const host = $("x-table");
    const latest = a => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return [a[i], C.dates[i]]; return [null, ""]; };
    const rows = [];
    const [cm, cmd] = latest(C.mom.cpi), [cy] = [[C.cpi_latest.yoy]];
    rows.push(["CPI, all items", "the headline input", cmd, C.cpi_latest.mom, C.cpi_latest.yoy, ""]);
    (C.ppi ? C.ppi.series : []).forEach(p => {
      const [m, md] = latest(p.mom), [y] = latest(p.yoy);
      rows.push([p.label, p.note || `feeds ${p.group.replace(/_/g, " ")}`, md, m, y, p.group]);
    });
    const [pm, pmd] = latest(C.mom.pce);
    host.innerHTML =
      `<table class="tbl"><thead><tr><th>Input</th><th>Why it matters</th>
        <th>through</th><th>m/m</th><th>y/y</th><th>feeds</th></tr></thead><tbody>`
      + rows.map(r => `<tr><td>${r[0]}</td><td class="muted small">${esc(r[1])}</td>
           <td>${r[2]}</td><td>${fmtPct(r[3], true)}</td><td>${fmtPct(r[4])}</td>
           <td class="muted">${String(r[5]).replace(/_/g, " ")}</td></tr>`).join("")
      + `<tr class="sep"><td>PCE, all items</td>
           <td class="muted small">the thing being estimated — published last</td>
           <td>${pmd}</td><td>${fmtPct(pm, true)}</td>
           <td>${fmtPct(lastOf(C.table.pce))}</td><td class="muted">—</td></tr>`
      + `</tbody></table>`;

    $("x-notes").innerHTML =
      `<div>The producer price index matters here because about a fifth of PCE is not
        priced from the CPI at all. The largest piece is medical services — 17.6% of PCE
        against 6.1% of the CPI — which BEA prices from the PPI, counting what insurers
        pay rather than what a household is billed. Adding these series cuts the
        medical-services nowcast error by 57% and the core PCE error by 21%.</div>
       <div>Portfolio management has <em>no</em> CPI counterpart, so its PPI is the only
        monthly reading that exists for it.</div>
       ${C.ppi ? `<div class="muted">PPI series are published unadjusted; they are
        seasonally adjusted here with trailing month effects (no future data).
        Latest PPI month: ${C.ppi.last_month}.</div>` : ""}`;
  }

  // ---- view 3: the gap -----------------------------------------------------
  function renderGap() {
    show("x-chart", true); show("x-table", false); show("x-bridge-panels", false);
    const x = sliceFrom(X);
    const traces = C.components.map(k => ({
      x, y: sliceFrom(smooth(C.table[k])), name: NAMES[k] || k,
      type: "bar", marker: { color: COLORS[k] || "#8b98a5" },
    }));
    traces.push({
      x, y: sliceFrom(smooth(C.table.gap)), name: "CPI − PCE (12m, pp)",
      type: "scatter", mode: "lines", line: { color: GAPC, width: 1.8 },
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

    const i = lastIdx(C.table.gap);
    const parts = C.components.map(k => [NAMES[k] || k, C.table[k][i]])
      .filter(([, v]) => v != null).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    const big = parts[0];
    $("x-readout").innerHTML = [
      ["CPI (12m)", fmtPct(C.table.cpi[i])],
      ["PCE (12m)", fmtPct(C.table.pce[i])],
      ["Gap", fmtPct(C.table.gap[i], true)],
      [big ? `biggest term — ${big[0].toLowerCase()}` : "biggest term",
       big ? `${big[1] >= 0 ? "+" : ""}${big[1].toFixed(2)}pp` : "—"],
      ["C-CPI-U formula proxy (diagnostic)", fmtPct(C.table.ccpi_proxy[i], true)],
    ].map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
    $("x-notes").innerHTML = (C.notes || []).map(n => `<div>${n}</div>`).join("");
  }

  // ---- view 4: the groups --------------------------------------------------
  function renderGroups() {
    show("x-chart", false); show("x-table", true); show("x-bridge-panels", false);
    const host = $("x-table"); if (!host) return;
    const rows = [...C.groups].sort((a, b) => (b.w_pce || 0) - (a.w_pce || 0));
    const fmt = (v, dp = 2) => v == null ? "—" : v.toFixed(dp);
    const pct = v => v == null ? "—" : `${v.toFixed(2)}%`;
    const signed = v => v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
    host.innerHTML =
      `<table class="tbl"><thead>
         <tr><th rowspan="2">Group</th><th rowspan="2">Role</th>
             <th colspan="2">Weight</th><th colspan="2">CPI</th>
             <th colspan="2">PCE</th><th rowspan="2">Pass-through</th>
             <th rowspan="2">PPI input</th></tr>
         <tr><th>CPI</th><th>PCE</th><th>m/m</th><th>y/y</th><th>m/m</th><th>y/y</th></tr>
       </thead><tbody>`
      + rows.map(r => {
          const cls = r.slope == null ? "" : (r.slope < 0.6 ? "low" : (r.slope > 1.15 ? "high" : ""));
          return `<tr>
            <td title="CPI: ${esc(r.cpi_members)}&#10;PCE: ${esc(r.pce_members)}">${r.group.replace(/_/g, " ")}</td>
            <td class="muted">${r.role}</td>
            <td>${pct(r.w_cpi)}</td><td>${pct(r.w_pce)}</td>
            <td>${signed(lastOf(r.cpi_mom))}</td><td>${pct(lastOf(r.cpi_yoy))}</td>
            <td>${signed(lastOf(r.pce_mom))}</td><td>${pct(lastOf(r.pce_yoy))}</td>
            <td class="${cls}">${r.slope == null ? "—" : fmt(r.slope)}</td>
            <td class="muted small">${(r.ppi || []).join("; ") || "—"}</td></tr>`;
        }).join("")
      + `</tbody></table>`;
    $("x-readout").innerHTML = "";
    $("x-notes").innerHTML =
      `<div>m/m is the latest month each gauge has published — the CPI column runs one
        month ahead of the PCE column, which is exactly the gap the nowcast fills.</div>
       <div>Pass-through is how much of a 1pp move in that group's CPI turns up in the
        PCE deflator for the same spending. Shelter is 1.00 because PCE takes the number
        straight from the CPI; medical services is ~0.31 because it does not.</div>`;
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

  function downloadCsv() {
    const b = bridge();
    const cols = ["cpi", "pce", "gap"].concat(C.components).concat(["ccpi_proxy"]);
    const rows = [["date", "cpi_mom", "pce_mom"].concat(cols)
      .concat(["pce_implied_mom", "pce_actual_mom", "pce_implied_yoy", "pce_actual_yoy"])];
    for (let i = D.startIdx; i < C.dates.length; i++) {
      rows.push([C.dates[i], C.mom.cpi[i], C.mom.pce[i]]
        .concat(cols.map(c => C.table[c] ? C.table[c][i] : ""))
        .concat([b.monthly.implied[i], b.monthly.actual[i],
                 b.yoy.implied[i], b.yoy.actual[i]]));
    }
    const csv = rows.map(r => r.map(v => v == null ? "" : v).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `cpi_pce_${D.scope}.csv`;
    a.click();
  }

  // ---- register ------------------------------------------------------------
  window.CpiPceApp = { init };
  if (typeof ModelBar !== "undefined") {
    ModelBar.register({
      key: "cpipce",
      label: "CPI → PCE",
      viewId: "cpipce-view",
      sub: "The CPI is out and the PCE is not: what will it print? A group-level "
         + "bridge from the CPI and the producer prices BEA actually uses, plus "
         + "the exact accounting of why the two gauges differ at all.",
      init,
    });
  }
})();
