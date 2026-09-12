/* Trimmed mean & median inflation — the third model in the interactive site.

   Self-contained controller for #trim-view. Like the other two models the
   heavy work runs CLIENT-SIDE: data/trim.json ships the seasonally adjusted
   category panels and the month-by-month weight panels, and trim_worker.js
   (running trim_engine.js, a parity-tested port of src/ism/trim_engine.py)
   re-trims the cross-section whenever a control moves.

   What you can actually change, and why each control is here:

     * the two trim fractions, independently — the asymmetry is the point. The
       Dallas Fed cuts 24% off the bottom and 31% off the top because the PCE
       cross-section is right-skewed; drag the two sliders apart and watch the
       bias against the published series close.
     * the weight vintage — "versioned" is the real month-by-month relative
       importance path; "latest" and "first" freeze one vector and broadcast it,
       which is how you see what using today's shelter weight in 1998 does to
       the history. This is the control the whole cpi_ri module exists for.
     * the seasonal adjustment — irrelevant for the US scopes, whose panels
       arrive already adjusted by the agency, and decisive for the country
       scopes, which do not.
     * the category set — untick a line and the trim points move, because the
       trim is a fraction of the *weight* that remains. */

(() => {
  const D = {
    scope: null, lower: 0.08, upper: 0.08, preset: "trim16",
    sa: null, saWindow: 120, weightVintage: "versioned",
    view: "yoy", startIdx: 0, official: true, headline: true,
    selectedDate: null, inited: false,
  };
  let DATA = null, X = [], WORKER = null, READY = false, LIVE = new Set();
  let REQ = 0, REQ_KEY = "", RESULT = null, DEB = null;
  const EXCLUDED = {};

  // bzhmacro house tokens — see the note in app.js.
  const PLOT_BG = "#161D2C", GRID = "#2A3448", INK = "#EDE6D6";
  const OURS = "#f5a623", OFFICIAL = "#4c9aff", HEAD = "#d05ce3";
  const CUT_LO = "#4c9aff", KEEP = "#8b98a5", CUT_HI = "#f5605a", EDGE = "#c9b458";
  const $ = id => document.getElementById(id);

  // ---- init --------------------------------------------------------------
  async function init() {
    D.inited = true;
    try {
      const res = await fetch("data/trim.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      DATA = await res.json();
    } catch (e) {
      $("t-chart").innerHTML =
        `<div style="padding:24px;color:#f0d28a">Could not load <code>data/trim.json</code>.
         Run <code>python scripts/export_trim_data.py</code>, then redeploy. (${e})</div>`;
      return;
    }
    D.scope = DATA.meta.default_scope;
    adoptPreset();
    applyScope();
    buildControls();
    startWorker();
    render();
  }

  const scope = () => DATA.scopes[D.scope];
  const ui = () => DATA.meta.ui;

  function applyScope() {
    const s = scope();
    D.sa = D.sa === null ? s.sa : D.sa;
    X = s.dates.map(d => new Date(d + "-01"));
    D.startIdx = defaultStart(s);
    if (!EXCLUDED[D.scope]) EXCLUDED[D.scope] = new Set();
    const start = $("t-start");
    if (start) { start.max = String(s.dates.length - 1); start.value = String(D.startIdx); }
    buildCatList();
    setNotes();
  }

  /* Open on the span where the published series exists, so the first thing you
     see is the comparison rather than sixty years of our own line. */
  function defaultStart(s) {
    const off = firstOfficial(s);
    if (off < 0) return Math.max(0, s.dates.length - 12 * 40);
    return Math.max(0, off - 12);
  }
  function firstOfficial(s) {
    const o = s.official || {};
    let best = -1;
    for (const m of Object.keys(o)) {
      const arr = o[m].yoy || [];
      for (let i = 0; i < arr.length; i++)
        if (arr[i] != null) { if (best < 0 || i < best) best = i; break; }
    }
    return best;
  }

  // ---- worker ------------------------------------------------------------
  function startWorker() {
    try { WORKER = new Worker("trim_worker.js"); }
    catch (e) { setStatus("worker unavailable — showing the precomputed presets", true); return; }
    WORKER.onmessage = e => {
      const m = e.data;
      if (m.type === "ready") {
        READY = true; LIVE = new Set(m.scopes); requestCompute(0); return;
      }
      if (m.type === "result") {
        if (m.id !== REQ) return;                    // a stale reply
        RESULT = m; setStatus(`recomputed in ${m.ms} ms`); render();
        return;
      }
      if (m.type === "error") setStatus(m.message, true);
    };
    const panels = {};
    for (const [k, s] of Object.entries(DATA.scopes))
      panels[k] = { inflation: s.panel.inflation, weights: s.panel.weights, months: s.dates };
    WORKER.postMessage({ type: "init", panels });
  }

  const exSet = () => EXCLUDED[D.scope] || new Set();

  function requestCompute(delay = 140) {
    if (!WORKER || !READY || !LIVE.has(D.scope)) return;
    const key = [D.scope, D.lower, D.upper, D.sa, D.saWindow, D.weightVintage,
                 [...exSet()].join(",")].join("|");
    if (key === REQ_KEY && RESULT) return;
    REQ_KEY = key;
    clearTimeout(DEB);
    DEB = setTimeout(() => {
      REQ += 1;
      WORKER.postMessage({
        type: "compute", id: REQ, scope: D.scope,
        params: {
          lower: D.lower, upper: D.upper, sa: D.sa, saWindow: D.saWindow,
          ppy: scope().ppy || 12, weightVintage: D.weightVintage,
          minCategories: 5, excluded: [...exSet()],
        },
      });
      setStatus("computing…");
    }, delay);
  }

  function setStatus(t, warn) {
    const el = $("t-status"); if (!el) return;
    el.textContent = t || ""; el.classList.toggle("warn", !!warn);
  }

  /* The worker's answer when it has one, else the preset baked into the
     payload — so the page paints before the worker is warm. */
  function currentResult() {
    if (RESULT && RESULT.scope === D.scope) return RESULT;
    const b = scope().baseline || {};
    const preset = b[D.preset] || b.trim16 || Object.values(b)[0];
    if (!preset) return null;
    return { rate: preset.rate, yoy: preset.yoy, n: preset.n, latest: null,
             baseline: true };
  }

  // ---- controls ----------------------------------------------------------
  function seg(id, values, current, label, onPick) {
    const host = $(id); if (!host) return; host.innerHTML = "";
    values.forEach(v => {
      const b = document.createElement("button");
      b.textContent = label(v);
      b.setAttribute("aria-pressed", String(v === current));
      b.onclick = () => {
        [...host.children].forEach(c => c.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        onPick(v);
      };
      host.appendChild(b);
    });
  }

  function buildControls() {
    seg("t-scope", DATA.meta.scopes, D.scope,
        k => DATA.scopes[k].tab || k,
        k => {
          D.scope = k; D.sa = DATA.scopes[k].sa; RESULT = null; REQ_KEY = "";
          adoptPreset();          // a CPI preset means nothing on the PCE scope
          applyScope(); syncSA(); syncPreset(); requestCompute(0); render();
        });

    const presets = ui().presets;
    seg("t-preset", Object.keys(presets).concat(["custom"]), D.preset,
        k => k === "custom" ? "Custom" : presets[k].label,
        k => {
          D.preset = k;
          if (k !== "custom") { D.lower = presets[k].lower; D.upper = presets[k].upper; syncTrim(); }
          requestCompute(0);
        });

    seg("t-view", ["yoy", "rate"], D.view,
        v => v === "yoy" ? "12-month" : "1-month annualised",
        v => { D.view = v; render(); });

    seg("t-weights", ui().weight_vintages, D.weightVintage,
        v => ({ versioned: "Versioned (month by month)", latest: "Latest, frozen",
                first: "First, frozen" }[v] || v),
        v => { D.weightVintage = v; requestCompute(0); });

    seg("t-sa", ui().sa_methods, D.sa,
        v => ({ none: "As published", rolling: "Rolling month effects",
                dummy: "Full-sample month effects" }[v] || v),
        v => { D.sa = v; requestCompute(0); });

    bindSlider("t-lower", v => { D.lower = v; D.preset = "custom"; markCustom(); syncTrim(); requestCompute(); });
    bindSlider("t-upper", v => { D.upper = v; D.preset = "custom"; markCustom(); syncTrim(); requestCompute(); });

    const start = $("t-start");
    if (start) start.oninput = () => { D.startIdx = +start.value; render(); };

    bindCheck("t-t-official", D.official, v => { D.official = v; render(); });
    bindCheck("t-t-headline", D.headline, v => { D.headline = v; render(); });

    const dl = $("t-download");
    if (dl) dl.onclick = downloadCsv;

    syncTrim(); syncSA();
  }

  function bindSlider(id, onInput) {
    const el = $(id); if (!el) return;
    el.oninput = () => onInput(+el.value / 100);
  }
  function bindCheck(id, initial, onChange) {
    const el = $(id); if (!el) return;
    el.checked = initial;
    el.onchange = () => onChange(el.checked);
  }
  /* Keep the preset meaningful for the scope in view: the Cleveland presets
     have no published counterpart on PCE and the Dallas one has none on CPI,
     so switching scope should switch the comparison too rather than leave the
     "Published" read-out showing a dash. Only moves off a preset that has gone
     stale; a custom trim is left alone. */
  function adoptPreset() {
    if (D.preset === "custom") return;
    const off = scope().official || {};
    if (off[D.preset]) return;
    const next = Object.keys(ui().presets).find(k => off[k]);
    if (!next) return;
    D.preset = next;
    D.lower = ui().presets[next].lower;
    D.upper = ui().presets[next].upper;
    syncTrim();
  }

  function syncPreset() {
    const host = $("t-preset"); if (!host) return;
    const keys = Object.keys(ui().presets).concat(["custom"]);
    [...host.children].forEach((c, i) =>
      c.setAttribute("aria-pressed", String(keys[i] === D.preset)));
  }

  function markCustom() {
    const host = $("t-preset"); if (!host) return;
    [...host.children].forEach(c =>
      c.setAttribute("aria-pressed", String(c.textContent === "Custom")));
  }
  function syncTrim() {
    const lo = $("t-lower"), up = $("t-upper");
    if (lo) lo.value = String(Math.round(D.lower * 100));
    if (up) up.value = String(Math.round(D.upper * 100));
    const l = $("t-lower-label"), u = $("t-upper-label"), k = $("t-keep-label");
    if (l) l.textContent = `${(100 * D.lower).toFixed(0)}%`;
    if (u) u.textContent = `${(100 * D.upper).toFixed(0)}%`;
    if (k) k.textContent = D.lower + D.upper >= 0.999
      ? "the weighted median"
      : `${(100 * (1 - D.lower - D.upper)).toFixed(0)}% of the basket kept`;
  }
  function syncSA() {
    const host = $("t-sa"); if (!host) return;
    [...host.children].forEach((c, i) =>
      c.setAttribute("aria-pressed", String(ui().sa_methods[i] === D.sa)));
    const note = $("t-sa-note");
    if (note) note.textContent = scope().sa === "none"
      ? "This gauge arrives seasonally adjusted by the agency — leave it on “as published”."
      : "This gauge is published unadjusted, so the seasonal is removed here.";
  }

  function setNotes() {
    const s = scope();
    const el = $("t-notes"); if (!el) return;
    const bits = [s.source_note, s.weight_note].filter(Boolean);
    el.innerHTML = bits.map(b => `<div>${b}</div>`).join("")
      + (s.notes || []).map(n => `<div class="muted">${n}</div>`).join("");
  }

  // ---- category picker ---------------------------------------------------
  function buildCatList() {
    const host = $("t-catlist"); if (!host) return;
    const s = scope();
    host.innerHTML = "";
    s.categories.forEach((c, i) => {
      const row = document.createElement("label");
      row.className = "catrow";
      const box = document.createElement("input");
      box.type = "checkbox"; box.checked = !exSet().has(i);
      box.onchange = () => {
        const ex = exSet();
        box.checked ? ex.delete(i) : ex.add(i);
        EXCLUDED[D.scope] = ex;
        updateCatSummary(); requestCompute();
      };
      const span = document.createElement("span");
      span.textContent = c.label;
      row.appendChild(box); row.appendChild(span);
      host.appendChild(row);
    });
    const search = $("t-cat-search");
    if (search) search.oninput = () => {
      const q = search.value.toLowerCase();
      [...host.children].forEach(r =>
        r.classList.toggle("hidden", q && !r.textContent.toLowerCase().includes(q)));
    };
    updateCatSummary();
  }
  function updateCatSummary() {
    const el = $("t-cat-summary"); if (!el) return;
    const n = scope().categories.length, ex = exSet().size;
    el.textContent = ex ? `${n - ex} of ${n} included` : `all ${n} included`;
  }

  // ---- render ------------------------------------------------------------
  const sliceFrom = a => (a ? a.slice(D.startIdx) : a);

  function render() {
    if (!DATA) return;
    const s = scope(), res = currentResult();
    const lab = $("t-start-label"); if (lab) lab.textContent = s.dates[D.startIdx];
    if (!res) return;
    const x = sliceFrom(X);
    const ours = D.view === "yoy" ? res.yoy : res.rate;
    const yLabel = D.view === "yoy" ? "12-month inflation (%)"
                                    : "1-month inflation, annualised (%)";

    const traces = [{
      x, y: sliceFrom(ours), name: ourName(), type: "scatter", mode: "lines",
      line: { color: OURS, width: 1.8 },
    }];

    if (D.official) {
      for (const [key, o] of Object.entries(s.official || {})) {
        const y = D.view === "yoy" ? o.yoy : o.rate;
        traces.push({ x, y: sliceFrom(y), name: o.label, type: "scatter",
                      mode: "lines",
                      line: { color: OFFICIAL, width: 1, dash: key === D.preset ? "dot" : "dashdot" },
                      opacity: key === D.preset ? 1 : 0.45 });
      }
    }
    if (D.headline && s.headline && D.view === "yoy") {
      traces.push({ x, y: sliceFrom(s.headline.series), name: s.headline.label,
                    type: "scatter", mode: "lines",
                    line: { color: HEAD, width: 1, dash: "dot" } });
    }

    const layout = {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 12 },
      margin: { l: 52, r: 16, t: 10, b: 36 },
      legend: { orientation: "h", y: 1.13, font: { size: 11 } },
      xaxis: { gridcolor: GRID, zeroline: false },
      yaxis: { title: yLabel, gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0,
                 line: { color: "#3a4b5c", width: 1 } }],
    };
    Plotly.react("t-chart", traces, layout, { responsive: true, displayModeBar: false });

    renderReadout(res, ours);
    renderCrossSection(res);
    renderWeights();
  }

  function ourName() {
    if (D.lower + D.upper >= 0.999) return "Our median";
    if (D.lower === 0 && D.upper === 0) return "Our weighted mean (no trim)";
    return `Our trim ${(100 * D.lower).toFixed(0)}/${(100 * D.upper).toFixed(0)}`;
  }

  function lastOf(a) {
    if (!a) return null;
    for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i];
    return null;
  }

  function renderReadout(res, ours) {
    const s = scope();
    const latest = lastOf(ours);
    const matched = s.official && s.official[D.preset];
    const off = matched ? lastOf(D.view === "yoy" ? matched.yoy : matched.rate) : null;
    const corr = matched ? pearson(sliceFrom(ours),
                                   sliceFrom(D.view === "yoy" ? matched.yoy : matched.rate)) : NaN;
    const headline = s.headline ? lastOf(s.headline.series) : null;

    const stats = [
      ["Latest", latest == null ? "—" : latest.toFixed(2) + "%"],
      ["Published", off == null ? "—" : off.toFixed(2) + "%"],
      ["Headline", headline == null ? "—" : headline.toFixed(2) + "%"],
      ["Corr w/ published", isNaN(corr) ? "—" : corr.toFixed(3)],
      ["Categories", String(s.categories.length - exSet().size)],
    ];
    $("t-readout").innerHTML = stats
      .map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");

    /* The specification is a sentence, not a statistic — it belongs under the
       tiles rather than stretched across one of them. */
    const spec = $("t-spec");
    if (spec) spec.textContent =
      `${s.tab} · ${ourName().toLowerCase()} · ${D.weightVintage} weights · `
      + `seasonal: ${D.sa} · correlation measured over the visible window`
      + (exSet().size ? ` · ${exSet().size} categories excluded` : "");
  }

  /* The latest cross-section, sorted, coloured by where each category fell —
     this is the picture the Reserve Banks publish as their component table, and
     the one that answers "what actually got trimmed this month?". */
  function renderCrossSection(res) {
    const host = "t-cross", s = scope();
    const L = res.latest;
    if (!L) {
      Plotly.react(host, [], {
        paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, margin: { t: 10 },
        annotations: [{ text: "cross-section appears once the worker has run",
                        showarrow: false, font: { color: "#8b98a5", size: 11 } }],
      }, { displayModeBar: false });
      return;
    }
    const rows = [];
    for (let j = 0; j < s.categories.length; j++) {
      if (L.values[j] == null || L.weights[j] == null) continue;
      rows.push({ label: s.categories[j].label, v: L.values[j],
                  w: 100 * L.weights[j], m: L.membership[j],
                  kept: L.retained ? 100 * L.retained[j] : null });
    }
    rows.sort((a, b) => a.v - b.v);
    /* Four states, not three. A category straddling a trim point had part of
       its weight retained, so it is neither "cut" nor "included" — colouring it
       cut would say a category that drove the number was discarded. */
    const colour = m => m === -1 ? CUT_LO : (m === 1 ? CUT_HI : (m === 2 ? EDGE : KEEP));
    const straddlers = rows.filter(r => r.m === 2);
    const el = $("t-cross-date");
    if (el) el.textContent = s.dates[L.row]
      + (straddlers.length
          ? ` · ${straddlers.length} at the trim point (gold, partly counted)`
          : "");

    Plotly.react(host, [{
      type: "bar", orientation: "h",
      y: rows.map(r => r.label), x: rows.map(r => r.v),
      marker: { color: rows.map(r => colour(r.m)) },
      customdata: rows.map(r => [r.w, r.kept == null ? r.w : r.kept,
                                 r.m === 2 ? "partly counted (trim point)"
                                 : (r.m === 0 ? "counted"
                                 : (r.m === -1 ? "cut from the bottom" : "cut from the top"))]),
      hovertemplate: "%{y}<br>%{x:.1f}% annualised"
        + "<br>weight %{customdata[0]:.2f}%, of which %{customdata[1]:.2f}% counted"
        + "<br>%{customdata[2]}<extra></extra>",
    }], {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG,
      font: { color: INK, size: 10 },
      margin: { l: 190, r: 10, t: 6, b: 30 },
      xaxis: { title: "annualised %", gridcolor: GRID, zeroline: true, zerolinecolor: "#3a4b5c" },
      yaxis: { automargin: false, tickfont: { size: 9 } },
      height: Math.max(320, 15 * rows.length),
    }, { responsive: true, displayModeBar: false });
  }

  /* The weight panel itself: what "versioned" actually buys you. Shows the
     five categories whose weight moved most over the sample. */
  function renderWeights() {
    const s = scope(), host = "t-weights-chart";
    const W = s.panel.weights, cats = s.categories;
    const firstRow = [], lastRow = [];
    for (let j = 0; j < cats.length; j++) {
      firstRow.push(firstFinite(W[j]));
      lastRow.push(lastFinite(W[j]));
    }
    const moved = cats.map((c, j) => ({ j, label: c.label,
                                        d: Math.abs((lastRow[j] ?? 0) - (firstRow[j] ?? 0)) }))
                      .sort((a, b) => b.d - a.d).slice(0, 5);
    const x = sliceFrom(X);
    const traces = moved.map(m => ({
      x, y: sliceFrom(W[m.j]).map(v => v == null ? null : 100 * v),
      name: m.label, type: "scatter", mode: "lines", line: { width: 1.4 },
    }));
    Plotly.react(host, traces, {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, font: { color: INK, size: 11 },
      margin: { l: 44, r: 10, t: 6, b: 30 },
      legend: { orientation: "h", y: 1.22, font: { size: 9 } },
      xaxis: { gridcolor: GRID }, yaxis: { title: "weight (%)", gridcolor: GRID },
    }, { responsive: true, displayModeBar: false });

    const note = $("t-weights-note");
    if (note) note.textContent = s.weights_source
      ? sourceSpanNote(s) : (s.weight_note || "");
  }

  function sourceSpanNote(s) {
    const src = s.weights_source;
    let firstAnchored = -1;
    for (let i = 0; i < src.length; i++) if (src[i] === "anchored") { firstAnchored = i; break; }
    if (firstAnchored <= 0) return s.weight_note || "";
    return `${s.weight_note}. Before ${s.dates[firstAnchored]} the weights are `
         + `back-updated from the first published anchor rather than anchored on `
         + `a table of their own.`;
  }

  const firstFinite = a => { for (const v of a) if (v != null) return v; return null; };
  const lastFinite = a => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };

  function pearson(a, b) {
    let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
    for (let i = 0; i < a.length; i++) {
      const x = a[i], y = b && b[i];
      if (x == null || y == null) continue;
      n++; sa += x; sb += y; saa += x * x; sbb += y * y; sab += x * y;
    }
    if (n < 3) return NaN;
    const cov = sab / n - (sa / n) * (sb / n);
    const va = saa / n - (sa / n) ** 2, vb = sbb / n - (sb / n) ** 2;
    return cov / Math.sqrt(va * vb);
  }

  // ---- download ----------------------------------------------------------
  function downloadCsv() {
    const s = scope(), res = currentResult(); if (!res) return;
    const off = s.official || {};
    const offKeys = Object.keys(off);
    const rows = [["date", "rate_ann", "yoy", "n_categories"]
      .concat(offKeys.flatMap(k => [`${k}_rate`, `${k}_yoy`]))];
    for (let i = D.startIdx; i < s.dates.length; i++) {
      rows.push([s.dates[i], res.rate[i], res.yoy ? res.yoy[i] : "", res.n ? res.n[i] : ""]
        .concat(offKeys.flatMap(k => [off[k].rate[i], off[k].yoy[i]])));
    }
    const csv = rows.map(r => r.map(v => v == null ? "" : v).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `trim_${D.scope}_${(100 * D.lower).toFixed(0)}_${(100 * D.upper).toFixed(0)}`
               + `_${D.weightVintage}.csv`;
    a.click();
  }

  // ---- register ----------------------------------------------------------
  window.TrimApp = { init };
  if (typeof ModelBar !== "undefined") {
    ModelBar.register({
      key: "trim",
      label: "Trimmed mean & median",
      viewId: "trim-view",
      sub: "Limited-influence inflation measures — the weighted median and "
         + "asymmetric trimmed means behind the Cleveland Fed's median CPI and "
         + "the Dallas Fed's trimmed mean PCE — recomputed live from the "
         + "category cross-section, with the weights that actually applied in "
         + "each month.",
      init,
      refresh: () => requestCompute(0),
    });
  }
})();
