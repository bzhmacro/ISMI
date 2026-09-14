/* Wages, indexation and the spiral gain — the fifth model in the interactive site.

   Self-contained controller for #wage-view. Everything is recomputed in the
   browser from data/wage.json by wage_engine.js, the parity-tested twin of
   src/ism/wage_engine.py: move a control and the equations are re-estimated,
   not re-plotted.

   What you can change, and why each control is here:

     * the four channel elasticities. lambda, the indexation intensity, is not
       measured — it is built by weighting documented coverage shares by an
       assumed pass-through per channel (0.90 for a contractual escalator, 1.00
       for statutory public pay, 0.35 for a minimum-wage-benchmarked agreement,
       0.30 for a formal inflation reference). Those four numbers carry the
       whole institutional story, so they are the first thing you should be
       able to disagree with. Set the minimum-wage channel to zero and watch
       France fall out of the catch-up region.
     * the anchoring gain q. Trend inflation is a fixed-gain local-level filter;
       q = 0 is a perfectly anchored central bank and large q is no anchor at
       all. This is the observable counterpart of the parameter Bernanke and
       Blanchard estimate.
     * the horizon at which the gains are read. The long run is uninformative
       by construction — the homogeneity restriction sets long-run pass-through
       to one — so the question is always "how much, by when".
     * the income group, for the effective wage index. The bottom quartile
       takes 39% of its income from indexed benefits in the United States and
       52% in Germany; the top quartile takes none.
     * the simulator's fiscal and monetary dials, which is where the feedback
       loop the paper is about actually closes. */

