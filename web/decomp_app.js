/* Supply/demand decomposition explorer (Shapiro 2022-18) — the second model in
   the interactive site. Self-contained controller for the #decomp-view; the
   top-level Model toggle (ISM <-> Supply/Demand) is wired here too.

   Like the ISM app, the heavy modelling runs CLIENT-SIDE: data/decomp.json ships
   the raw log-price / log-quantity / weight panels, and decomp_worker.js
   (running decomp_engine.js, a parity-tested port of src/ism/decomp_engine.py)
   recomputes the decomposition whenever a control changes. */

(() => {
  const D = { scope: "headline", J: 12, W: 120, precisionCut: 0, view: "contrib_yoy",
              startIdx: 0, author: true, headline: true, selectedDate: null, inited: false };
  let DATA = null, X = [], WORKER = null, READY = false, LIVE = new Set();
  let REQ = 0, REQ_KEY = "", RESULT = null, DEB = null;
  const EXCLUDED = {};

  const PLOT_BG = "#171e26", GRID = "#243240", INK = "#e6edf3", MUTED = "#8b98a5";
  const SUP = "#f5605a", DEM = "#27406b", DEMI = "#4c9aff", AMB = "#c9b458", TOT = "#e6edf3";
  const $ = id => document.getElementById(id);

  // ---- model toggle (ISM <-> decomp) -------------------------------------
  function setupModelToggle() {
    const host = $("model");
    if (!host) return;
    const models = [["ism", "Inflation Shock Momentum"], ["decomp", "Supply vs Demand"]];
    host.innerHTML = "";
    models.forEach(([key, label]) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.setAttribute("aria-pressed", String(key === "ism"));
      b.onclick = () => {
        [...host.children].forEach(c => c.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        switchModel(key);
      };
      host.appendChild(b);
    });
  }

  function switchModel(model) {
    const ism = $("ism-view"), dec = $("decomp-view");
    const sub = $("model-sub");
    if (model === "decomp") {
      ism.hidden = true; dec.hidden = false;
      if (sub) sub.textContent =
        "Decomposing inflation into supply- and demand-driven contributions " +
        "(Shapiro 2022-18; Canada: Bank of Canada SAP 2026-33). Each category-" +
        "period is signed from the reduced-form price & quantity residuals; " +
        "recomputed live in your browser.";
      if (!D.inited) init();
      else requestCompute(0);
    } else {
      dec.hidden = true; ism.hidden = false;
      if (sub) sub.textContent =
        "Replication of Lansing & Shapiro (2026): the share of categories with " +
        "sustained inflation surprises, recomputed live in your browser.";
    }
  }

  // ---- init --------------------------------------------------------------
  async function init() {
    D.inited = true;
    try {
      const res = await fetch("data/decomp.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      DATA = await res.json();
    } catch (e) {
      $("d-chart").innerHTML =
        `<div style="padding:24px;color:#f0d28a">Could not load <code>data/decomp.json</code>.
         Run <code>python scripts/export_decomp_data.py</code>, then redeploy. (${e})</div>`;
      return;
    }
    D.scope = (DATA.meta && DATA.meta.default_scope) || "headline";
    if (DATA.meta && DATA.meta.demo) {
      const ban = $("d-demo-banner");
      if (ban) { ban.hidden = false; ban.textContent =
        "⚠ DEMO data: category quantity is proxied as nominal/price. Rerun the exporter with BEA table U20403 for the exact series."; }
    }
    setupWorker();
    buildScopeSeg();
    buildParamControls();
    setupToggles();
    setupViewSeg();
    applyScope();
    setupDownload();
    requestCompute(0);
  }

  function scope() { return DATA.scopes[D.scope]; }
  function ui() { return (DATA.meta && DATA.meta.ui) || {}; }
  function exSet() { return (EXCLUDED[D.scope] = EXCLUDED[D.scope] || new Set()); }

  // per-scope frequency + baseline params (12/12/120 monthly US, 4/4/40 quarterly CA)
  function sconf() {
    const s = scope() || {};
    const bp = s.baseline_params || {};
    return { ppy: s.ppy || 12, J0: bp.J || 12, W0: bp.W || 120, ui: s.ui || ui(),
             quarterly: (s.ppy || 12) === 4 };
  }

  // ---- worker ------------------------------------------------------------
  function setupWorker() {
    if (typeof Worker === "undefined") return;
    const panels = {};
    for (const [name, s] of Object.entries(DATA.scopes)) if (s.panel) panels[name] = s.panel;
    try { WORKER = new Worker("decomp_worker.js"); } catch (e) { WORKER = null; return; }
    WORKER.onerror = () => { WORKER = null; READY = false; setStatus("live compute unavailable — showing baseline", true); render(); };
    WORKER.onmessage = e => {
      const m = e.data;
      if (m.type === "ready") { READY = true; LIVE = new Set(m.scopes); requestCompute(0); return; }
      if (m.type === "error") { setStatus(`compute error: ${m.message}`, true); return; }
      if (m.type === "result") {
        if (m.id !== REQ) return;
        RESULT = { key: REQ_KEY, scope: m.scope, res: m };
        setStatus(`computed in your browser · ${m.ms} ms`);
        render();
      }
    };
    WORKER.postMessage({ type: "init", panels });
  }

  function liveReady() { return !!(WORKER && READY && LIVE.has(D.scope)); }
  function paramsKey() {
    const ex = [...exSet()].sort((a, b) => a - b).join(".");
    return `${D.scope}|J${D.J}|W${D.W}|c${D.precisionCut}|x${ex}`;
  }
  function isBaseline() {
    const c = sconf();
    return D.J === c.J0 && D.W === c.W0 && D.precisionCut === 0 && exSet().size === 0;
  }

  // result selection: fresh worker result > precomputed baseline
  function currentResult() {
    if (RESULT && RESULT.scope === D.scope && RESULT.key === paramsKey()) return RESULT.res;
    if (isBaseline() && scope().baseline) return baselineAsResult();
    if (RESULT && RESULT.scope === D.scope) return RESULT.res;     // stale, refresh inflight
    if (scope().baseline) return baselineAsResult();
    return null;
  }
  function baselineAsResult() {
    const b = scope().baseline;
    const drivers = Object.entries(b.drivers || {}).map(([date, contrib]) => ({ date, contrib }));
    return {
      supply: b.contrib.supply, demand: b.contrib.demand, ambiguous: b.contrib.ambiguous, total: b.contrib.total,
      supply_yoy: b.contrib_yoy.supply, demand_yoy: b.contrib_yoy.demand,
      ambiguous_yoy: b.contrib_yoy.ambiguous, total_yoy: b.contrib_yoy.total,
      sh_supply: b.shares.supply, sh_demand: b.shares.demand, sh_ambiguous: b.shares.ambiguous,
      _baselineDrivers: drivers,
    };
  }

  function requestCompute(delay = 150) {
    if (!liveReady()) { render(); return; }
    const key = paramsKey();
    if (RESULT && RESULT.scope === D.scope && RESULT.key === key) { render(); return; }
    render();  // instant paint with baseline/stale while computing
    clearTimeout(DEB);
    DEB = setTimeout(() => {
      REQ += 1; REQ_KEY = key;
      WORKER.postMessage({ type: "compute", id: REQ, scope: D.scope,
        params: { J: D.J, W: D.W, h: 0, ppy: sconf().ppy, precisionCut: D.precisionCut, excluded: [...exSet()] } });
      setStatus("computing…");
    }, delay);
  }

  function setStatus(t, warn) { const el = $("d-status"); if (!el) return; el.textContent = t || ""; el.classList.toggle("warn", !!warn); }

  // ---- controls ----------------------------------------------------------
  function seg(id, values, current, label, onPick, decorate) {
    const host = $(id); if (!host) return; host.innerHTML = "";
    values.forEach(v => {
      const b = document.createElement("button");
      b.textContent = label(v);
      b.setAttribute("aria-pressed", String(v === current));
      b.onclick = () => { [...host.children].forEach(c => c.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); onPick(v); };
      if (decorate) decorate(b, v);   // optional per-button styling / tooltip
      host.appendChild(b);
    });
  }

  // Scopes whose national-accounts cross-section is too small for the
  // supply/demand split to be meaningful — greyed out (but still selectable),
  // with a hover tooltip explaining the caveat. Keyed by scope name.
  const CAUTION_SOURCE = {
    jp: "Japan's quarterly national accounts",
    de: "Germany's quarterly national accounts",
  };

  function cautionText(n) {
    const sc = DATA.scopes[n] || {};
    const src = CAUTION_SOURCE[n];
    return `${src} break household consumption into only ${sc.n_categories || "a few"} `
      + `categories. The supply-vs-demand split needs a broad cross-section of `
      + `category prices and quantities, so with this few series the model isn't `
      + `reliable here — shown for completeness, read it as a coarse `
      + `goods-vs-services signal, not a real decomposition.`;
  }

  function buildScopeSeg() {
    const names = (DATA.meta && DATA.meta.scopes) || ["headline"];
    const label = n => (DATA.scopes[n] && DATA.scopes[n].tab) || (n[0].toUpperCase() + n.slice(1));
    seg("d-scope", names, D.scope, label,
        n => { D.scope = n; D.selectedDate = null; applyScope(); requestCompute(0); },
        (b, n) => {
          if (!(n in CAUTION_SOURCE)) return;
          b.classList.add("caution");
          b.setAttribute("title", cautionText(n));   // native fallback
          const tip = document.createElement("span");
          tip.className = "tip"; tip.textContent = cautionText(n);
          b.appendChild(tip);
        });
  }

  // J-lags seg + W slider depend on the scope's frequency (monthly vs quarterly),
  // so they are (re)built on every scope switch from that scope's ui/baseline.
  function applyScopeParams() {
    const c = sconf();
    D.J = c.J0; D.W = c.W0;
    seg("d-lags", c.ui.var_lags || [3, 12, 24], D.J, v => `${v} lags`,
        v => { D.J = v; D.selectedDate = null; requestCompute(0); });
    const W = $("d-W"), wcfg = c.ui.window || { min: 60, max: 240, step: 6, default: 120 };
    W.min = wcfg.min; W.max = wcfg.max; W.step = wcfg.step; W.value = D.W;
    $("d-W-label").textContent = D.W;
    const unit = $("d-W-unit"); if (unit) unit.textContent = c.quarterly ? "quarters" : "months";
    W.oninput = () => { D.W = +W.value; $("d-W-label").textContent = D.W; D.selectedDate = null; requestCompute(180); };
  }

  function buildParamControls() {
    const u = ui();
    const C = $("d-cut"), ccfg = u.precision_cut || { min: 0, max: 0.3, step: 0.05, default: 0 };
    C.min = ccfg.min; C.max = ccfg.max; C.step = ccfg.step; C.value = D.precisionCut;
    $("d-cut-label").textContent = D.precisionCut === 0 ? "0 (binary)" : D.precisionCut.toFixed(2);
    C.oninput = () => { D.precisionCut = +C.value; $("d-cut-label").textContent = D.precisionCut === 0 ? "0 (binary)" : D.precisionCut.toFixed(2); D.selectedDate = null; requestCompute(150); };
  }

  function setupViewSeg() {
    const views = [["contrib_yoy", "Contributions (y/y)"], ["contrib_monthly", "Contributions (monthly)"], ["shares", "Shares of basket"]];
    const host = $("d-view"); host.innerHTML = "";
    views.forEach(([k, lab]) => {
      const b = document.createElement("button"); b.textContent = lab;
      b.setAttribute("aria-pressed", String(k === D.view));
      b.onclick = () => { [...host.children].forEach(c => c.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); D.view = k; render(); };
      host.appendChild(b);
    });
  }

  function setupToggles() {
    const a = $("d-t-author"); if (a) { a.checked = D.author; a.onchange = () => { D.author = a.checked; render(); }; }
    const h = $("d-t-headline"); if (h) { h.checked = D.headline; h.onchange = () => { D.headline = h.checked; render(); }; }
  }

  function applyScope() {
    const s = scope();
    applyScopeParams();
    X = s.dates.map(d => new Date(d + "-01"));
    const a = $("d-t-author"), hasA = !!s.author;
    if (a) { a.disabled = !hasA; const lab = a.closest(".chk"); if (lab) { lab.style.opacity = hasA ? "" : ".4"; lab.title = hasA ? "" : "No FRBSF author overlay in this data file"; } if (!hasA) a.checked = false; D.author = a.checked; }
    const r = $("d-start"); r.min = 0; r.max = s.dates.length - 1;
    const base = s.baseline ? s.baseline.contrib_yoy.total : null;
    let first = base ? base.findIndex(v => v != null) : 0; if (first < 0) first = 0;
    D.startIdx = first; r.value = first;
    r.oninput = () => { D.startIdx = +r.value; render(); };
    $("d-meta").textContent = `${s.n_categories} categories · ${s.dates[0]}–${s.dates[s.dates.length - 1]}`;
    const note = $("d-note"); if (note) note.textContent = s.note || "";
    buildCatList();
  }

  // ---- categories --------------------------------------------------------
  function buildCatList() {
    const s = scope(), host = $("d-catlist"); if (!host) return; host.innerHTML = "";
    const ex = exSet();
    s.categories.forEach((c, i) => {
      const row = document.createElement("label"); row.className = "catrow"; row.title = c.label;
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !ex.has(i); cb.dataset.idx = i;
      cb.onchange = () => { if (cb.checked) ex.delete(i); else ex.add(i); updateCatSummary(); requestCompute(250); };
      const sp = document.createElement("span"); sp.textContent = c.label;
      row.appendChild(cb); row.appendChild(sp); host.appendChild(row);
    });
    const search = $("d-cat-search"); if (search) { search.value = ""; search.oninput = () => { const q = search.value.trim().toLowerCase(); [...host.children].forEach(r => r.classList.toggle("hidden", q && !r.title.toLowerCase().includes(q))); }; }
    updateCatSummary();
  }
  function updateCatSummary() { const s = scope(), t = s.categories.length; $("d-cat-summary").textContent = `${t - exSet().size}/${t} included`; }

  // ---- helpers -----------------------------------------------------------
  function sliceFrom(a) { return a ? a.slice(D.startIdx) : []; }
  function pearson(a, b) {
    const xs = [], ys = [];
    for (let i = 0; i < a.length; i++) { if (a[i] == null || b[i] == null) continue; xs.push(a[i]); ys.push(b[i]); }
    const n = xs.length; if (n < 3) return NaN;
    const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
    let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < n; i++) { const dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
    return sxy / Math.sqrt(sxx * syy);
  }
  function authorSeries(s, which) {
    const a = scope().author; if (!a) return null;
    const block = D.view === "contrib_monthly" ? a.monthly : a.yoy;
    return block ? block[which] : null;
  }

  // ---- render ------------------------------------------------------------
  function render() {
    if (!DATA) return;
    const s = scope();
    $("d-start-label").textContent = s.dates[D.startIdx];
    const res = currentResult(); if (!res) return;
    const x = sliceFrom(X);

    let sup, dem, amb, tot, yLabel, isShare = false;
    const perLabel = sconf().quarterly ? "quarterly" : "monthly";
    if (D.view === "shares") {
      sup = res.sh_supply; dem = res.sh_demand; amb = res.sh_ambiguous; tot = null; yLabel = "share of basket"; isShare = true;
    } else if (D.view === "contrib_monthly") {
      sup = res.supply; dem = res.demand; amb = res.ambiguous; tot = res.total; yLabel = `contribution to ${perLabel} inflation (pp)`;
    } else {
      sup = res.supply_yoy; dem = res.demand_yoy; amb = res.ambiguous_yoy; tot = res.total_yoy; yLabel = "contribution to year-over-year inflation (pp)";
    }

    const hasAmb = D.precisionCut > 0 || (amb && amb.some(v => v != null && Math.abs(v) > 1e-9));
    const traces = [];
    const stack = "z";
    traces.push({ x, y: sliceFrom(dem), name: "Demand-driven", type: "scatter", mode: "lines",
                  stackgroup: stack, line: { width: 0.5, color: DEMI }, fillcolor: "rgba(76,154,255,0.75)" });
    traces.push({ x, y: sliceFrom(sup), name: "Supply-driven", type: "scatter", mode: "lines",
                  stackgroup: stack, line: { width: 0.5, color: SUP }, fillcolor: "rgba(245,96,90,0.78)" });
    if (hasAmb) traces.push({ x, y: sliceFrom(amb), name: "Ambiguous", type: "scatter", mode: "lines",
                  stackgroup: stack, line: { width: 0.5, color: AMB }, fillcolor: "rgba(201,180,88,0.7)" });
    if (!isShare && D.headline) {
      const hy = s.headline_yoy && D.view !== "contrib_monthly" ? s.headline_yoy : null;
      const totName = D.view === "contrib_monthly" ? `Total (${perLabel})` : "Total (y/y)";
      traces.push({ x, y: sliceFrom(tot), name: totName, type: "scatter", mode: "lines", line: { color: TOT, width: 1.4 } });
      if (hy) traces.push({ x, y: sliceFrom(hy), name: "Published inflation", type: "scatter", mode: "lines", line: { color: "#d05ce3", width: 1, dash: "dot" } });
    }
    if (D.author && scope().author) {
      const aS = authorSeries(s, "supply"), aD = authorSeries(s, "demand");
      if (aS) traces.push({ x, y: sliceFrom(aS), name: "Supply (FRBSF)", type: "scatter", mode: "lines", line: { color: "#ffb3b0", width: 1, dash: "dot" } });
      if (aD) traces.push({ x, y: sliceFrom(aD), name: "Demand (FRBSF)", type: "scatter", mode: "lines", line: { color: "#bcd8ff", width: 1, dash: "dot" } });
    }

    const layout = {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
      margin: { l: 52, r: 16, t: 10, b: 36 }, legend: { orientation: "h", y: 1.13, font: { size: 11 } },
      xaxis: { gridcolor: GRID, zeroline: false },
      yaxis: { title: yLabel, gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
      shapes: [{ type: "line", x0: x[0], x1: x[x.length - 1], y0: 0, y1: 0, yref: "y", line: { color: "#3a4b5c", width: 1 } }],
    };
    Plotly.react("d-chart", traces, layout, { responsive: true, displayModeBar: false });

    renderReadout(res, sup, dem, tot);
    renderBars(res);
    renderDrivers(res);
  }

  function renderReadout(res, sup, dem, tot) {
    const s = scope();
    const last = i => { for (let k = i.length - 1; k >= 0; k--) if (i[k] != null) return i[k]; return null; };
    const lsup = last(sup), ldem = last(dem);
    const aS = authorSeries(s, "supply");
    const corr = aS ? pearson(sliceFrom(sup), sliceFrom(aS)) : NaN;
    const spec = `${s.tab || s.label || D.scope} · ${D.J} lags · W=${D.W} · ${D.precisionCut === 0 ? "binary" : "cut " + D.precisionCut.toFixed(2)}` + (exSet().size ? ` · −${exSet().size} cats` : "");
    const stats = [
      ["Latest supply", lsup == null ? "—" : lsup.toFixed(2)],
      ["Latest demand", ldem == null ? "—" : ldem.toFixed(2)],
      ["Corr w/ FRBSF (supply)", isNaN(corr) ? "—" : corr.toFixed(3)],
      ["Spec", spec],
    ];
    $("d-readout").innerHTML = stats.map(([s2, v]) => `<div class="stat"><b>${v}</b><span>${s2}</span></div>`).join("");
  }

  function driversFor(res) {
    if (res.drivers) return res.drivers.map(d => ({ date: scope().dates[d.t], contrib: d.contrib }));
    if (res._baselineDrivers) return res._baselineDrivers;
    return [];
  }

  function renderBars(res) {
    const s = scope(), N = 22;
    const sup = D.view === "shares" ? res.sh_supply : (D.view === "contrib_monthly" ? res.supply : res.supply_yoy);
    const dem = D.view === "shares" ? res.sh_demand : (D.view === "contrib_monthly" ? res.demand : res.demand_yoy);
    const pairs = [];
    for (let i = s.dates.length - 1; i >= 0 && pairs.length < N; i--) if (sup[i] != null) pairs.push([s.dates[i], sup[i], dem[i]]);
    pairs.reverse();
    const xs = pairs.map(p => p[0]);
    const layout = { paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 11 }, barmode: "stack",
      margin: { l: 40, r: 8, t: 6, b: 60 }, legend: { orientation: "h", y: 1.2, font: { size: 10 } },
      xaxis: { type: "category", tickangle: -60, gridcolor: "transparent" }, yaxis: { gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" } };
    Plotly.react("d-bars", [
      { x: xs, y: pairs.map(p => p[2]), name: "Demand", type: "bar", marker: { color: DEMI } },
      { x: xs, y: pairs.map(p => p[1]), name: "Supply", type: "bar", marker: { color: SUP } },
    ], layout, { responsive: true, displayModeBar: false });
    const el = $("d-bars");
    if (el && el.on && !el._bound) { el._bound = true; el.on("plotly_click", data => { const date = String(data.points[0].x).slice(0, 7); D.selectedDate = (D.selectedDate === date) ? null : date; renderDrivers(currentResult()); }); }
  }

  function renderDrivers(res) {
    const s = scope(), host = "d-drivers", dateEl = $("d-drivers-date");
    const all = driversFor(res);
    let dd = null;
    if (D.selectedDate) dd = all.find(h => h.date === D.selectedDate);
    if (!dd) dd = all[all.length - 1];
    if (!dd || !dd.contrib || !dd.contrib.length) {
      if (dateEl) dateEl.textContent = "";
      Plotly.react(host, [], { paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, margin: { t: 10 },
        annotations: [{ text: "no active drivers", showarrow: false, font: { color: MUTED }, x: .5, y: .5, xref: "paper", yref: "paper" }] }, { displayModeBar: false });
      return;
    }
    if (dateEl) dateEl.textContent = `(${dd.date}${!D.selectedDate ? " · latest" : ""})`;
    const top = dd.contrib.slice(0, 15).reverse();
    const labels = top.map(p => { const c = s.categories[p[0]]; const n = c ? c.label : `cat ${p[0]}`; return n.length > 34 ? n.slice(0, 32) + "…" : n; });
    // p = [cat, signed contribution to inflation (pp), shock (+1 supply / -1 demand)].
    // Bars keep the TRUE sign (effect on inflation); supply vs demand is shown by
    // colour. (Older payloads without p[2] fall back to the sign as the type.)
    const vals = top.map(p => p[1]);
    const shock = top.map(p => (p.length > 2 && p[2] != null) ? p[2] : (p[1] >= 0 ? 1 : -1));
    const colors = shock.map(k => k >= 0 ? SUP : DEMI);
    const layout = { paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 11 },
      margin: { l: 180, r: 16, t: 6, b: 30 },
      xaxis: { title: "contribution to inflation (pp) · red = supply, blue = demand", gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
      yaxis: { gridcolor: "transparent", automargin: true } };
    const shockName = top.map(k => (k[2] != null ? (k[2] >= 0 ? "supply" : "demand") : ""));
    Plotly.react(host, [{ x: vals, y: labels, type: "bar", orientation: "h", marker: { color: colors },
      customdata: shockName, hovertemplate: "%{y}: %{x:.4f} pp (%{customdata})<extra></extra>" }], layout, { responsive: true, displayModeBar: false });
  }

  function setupDownload() {
    const btn = $("d-download"); if (!btn) return;
    btn.onclick = () => {
      const s = scope(), res = currentResult(); if (!res) return;
      const rows = [["date", "supply", "demand", "ambiguous", "total", "supply_yoy", "demand_yoy", "total_yoy", "sh_supply", "sh_demand"]];
      for (let i = D.startIdx; i < s.dates.length; i++)
        rows.push([s.dates[i], res.supply[i], res.demand[i], res.ambiguous[i], res.total[i], res.supply_yoy[i], res.demand_yoy[i], res.total_yoy[i], res.sh_supply[i], res.sh_demand[i]]);
      const csv = rows.map(r => r.map(v => v == null ? "" : v).join(",")).join("\n");
      const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      a.download = `decomp_${D.scope}_J${D.J}_W${D.W}_cut${D.precisionCut}.csv`; a.click();
    };
  }

  // expose + wire the model toggle once the DOM is ready
  window.DecompApp = { init };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupModelToggle);
  else setupModelToggle();
})();