(() => {
  const D = {
    country: "US", view: "gain", group: "q1",
    lags: 4, anchorQ: 0.05, horizon: 12,
    el: { automatic: 0.90, public: 1.00, minwage: 0.35, benchmark: 0.30 },
    sim: { lam: 0.10, phiE: 0.0, mpc: 0.30, taylor: 0.5, shock: 25, shockLen: 4 },
    inited: false,
  };

  let DATA = null, FIT = null, DIRTY = true;

  // bzhmacro house tokens — the same palette the other four models use.
  const PLOT_BG = "#161D2C", GRID = "#2A3448", INK = "#EDE6D6";
  const SERIES = {
    US: "#f5a623", UK: "#4c9aff", FR: "#d05ce3", DE: "#3fb950",
    BE: "#f5605a", IT: "#c9b458", ES: "#8b98a5",
  };
  const ACCENT = "#f5a623", COOL = "#4c9aff", WARM = "#f5605a",
        GREEN = "#3fb950", MUTED = "#8b98a5";
  const $ = id => document.getElementById(id);
  const W = () => window.WageEngine;

  const MODELLED = ["US", "UK", "FR", "DE"];
  const REFERENCE = ["BE", "IT", "ES"];

  // ---- init --------------------------------------------------------------
  async function init() {
    D.inited = true;
    try {
      const res = await fetch("data/wage.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      DATA = await res.json();
    } catch (e) {
      $("w-chart").innerHTML =
        `<div style="padding:24px;color:#f0d28a">Could not load <code>data/wage.json</code>.
         Run <code>python scripts/build_wage.py</code> then
         <code>python scripts/export_wage_data.py</code>, and redeploy. (${e})</div>`;
      return;
    }
    buildControls();
    render();
  }

  const C = code => DATA.countries[code];
  const dates = code => C(code).dates.map(d => new Date(d));

  // ---- recomputation -----------------------------------------------------
  /* Rebuild lambda from the coverage shares under the current elasticities,
     re-filter trend inflation under the current anchoring gain, and refit.
     Everything downstream reads from here. */
  function panelFor(code) {
    const c = C(code), s = c.series;
    const cov = {};
    for (const k of ["automatic", "public", "minwage", "benchmark"])
      if (s["cov_" + k]) cov[k] = s["cov_" + k];
    const lambda = Object.keys(cov).length
      ? W().indexationIntensity(cov, D.el) : s.lambda;
    const pistar = W().trendInflation(s.gp, D.anchorQ);
    return {
      gw: s.gw, gp: s.gp, slack: s.slack, catchup: s.catchup,
      gpty: s.gpty, dmw: s.dmw, grpe: s.grpe, grpf: s.grpf, h: s.h_disc || s.h,
      lambda, pistar,
    };
  }

  function recompute() {
    if (!DIRTY && FIT) return FIT;
    const cfg = { lags: D.lags, anchorQ: D.anchorQ, homogeneity: true };
    const panels = {};
    for (const code of Object.keys(DATA.countries)) panels[code] = panelFor(code);
    const panelFit = W().fitPanelWageEquation(panels, cfg, true);
    const price = {}, gain = {}, M = {};
    for (const code of Object.keys(panels)) {
      const pf = W().fitPriceEquation(panels[code], cfg);
      price[code] = pf;
      if (pf) {
        M[code] = W().wageToPriceGain(pf, D.lags, D.horizon);
        // Country-specific on BOTH sides: M from this country's price
        // equation, Lambda from its own wage dynamics with the common
        // catch-up coefficients.
        gain[code] = panelFit
          ? W().spiralGain(panelFit, pf, panels[code].lambda,
                           { p: D.lags, horizon: D.horizon, country: code })
          : null;
      }
    }
    FIT = { panels, panelFit, price, gain, M };
    DIRTY = false;
    return FIT;
  }

  const mark = () => { DIRTY = true; };

  // ---- controls ----------------------------------------------------------
  function seg(host, items, current, onPick) {
    const el = $(host);
    if (!el) return;
    el.innerHTML = "";
    for (const it of items) {
      const b = document.createElement("button");
      b.textContent = it.label;
      b.className = "segbtn" + (it.key === current ? " active" : "");
      if (it.title) b.title = it.title;
      b.addEventListener("click", () => { onPick(it.key); render(); });
      el.appendChild(b);
    }
  }

  function slider(host, opts, onChange) {
    const el = $(host);
    if (!el) return;
    el.innerHTML = "";
    const lab = document.createElement("label");
    lab.className = "mini";
    lab.innerHTML = `${opts.label} <b id="${host}-val">${opts.fmt(opts.value)}</b>`;
    const input = document.createElement("input");
    input.type = "range";
    input.min = opts.min; input.max = opts.max; input.step = opts.step;
    input.value = opts.value;
    input.addEventListener("input", () => {
      const v = parseFloat(input.value);
      $(`${host}-val`).textContent = opts.fmt(v);
      onChange(v);
      render();
    });
    el.appendChild(lab);
    el.appendChild(input);
  }

  function buildControls() {
    seg("w-country",
      MODELLED.map(k => ({ key: k, label: C(k).name }))
        .concat(REFERENCE.map(k => ({
          key: k, label: C(k).name,
          title: "Reference country: not the paper's subject, but where the "
               + "indexation interaction is identified" }))),
      D.country, k => { D.country = k; });

    seg("w-view", [
      { key: "gain", label: "Spiral gain",
        title: "G = Lambda x M, the product of price-to-wage catch-up and wage-to-price pass-through" },
      { key: "ewi", label: "Effective wage" },
      { key: "index", label: "Indexation" },
      { key: "sim", label: "Simulator" },
      { key: "schemes", label: "Handouts" },
    ], D.view, k => { D.view = k; });

    seg("w-group", [
      { key: "q1", label: "Bottom quartile" }, { key: "q2", label: "Q2" },
      { key: "q3", label: "Q3" }, { key: "q4", label: "Top quartile" },
      { key: "all", label: "Average" },
    ], D.group, k => { D.group = k; });

    seg("w-lags", [2, 4, 6].map(n => ({ key: n, label: `${n} lags` })),
        D.lags, k => { D.lags = k; mark(); });

    seg("w-horizon", [
      { key: 4, label: "1 year" }, { key: 8, label: "2 years" },
      { key: 12, label: "3 years" }, { key: 20, label: "5 years" },
    ], D.horizon, k => { D.horizon = k; mark(); });

    slider("w-anchor", {
      label: "expectations anchoring q =", value: D.anchorQ,
      min: 0, max: 1, step: 0.01, fmt: v => v.toFixed(2),
    }, v => { D.anchorQ = v; mark(); });

    const chans = [
      ["automatic", "contractual escalator"],
      ["public", "statutory public pay"],
      ["minwage", "minimum-wage benchmark"],
      ["benchmark", "formal inflation reference"],
    ];
    for (const [k, lab] of chans) {
      slider(`w-el-${k}`, {
        label: `${lab} e =`, value: D.el[k],
        min: 0, max: 1.2, step: 0.05, fmt: v => v.toFixed(2),
      }, v => { D.el[k] = v; mark(); });
    }

    const sims = [
      ["lam", "indexation intensity &lambda; =", 0, 1, 0.01, v => v.toFixed(2)],
      ["phiE", "fiscal response &phi;<sub>e</sub> =", 0, 2, 0.05, v => v.toFixed(2)],
      ["mpc", "share of transfers reaching demand =", 0, 1, 0.05, v => v.toFixed(2)],
      ["taylor", "monetary response =", 0, 2, 0.05, v => v.toFixed(2)],
      ["shock", "energy price shock, pp =", 0, 60, 5, v => v.toFixed(0)],
    ];
    for (const [k, lab, mn, mx, st, fmt] of sims) {
      slider(`w-sim-${k}`, { label: lab, value: D.sim[k], min: mn, max: mx, step: st, fmt },
             v => { D.sim[k] = v; });
    }
  }

  // ---- plot helpers ------------------------------------------------------
  const LAYOUT = extra => Object.assign({
    paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG,
    font: { color: INK, family: "IBM Plex Sans, system-ui, sans-serif", size: 12 },
    margin: { l: 56, r: 20, t: 28, b: 44 },
    xaxis: { gridcolor: GRID, zerolinecolor: GRID },
    yaxis: { gridcolor: GRID, zerolinecolor: GRID },
    hovermode: "x unified",
    legend: { orientation: "h", y: -0.16, font: { size: 11 } },
    showlegend: true,
  }, extra || {});

  const CFG = { displayModeBar: false, responsive: true };

  function draw(id, traces, layout) {
    const host = $(id);
    if (!host || typeof Plotly === "undefined") return;
    Plotly.react(host, traces, LAYOUT(layout), CFG);
  }

  // ---- views -------------------------------------------------------------
  function viewGain() {
    const f = recompute();
    const traces = [];
    for (const code of MODELLED.concat(REFERENCE)) {
      const g = f.gain[code];
      if (!g) continue;
      traces.push({
        x: dates(code), y: g.map(r => (r ? r.G : null)),
        type: "scatter", mode: "lines", name: C(code).name,
        line: { color: SERIES[code], width: code === D.country ? 2.6 : 1.3,
                dash: C(code).modelled ? "solid" : "dot" },
        opacity: code === D.country ? 1 : 0.75,
      });
    }
    traces.push({
      x: [new Date("1960-01-01"), new Date("2026-07-01")], y: [1, 1],
      type: "scatter", mode: "lines", name: "spiral threshold",
      line: { color: WARM, width: 1, dash: "dash" }, hoverinfo: "skip",
    });
    draw("w-chart", traces, {
      title: { text: "Spiral gain G = Λ(λ) × M", font: { size: 14 } },
      yaxis: { gridcolor: GRID, zerolinecolor: "#4a5668", title: "gain" },
    });

    // The Lambda(lambda) schedule: the paper's central object, drawn as a
    // schedule rather than a number because lambda is the thing in dispute.
    // One schedule per country: the catch-up coefficients are common, but
    // each country's own persistence propagates them differently, so Λ(λ) is
    // a family of lines rather than one.
    const xs = [];
    for (let i = 0; i <= 40; i++) xs.push(i / 40);
    const schedules = MODELLED.concat(REFERENCE).map(code => ({
      x: xs, type: "scatter", mode: "lines", name: C(code).name,
      y: xs.map(l => (f.panelFit
        ? W().priceToWageGain(f.panelFit, l, D.lags, D.horizon, code) : null)),
      line: { color: SERIES[code], width: code === D.country ? 2.6 : 1.2,
              dash: C(code).modelled ? "solid" : "dot" },
      opacity: code === D.country ? 1 : 0.7,
    }));
    const pts = MODELLED.concat(REFERENCE).map(code => {
      const lam = f.panels[code].lambda;
      const last = lam[lam.length - 1];
      return { code, lam: last,
               L: f.panelFit
                 ? W().priceToWageGain(f.panelFit, last, D.lags, D.horizon, code) : null };
    });
    draw("w-chart2", schedules.concat([
      { x: xs, y: xs.map(() => 0), type: "scatter", mode: "lines",
        name: "no catch-up", line: { color: MUTED, width: 1, dash: "dot" },
        hoverinfo: "skip" },
      { x: pts.map(p => p.lam), y: pts.map(p => p.L), text: pts.map(p => p.code),
        type: "scatter", mode: "markers+text", name: "today",
        textposition: "top center", textfont: { size: 10 },
        marker: { size: 9, color: pts.map(p => SERIES[p.code]) } },
    ]), {
      title: { text: "Three-year catch-up Λ(λ), one schedule per country",
               font: { size: 14 } },
      xaxis: { gridcolor: GRID, title: "λ — share of the wage bill indexed to past prices" },
      yaxis: { gridcolor: GRID, zerolinecolor: "#4a5668",
               title: "pp of wage growth per pp of real-wage gap" },
    });

    const code = D.country, g = f.gain[code];
    const last = g ? g[g.length - 1] : null;
    const lam = f.panels[code].lambda;
    const dL = f.panelFit
      ? W().priceToWageGain(f.panelFit, 1, D.lags, D.horizon, code)
        - W().priceToWageGain(f.panelFit, 0, D.lags, D.horizon, code)
      : null;
    stats([
      ["λ now", lam[lam.length - 1], v => v.toFixed(3)],
      ["Λ price → wage", last ? last.Lambda : null, v => v.toFixed(3)],
      ["M wage → price", f.M[code], v => v.toFixed(3)],
      ["G spiral gain", last ? last.G : null, v => v.toFixed(3)],
      ["∂Λ/∂λ", dL, v => v.toFixed(3)],
    ]);
    note(`The wage equation is <strong>partially pooled</strong>: each country keeps its `
       + `own persistence, trend weight and slack response — a Chow test rejects pooling `
       + `them at F = 2.9 on (120, 1030) — while the catch-up block and its interaction `
       + `with λ are common, because λ barely moves inside a country and the cross-section `
       + `is the only place that effect can be identified. `
       + `Λ is the share of a real-wage shortfall recovered within ${D.horizon / 4} `
       + `year${D.horizon === 4 ? "" : "s"}; M is the share of a wage impulse that reaches `
       + `prices over the same horizon. Their product is the gain of one turn of the loop. `
       + `A gain above one is self-sustaining; no country in this panel reaches it, and only `
       + `Belgium and Italy under the scala mobile get close. Belgium is the instructive case: `
       + `it has the highest λ in the panel and the lowest M, so full pass-through into wages `
       + `produces almost none back out into prices.`);
  }

  function viewEwi() {
    const f = recompute();
    const code = D.country, c = C(code), s = c.series;
    const sh = shareFor(code, D.group);
    const comp = {
      wage: s.lvl_wage, minwage: s.lvl_minwage,
      benefit: s.lvl_benefit, handout: s.lvl_handout,
    };
    const ewi = W().effectiveWageIndex(comp, sh);
    const base = c.dates.indexOf("2019-10-01");
    const real = W().realEffectiveWage(ewi, s.lvl_price, s.wedge, base < 0 ? 0 : base);
    const mkt = s.lvl_wage.map((v, i) =>
      (v != null && s.lvl_price[i] ? v / s.lvl_price[i] : null));
    const b = base >= 0 ? mkt[base] : mkt.find(v => v != null);
    const mktIdx = mkt.map(v => (v != null && b ? 100 * v / b : null));
    const X = dates(code);

    draw("w-chart", [
      { x: X, y: real.real, type: "scatter", mode: "lines",
        name: "effective wage, real", line: { color: ACCENT, width: 2.6 } },
      { x: X, y: real.real_subsidy_neutral, type: "scatter", mode: "lines",
        name: "effective wage, subsidy-neutral",
        line: { color: COOL, width: 1.8, dash: "dash" } },
      { x: X, y: mktIdx, type: "scatter", mode: "lines",
        name: "market wage, real", line: { color: MUTED, width: 1.6 } },
    ], {
      title: { text: `${c.name} — real effective wage, ${groupLabel(D.group)} (2019 Q4 = 100)`,
               font: { size: 14 } },
      xaxis: { gridcolor: GRID, range: ["2015-01-01", X[X.length - 1]] },
      yaxis: { gridcolor: GRID, title: "index" },
    });

    // The components, so the reader can see which part of income moved.
    draw("w-chart2", [
      { x: X, y: comp.wage, name: "market wage", type: "scatter", mode: "lines",
        line: { color: MUTED, width: 1.6 } },
      { x: X, y: comp.minwage, name: "statutory floor", type: "scatter", mode: "lines",
        line: { color: GREEN, width: 1.6 } },
      { x: X, y: comp.benefit, name: "indexed benefits", type: "scatter", mode: "lines",
        line: { color: COOL, width: 1.6 } },
      { x: X, y: s.lvl_price, name: "consumer prices", type: "scatter", mode: "lines",
        line: { color: WARM, width: 1.6, dash: "dot" } },
      { x: X, y: comp.handout, name: "handouts (right)", type: "scatter", mode: "lines",
        yaxis: "y2", line: { color: ACCENT, width: 2 } },
    ], {
      title: { text: "Components (2019 Q4 = 100); handouts on the right axis",
               font: { size: 14 } },
      xaxis: { gridcolor: GRID, range: ["2015-01-01", X[X.length - 1]] },
      yaxis: { gridcolor: GRID, title: "index" },
      yaxis2: { overlaying: "y", side: "right", gridcolor: "rgba(0,0,0,0)",
                title: "handout index" },
    });

    const at = d => { const i = c.dates.indexOf(d); return i < 0 ? null : i; };
    const i22 = at("2022-10-01"), iNow = real.real.length - 1;
    stats([
      ["real, 2022 Q4", i22 != null ? real.real[i22] : null, v => v.toFixed(1)],
      ["subsidy-neutral, 2022 Q4",
        i22 != null ? real.real_subsidy_neutral[i22] : null, v => v.toFixed(1)],
      ["market wage, 2022 Q4", i22 != null ? mktIdx[i22] : null, v => v.toFixed(1)],
      ["real, latest", real.real[iNow], v => v.toFixed(1)],
    ]);
    note(`The effective wage adds the statutory floor, indexed benefits and one-off `
       + `payments to market earnings, weighted by this group's income composition. `
       + `The subsidy-neutral line deflates by the price index that would have been `
       + `recorded without caps, tariff shields and fuel-duty cuts — the gap between the `
       + `two lines is the part of measured real income that is a consequence of how the `
       + `support was delivered rather than of what households received.`);
  }

  function viewIndex() {
    const f = recompute();
    const traces = [];
    for (const code of MODELLED.concat(REFERENCE)) {
      traces.push({
        x: dates(code), y: f.panels[code].lambda, type: "scatter", mode: "lines",
        name: C(code).name,
        line: { color: SERIES[code], width: code === D.country ? 2.6 : 1.3,
                dash: C(code).modelled ? "solid" : "dot" },
      });
    }
    draw("w-chart", traces, {
      title: { text: "Indexation intensity λ — the share of the wage bill that moves with past prices",
               font: { size: 14 } },
      yaxis: { gridcolor: GRID, title: "λ", range: [0, 1.05] },
    });

    const code = D.country, s = C(code).series, X = dates(code);
    const chans = [
      ["cov_automatic", "contractual escalator", ACCENT],
      ["cov_public", "statutory public pay", GREEN],
      ["cov_minwage", "minimum-wage benchmark", COOL],
      ["cov_benchmark", "formal inflation reference", MUTED],
    ];
    draw("w-chart2", chans.filter(([k]) => s[k]).map(([k, lab, col]) => ({
      x: X, y: s[k], name: lab, type: "scatter", mode: "lines",
      stackgroup: "one", line: { width: 0.6, color: col },
      fillcolor: col + "55",
    })), {
      title: { text: `${C(code).name} — coverage by channel (shares, before elasticities)`,
               font: { size: 14 } },
      yaxis: { gridcolor: GRID, title: "share of employees" },
    });

    const lam = f.panels[code].lambda;
    const yr = y => {
      const i = C(code).dates.findIndex(d => d.startsWith(String(y)));
      return i < 0 ? null : lam[i];
    };
    stats([
      ["λ 1975", yr(1975), v => v.toFixed(3)],
      ["λ 1985", yr(1985), v => v.toFixed(3)],
      ["λ 2005", yr(2005), v => v.toFixed(3)],
      ["λ today", lam[lam.length - 1], v => v.toFixed(3)],
    ]);
    note(`Coverage shares are documented at the dates in `
       + `<code>config/indexation_coverage.csv</code>, every row sourced, and linearly `
       + `interpolated between them; λ weights them by the four elasticities above and `
       + `clips at one. The step in the United Kingdom in 1974 is the Heath government's `
       + `threshold agreements, which covered about a third of the workforce and fired `
       + `eleven times in twelve months. France's level is high and flat because the 1983 `
       + `désindexation ended general wage indexation but left the SMIC formula in force.`);
  }

  function viewSim() {
    const f = recompute();
    const code = D.country;
    const pf = f.price[code];
    if (!f.panelFit || !pf) { note("Not enough data to simulate this country."); return; }
    const sim = W().simulateLoop(f.panelFit, pf, {
      lam: D.sim.lam, anchorQ: D.anchorQ, phiE: D.sim.phiE, mpc: D.sim.mpc,
      taylor: D.sim.taylor, shock: D.sim.shock, shockLen: D.sim.shockLen,
      horizon: 24, p: D.lags, country: code,
    });
    const q = sim.quarter;
    draw("w-chart", [
      { x: q, y: sim.price_inflation, name: "price inflation", type: "scatter",
        mode: "lines", line: { color: WARM, width: 2.6 } },
      { x: q, y: sim.wage_growth, name: "wage growth", type: "scatter",
        mode: "lines", line: { color: ACCENT, width: 2.6 } },
      { x: q, y: sim.trend, name: "trend inflation", type: "scatter",
        mode: "lines", line: { color: COOL, width: 1.6, dash: "dash" } },
      { x: q, y: sim.real_wage, name: "real wage growth", type: "scatter",
        mode: "lines", line: { color: GREEN, width: 1.6 } },
    ], {
      title: { text: `${C(code).name} — response to a ${D.sim.shock}pp relative energy price shock`,
               font: { size: 14 } },
      xaxis: { gridcolor: GRID, title: "quarters after the shock" },
      yaxis: { gridcolor: GRID, zerolinecolor: "#4a5668",
               title: "deviation, percentage points" },
    });
    draw("w-chart2", [
      { x: q, y: sim.handout, name: "fiscal handout", type: "scatter", mode: "lines",
        line: { color: ACCENT, width: 2 }, fill: "tozeroy", fillcolor: ACCENT + "33" },
      { x: q, y: sim.slack, name: "labour-market slack opened by policy", type: "scatter",
        mode: "lines", line: { color: COOL, width: 2 } },
      { x: q, y: sim.catchup, name: "real-wage gap", type: "scatter", mode: "lines",
        line: { color: MUTED, width: 1.6, dash: "dot" } },
    ], {
      title: { text: "The policy response", font: { size: 14 } },
      xaxis: { gridcolor: GRID, title: "quarters after the shock" },
      yaxis: { gridcolor: GRID, zerolinecolor: "#4a5668" },
    });
    const peak = Math.max(...sim.price_inflation);
    const cum = sim.price_inflation.reduce((a, b) => a + b, 0) / 4;
    stats([
      ["peak inflation", peak, v => v.toFixed(2) + "pp"],
      ["cumulative, 6 years", cum, v => v.toFixed(1) + "pp"],
      ["trough real wage", Math.min(...sim.real_wage), v => v.toFixed(2) + "pp"],
      ["peak handout", Math.max(...sim.handout), v => v.toFixed(2) + "% of income"],
    ]);
    note(`The fiscal dial is the reaction function of Eq. (W9): how much of household `
       + `income a government hands out per percentage point of inflation above trend. `
       + `Turning it up with the monetary dial at zero is the configuration the paper `
       + `warns about. The monetary dial is written as slack opened per point of excess `
       + `inflation rather than as an interest rate, because the estimated wage equation `
       + `takes slack and not the policy rate — a Taylor rule here would need an IS curve `
       + `that has not been estimated.`);
  }

  function viewSchemes() {
    const code = D.country;
    const rows = (DATA.schemes || []).filter(r => r.country === code);
    const host = $("w-table");
    if (!rows.length) {
      host.innerHTML = `<p class="muted">No schemes recorded for ${C(code).name}. `
        + `The database covers 2021-2026 and only the countries whose energy and `
        + `cost-of-living packages were large enough to move household income.</p>`;
    } else {
      const body = rows.map(r => `<tr>
        <td>${r.scheme}</td>
        <td><span class="kind kind-${r.kind}">${r.kind}</span></td>
        <td>${r.start} → ${r.end}</td>
        <td class="num">${r.cost_bn ? Number(r.cost_bn).toFixed(1) + " " + r.currency : "—"}</td>
        <td>${r.amount}</td>
        <td class="src">${r.source}</td></tr>`).join("");
      host.innerHTML = `<table class="tbl"><thead><tr>
        <th>Scheme</th><th>Kind</th><th>In force</th><th class="num">Cost, bn</th>
        <th>Design</th><th>Source</th></tr></thead><tbody>${body}</tbody></table>`;
    }

    const s = C(code).series, X = dates(code);
    draw("w-chart", [
      { x: X, y: s.wedge, name: "price-measure wedge", type: "bar",
        marker: { color: s.wedge.map(v => (v < 0 ? COOL : WARM)) } },
    ], {
      title: { text: `${C(code).name} — contribution of price-based support to measured inflation`,
               font: { size: 14 } },
      xaxis: { gridcolor: GRID, range: ["2021-01-01", "2026-07-01"] },
      yaxis: { gridcolor: GRID, zerolinecolor: "#4a5668", title: "percentage points" },
      showlegend: false,
    });
    draw("w-chart2", [
      { x: X, y: s.h_disc || s.h, name: "transfer impulse, cyclically adjusted",
        type: "scatter", mode: "lines", line: { color: ACCENT, width: 2 } },
      { x: X, y: s.transfer_share, name: "transfers, % of disposable income (right)",
        type: "scatter", mode: "lines", yaxis: "y2",
        line: { color: MUTED, width: 1.6 } },
    ], {
      title: { text: "Government cash transfers to households", font: { size: 14 } },
      yaxis: { gridcolor: GRID, zerolinecolor: "#4a5668", title: "pp of income, 4-quarter change" },
      yaxis2: { overlaying: "y", side: "right", gridcolor: "rgba(0,0,0,0)" },
    });
    stats([]);
    note(`A price measure lowers measured inflation while it is in force and raises it `
       + `when it expires; an income measure never enters the index at all. Two packages `
       + `of identical cost therefore leave very different traces in the statistics, and `
       + `in every price-indexed contract downstream of them. Germany's `
       + `Inflationsausgleichsprämie is the awkward case: it is a payment through the `
       + `payslip, so it raises measured wage growth without raising the wage base.`);
  }

  // ---- chrome ------------------------------------------------------------
  function shareFor(code, group) {
    const row = (DATA.shares || []).find(r => r.country === code && r.group === group);
    if (!row) return { wage: 0.7, minwage: 0.05, benefit: 0.24, handout: 0.01 };
    return { wage: +row.wage, minwage: +row.minwage,
             benefit: +row.benefit, handout: +row.handout };
  }

  const groupLabel = g => ({
    q1: "bottom quartile", q2: "second quartile", q3: "third quartile",
    q4: "top quartile", all: "all households",
  }[g] || g);

  function stats(items) {
    const host = $("w-stats");
    if (!host) return;
    host.innerHTML = items.map(([lab, v, fmt]) =>
      `<div class="stat"><span class="stat-label">${lab}</span>
       <span class="stat-value">${v == null || !isFinite(v) ? "—" : fmt(v)}</span></div>`
    ).join("");
  }

  function note(html) {
    const host = $("w-note");
    if (host) host.innerHTML = html;
  }

  function toggleControls() {
    const show = (id, on) => { const e = $(id); if (e) e.hidden = !on; };
    show("w-group-ctl", D.view === "ewi");
    show("w-sim-ctl", D.view === "sim");
    show("w-el-ctl", D.view === "gain" || D.view === "index");
    show("w-fit-ctl", D.view !== "schemes");
    show("w-table", D.view === "schemes");
    show("w-chart2", true);
  }

  function render() {
    if (!DATA) return;
    buildControls();
    toggleControls();
    if (D.view === "gain") viewGain();
    else if (D.view === "ewi") viewEwi();
    else if (D.view === "index") viewIndex();
    else if (D.view === "sim") viewSim();
    else viewSchemes();
    const f = FIT;
    const st = $("w-status");
    if (st && f && f.panelFit) {
      st.textContent = `pooled wage equation: ${f.panelFit.nobs} country-quarters, `
        + `R² ${f.panelFit.r2.toFixed(3)}; Σ catch-up × λ = `
        + `${f.panelFit.sumOf("cux_l").toFixed(3)}`;
    }
  }

  // ---- register ----------------------------------------------------------
  window.WageApp = { init };
  if (typeof ModelBar !== "undefined") {
    ModelBar.register({
      key: "wage",
      label: "Wages & indexation",
      viewId: "wage-view",
      sub: "Who is indexed to what, how much of a real-wage loss is recovered, "
         + "and whether the loop from prices to incomes and back closes — with "
         + "statutory wage floors, indexed benefits and one-off handouts "
         + "counted as part of the wage.",
      init,
      refresh: render,
    });
  }
})();
