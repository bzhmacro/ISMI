/* breakdown_app.js — Inflation Breakdown: what the headline is made of, and
   how much of it the benchmark saw coming.
   ===========================================================================

   Three questions, three charts:

     1. What are the major components?   Stacked contributions by BLS major
                                          group, through time.
     2. Who are the major contributors?   Ranked categories for the selected
                                          month.
     3. What is a surprise?               The part of each contribution that
                                          deviates from the category's own
                                          rolling AR(p) forecast.

   GROUPS COME FROM THE KEY, NOT FROM A MAPPING I INVENTED
   -------------------------------------------------------
   Four of the seven gauges encode their official taxonomy in the category code
   that ism.json already ships, so the grouping is a fact about the data rather
   than a judgement call:

     cpi    BLS item strata — the major expenditure group is the THIRD
            character: SEF* food & beverages, SEH* housing, SEA* apparel,
            SET* transportation, SEM* medical care, SER* recreation,
            SEE* education & communication, SEG* other goods & services.
     uk     ONS MM23 COICOP classes, dotted: "04.1" -> division 04.
     fr,de  Eurostat HICP COICOP leaves: "CP0116" -> division 01.

   pce, jp and ca do NOT encode a parent in the key — they are flat codes
   (DNEAR, 0021, P40). Their hierarchy exists, but in the Python pipelines:
   jp_pipeline walks the cat01 parent tree to take "the direct children of the
   10 major groups", ca_cpi_categories.csv carries parent_id/depth, and the BEA
   underlying-detail tables have a line/level hierarchy. None of it is exported.

   So those three are shown as unavailable rather than grouped by guesswork.
   The fix is one field in the exporter — emit `group` alongside `key`/`label`
   from each pipeline's own hierarchy — and this file already reads
   `category.group` when it is present, so they light up on the next export
   with no change here.

   HONESTY ABOUT THE TOTAL
   -----------------------
   The stacked bars sum to the sum of category contributions, which is NOT the
   published headline: 12-month inflation compounds while summed monthly
   contributions are linear, and the panel's renormalised weights are not the
   official relative importances. The readout reports both and the gap between
   them instead of quietly presenting one as the other. */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);

  // Series palette, --c1..--c8 then repeats. COICOP has 12-13 divisions, more
  // than the eight house series colours, so it cycles with a lightness shift
  // rather than reusing a colour outright.
  const SERIES = ["#2AA695", "#8A85E8", "#CE5533", "#BE8A31",
                  "#5E9CD8", "#E07B5F", "#7FB069", "#B9B2A0"];
  const colourFor = (i) => (i < SERIES.length ? SERIES[i]
    : SERIES[i % SERIES.length] + (["CC", "99", "66"][Math.floor(i / SERIES.length) - 1] || "80"));

  // BLS major expenditure groups, keyed by the third character of the stratum
  // code. Order is the order they appear in the CPI news release.
  const BLS = {
    F: "Food & beverages", H: "Housing", A: "Apparel", T: "Transportation",
    M: "Medical care", R: "Recreation", E: "Education & communication",
    G: "Other goods & services",
  };

  // COICOP divisions. 01-12 are COICOP-1999 (ONS MM23) and ECOICOP (Eurostat);
  // 13 only appears under COICOP-2018, and is carried so a future re-based
  // series does not fall into Unclassified.
  const COICOP = {
    "01": "Food & non-alcoholic drinks", "02": "Alcohol & tobacco",
    "03": "Clothing & footwear", "04": "Housing, water & fuels",
    "05": "Furnishings & household equipment", "06": "Health",
    "07": "Transport", "08": "Communication", "09": "Recreation & culture",
    "10": "Education", "11": "Restaurants & hotels",
    "12": "Miscellaneous goods & services", "13": "Personal care & social protection",
  };

  /* Per-gauge taxonomy. `from(key)` returns a group code, or null when this
     gauge does not encode one — in which case the view falls back to the
     `group` field on the category if the exporter has started shipping it, and
     otherwise reports the gauge as ungrouped rather than inventing bins. */
  const GAUGES = [
    { key: "cpi", label: "US CPI", names: BLS,
      from: (k) => (/^SE/i.test(k) && BLS[k[2]] ? k[2] : null) },
    { key: "uk", label: "UK", names: COICOP,
      from: (k) => (/^\d{2}\./.test(k) && COICOP[k.slice(0, 2)] ? k.slice(0, 2) : null) },
    { key: "fr", label: "France", names: COICOP,
      from: (k) => (/^CP\d{2}/i.test(k) && COICOP[k.slice(2, 4)] ? k.slice(2, 4) : null) },
    { key: "de", label: "Germany", names: COICOP,
      from: (k) => (/^CP\d{2}/i.test(k) && COICOP[k.slice(2, 4)] ? k.slice(2, 4) : null) },
    { key: "pce", label: "US PCE", names: null, from: () => null },
    { key: "jp", label: "Japan", names: null, from: () => null },
    { key: "ca", label: "Canada", names: null, from: () => null },
  ];

  const PLOT_BG = "#161D2C", GRID = "#2A3448", INK = "#EDE6D6", MUTED = "#B9B2A0";
  const SURPRISE_POS = "#CE5533", SURPRISE_NEG = "#2AA695";
  const UNCLASSIFIED = "Unclassified";

  const D = {
    gauge: "cpi", p: 1, W: 120, horizon: 12, sel: null, nTail: 120,
    ready: false, detailFrom: 0, res: null,
  };
  let DATA = null, B = null, WORKER = null, REQ = 0, DATES = [];
  let GROUP_LIST = [], GROUP_OF = [];

  function gaugeSpec(key) { return GAUGES.find((g) => g.key === key); }

  /* Build the group list and the per-category group index for a backbone.
     Returns null when the gauge cannot be grouped from available data. */
  function buildGroups(spec, backbone) {
    const cats = backbone.categories || [];
    const codes = cats.map((c) => {
      // Prefer an explicit group from the exporter when present — that is the
      // authoritative hierarchy, and it supersedes anything derived here.
      if (c.group) return String(c.group);
      return spec.from(String(c.key || ""));
    });
    if (codes.every((c) => c == null)) return null;      // nothing to group by

    const names = spec.names || {};
    const order = [];
    const seen = new Map();
    codes.forEach((code) => {
      const id = code == null ? "?" : code;
      if (!seen.has(id)) { seen.set(id, order.length); order.push(id); }
    });
    // Present groups in taxonomy order where we know it, else first-seen order.
    if (spec.names) {
      const known = Object.keys(names).filter((k) => seen.has(k));
      const rest = order.filter((k) => !names[k]);
      order.length = 0;
      order.push(...known, ...rest);
      seen.clear();
      order.forEach((id, i) => seen.set(id, i));
    }
    const list = order.map((id, i) => [
      id, id === "?" ? UNCLASSIFIED : (names[id] || id), colourFor(i),
    ]);
    return { list, of: codes.map((c) => seen.get(c == null ? "?" : c)) };
  }

  /* ------------------------------------------------------------------ */
  /* boot                                                                */
  /* ------------------------------------------------------------------ */

  async function init() {
    const host = $("b-chart");
    if (!host) return;
    status("loading data…");

    try {
      // Shared with app.js via a promise on window so the 8 MB payload is
      // fetched once even though both views want it.
      window.__ismJsonPromise = window.__ismJsonPromise ||
        fetch("data/ism.json", { cache: "no-cache" }).then((r) => {
          if (!r.ok) throw new Error(`ism.json ${r.status}`);
          return r.json();
        });
      DATA = await window.__ismJsonPromise;
    } catch (err) {
      status(`could not load data/ism.json (${err})`);
      return;
    }

    // Prefer the configured default, but fall back to the first gauge that is
    // both present and groupable, so the view never opens on a dead end.
    const present = (k) => DATA.backbones && DATA.backbones[k];
    const groupable = (k) => {
      const s = gaugeSpec(k);
      return present(k) && s && buildGroups(s, DATA.backbones[k]) != null;
    };
    if (!groupable(D.gauge)) {
      const alt = GAUGES.map((g) => g.key).find(groupable);
      if (alt) D.gauge = alt;
    }

    buildControls();
    selectGauge(D.gauge);
  }

  /* Switch backbone: rebuild the taxonomy, re-init the worker with the new
     panel, recompute. */
  function selectGauge(key) {
    D.gauge = key;
    D.sel = null;
    D.res = null;
    D.ready = false;

    const spec = gaugeSpec(key);
    B = DATA.backbones && DATA.backbones[key];
    if (!B || !B.panel) {
      ungrouped(`The ${spec ? spec.label : key} backbone is not in ism.json.`);
      return;
    }
    DATES = B.dates;

    const g = buildGroups(spec, B);
    if (!g) {
      ungrouped(
        `${spec.label} has no component taxonomy in the data yet. Its categories ` +
        `are flat codes (e.g. ${String((B.categories[0] || {}).key || "?")}), and the ` +
        `parent hierarchy lives in the Python pipeline rather than in ism.json. ` +
        `Emitting a "group" field from the exporter switches this on with no ` +
        `change here — until then it is not grouped, rather than grouped by guesswork.`);
      return;
    }
    GROUP_LIST = g.list;
    GROUP_OF = g.of;
    startWorker();
  }

  /* Gauge present but not groupable: say so plainly and blank the charts
     rather than leaving the previous gauge's bars on screen. */
  function ungrouped(msg) {
    status(msg);
    const blank = { paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, margin: { t: 10 },
      font: { color: MUTED, size: 11 }, xaxis: { visible: false }, yaxis: { visible: false } };
    ["b-chart", "b-groups", "b-surprises"].forEach((id) => {
      if ($(id) && window.Plotly) Plotly.react(id, [], blank, { displayModeBar: false });
    });
    const r = $("b-readout");
    if (r) r.innerHTML = "";
  }

  function status(msg) {
    const el = $("b-status");
    if (el) el.textContent = msg || "";
  }

  function startWorker() {
    // One worker per gauge switch: the panel is sent at init, so a new backbone
    // means a fresh worker rather than a second init on the old one.
    if (WORKER) { WORKER.terminate(); WORKER = null; }
    try {
      WORKER = new Worker("breakdown_worker.js");
    } catch (err) {
      status(`could not start the worker (${err}). The breakdown needs one — ` +
             `serve the site over http rather than opening the file directly.`);
      return;
    }
    WORKER.onmessage = (e) => {
      const m = e.data;
      if (m.type === "ready") { D.ready = true; compute(); return; }
      if (m.type === "error") { status(m.message); return; }
      if (m.type === "result") {
        D.res = m;
        D.detailFrom = m.detailFrom;
        if (D.sel == null) D.sel = lastValidIndex(m.total);
        status("");
        render();
      }
    };
    WORKER.onerror = (err) => status(`worker error: ${err.message || err}`);
    WORKER.postMessage({
      type: "init",
      inflation: B.panel.inflation,
      weights: B.panel.weights,
      groupOf: GROUP_OF,
      ngroup: GROUP_LIST.length,
    });
  }

  const lastValidIndex = (arr) => {
    for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return i;
    return arr.length - 1;
  };

  function compute() {
    if (!D.ready) return;
    status("computing…");
    WORKER.postMessage({
      type: "compute", id: ++REQ,
      p: D.p, W: D.W, horizon: D.horizon, detailMonths: 60,
    });
  }

  /* ------------------------------------------------------------------ */
  /* controls                                                            */
  /* ------------------------------------------------------------------ */

  function seg(hostId, options, get, set) {
    const host = $(hostId);
    if (!host) return;
    host.innerHTML = "";
    options.forEach(([val, label]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.setAttribute("aria-pressed", String(get() === val));
      b.onclick = () => {
        set(val);
        [...host.children].forEach((c, i) =>
          c.setAttribute("aria-pressed", String(options[i][0] === val)));
      };
      host.appendChild(b);
    });
  }

  function buildControls() {
    const avail = GAUGES.filter((g) => DATA.backbones && DATA.backbones[g.key]);
    seg("b-gauge", avail.map((g) => [g.key, g.label]),
      () => D.gauge, (v) => selectGauge(v));

    seg("b-horizon", [[12, "12-month"], [1, "1-month"]],
      () => D.horizon, (v) => { D.horizon = v; D.sel = null; compute(); });
    seg("b-ar", [[1, "AR(1)"], [2, "AR(2)"], [3, "AR(3)"]],
      () => D.p, (v) => { D.p = v; compute(); });

    const w = $("b-W");
    if (w) {
      w.value = D.W;
      const lab = $("b-W-label");
      if (lab) lab.textContent = D.W;
      w.oninput = () => {
        D.W = +w.value;
        if (lab) lab.textContent = D.W;
      };
      w.onchange = compute;
    }

    const span = $("b-span");
    if (span) {
      span.value = D.nTail;
      const lab = $("b-span-label");
      if (lab) lab.textContent = `${Math.round(D.nTail / 12)}y`;
      span.oninput = () => {
        D.nTail = +span.value;
        if (lab) lab.textContent = `${Math.round(D.nTail / 12)}y`;
        render();
      };
    }
  }

  /* ------------------------------------------------------------------ */
  /* render                                                              */
  /* ------------------------------------------------------------------ */

  function render() {
    if (!D.res) return;
    renderReadout();
    renderStack();
    renderGroups();
    renderSurprises();
    if (window.ChartExport) window.ChartExport.scan();
  }

  const pct = (v, dp = 2) => (v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(dp)}%`);
  const pp = (v, dp = 2) => (v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}pp`);

  function renderReadout() {
    const { total, totalSurprise } = D.res;
    const t = D.sel;
    const sum = total[t];
    const sup = totalSurprise[t];
    const published = B.headline && B.headline.series ? B.headline.series[t] : null;
    const label = D.horizon === 12 ? "12m" : "1m";

    const rows = [
      [pct(sum), `Σ contributions (${label})`],
      [published == null ? "—" : pct(published), "Published headline"],
      [published == null || sum == null ? "—" : pp(sum - published), "Gap vs published"],
      [pp(sup), "Of which surprise"],
      [DATES[t] || "—", "Month"],
    ];
    const host = $("b-readout");
    if (host) {
      host.innerHTML = rows
        .map(([v, s], i) => `<div class="stat${i === 0 ? " big" : ""}"><b>${v}</b><span>${s}</span></div>`)
        .join("");
    }
  }

  /* 1. Stacked group contributions through time. */
  function renderStack() {
    const { groupContrib } = D.res;
    const n = DATES.length;
    const from = Math.max(0, n - D.nTail);
    const x = DATES.slice(from).map((d) => d + "-01");

    const traces = GROUP_LIST.map((g, gi) => {
      const y = groupContrib[gi].slice(from);
      if (y.every((v) => v == null || Math.abs(v) < 1e-9)) return null;
      return {
        x, y, name: g[1], type: "bar",
        marker: { color: g[2], line: { width: 0 } },
        hovertemplate: `%{x|%b %Y}<br>${g[1]}: %{y:.2f}pp<extra></extra>`,
      };
    }).filter(Boolean);

    const layout = {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG,
      font: { color: INK, size: 12 },
      barmode: "relative",
      margin: { l: 52, r: 14, t: 10, b: 40 },
      xaxis: { gridcolor: GRID, zerolinecolor: GRID },
      yaxis: {
        gridcolor: GRID, zerolinecolor: GRID,
        title: { text: `contribution, pp (${D.horizon === 12 ? "12m" : "1m"})`, font: { size: 11 } },
      },
      legend: { orientation: "h", y: -0.16, font: { size: 10 } },
      showlegend: true,
    };
    Plotly.react("b-chart", traces, layout, { responsive: true, displayModeBar: false });

    const gd = $("b-chart");
    if (gd && !gd.dataset.clickBound) {
      gd.dataset.clickBound = "1";
      gd.on("plotly_click", (ev) => {
        const iso = ev.points && ev.points[0] && ev.points[0].x;
        if (!iso) return;
        const key = String(iso).slice(0, 7);
        const idx = DATES.indexOf(key);
        if (idx >= 0) { D.sel = idx; render(); }
      });
    }
  }

  /* 2. Selected month by group, expected vs surprise. */
  function renderGroups() {
    const { groupContrib, groupSurprise } = D.res;
    const t = D.sel;

    const rows = GROUP_LIST.map((g, gi) => {
      const c = groupContrib[gi][t];
      const s = groupSurprise[gi][t];
      return { label: g[1], contrib: c, surprise: s,
               expected: c == null || s == null ? null : c - s };
    }).filter((r) => r.contrib != null && Math.abs(r.contrib) > 1e-9);

    rows.sort((a, b2) => Math.abs(b2.contrib) - Math.abs(a.contrib));
    const labels = rows.map((r) => r.label);

    const layout = {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG,
      font: { color: INK, size: 11 },
      barmode: "relative",
      margin: { l: 150, r: 14, t: 10, b: 34 },
      xaxis: { gridcolor: GRID, zerolinecolor: GRID,
               title: { text: "pp", font: { size: 10 } } },
      yaxis: { gridcolor: GRID, automargin: true },
      legend: { orientation: "h", y: -0.2, font: { size: 10 } },
    };

    Plotly.react("b-groups", [
      { x: rows.map((r) => r.expected), y: labels, name: "expected by AR benchmark",
        type: "bar", orientation: "h", marker: { color: "#3A4558" },
        hovertemplate: "%{y}<br>expected %{x:.2f}pp<extra></extra>" },
      { x: rows.map((r) => r.surprise), y: labels, name: "surprise",
        type: "bar", orientation: "h",
        marker: { color: rows.map((r) => (r.surprise >= 0 ? SURPRISE_POS : SURPRISE_NEG)) },
        hovertemplate: "%{y}<br>surprise %{x:.2f}pp<extra></extra>" },
    ], layout, { responsive: true, displayModeBar: false });
  }

  /* 3. Biggest category-level surprises in the selected month. */
  function renderSurprises() {
    const { catSurprise, catContrib } = D.res;
    const t = D.sel - D.detailFrom;
    const host = "b-surprises";

    if (t < 0 || t >= (catSurprise[0] || []).length) {
      Plotly.react(host, [], {
        paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG, margin: { t: 10 },
        font: { color: MUTED, size: 11 },
        annotations: [{ text: "select a month inside the detail window", showarrow: false,
                        xref: "paper", yref: "paper", x: 0.5, y: 0.5 }],
        xaxis: { visible: false }, yaxis: { visible: false },
      }, { responsive: true, displayModeBar: false });
      return;
    }

    const rows = B.categories.map((c, i) => ({
      label: c.label, s: catSurprise[i][t], c: catContrib[i][t],
    })).filter((r) => r.s != null && Number.isFinite(r.s));

    rows.sort((a, b2) => Math.abs(b2.s) - Math.abs(a.s));
    const top = rows.slice(0, 12).reverse();

    const layout = {
      paper_bgcolor: PLOT_BG, plot_bgcolor: PLOT_BG,
      font: { color: INK, size: 11 },
      margin: { l: 190, r: 14, t: 10, b: 34 },
      xaxis: { gridcolor: GRID, zerolinecolor: GRID,
               title: { text: "surprise, pp", font: { size: 10 } } },
      yaxis: { gridcolor: GRID, automargin: true },
      showlegend: false,
    };
    Plotly.react(host, [{
      x: top.map((r) => r.s),
      y: top.map((r) => (r.label.length > 34 ? r.label.slice(0, 33) + "…" : r.label)),
      type: "bar", orientation: "h",
      marker: { color: top.map((r) => (r.s >= 0 ? SURPRISE_POS : SURPRISE_NEG)) },
      hovertemplate: "%{y}<br>surprise %{x:.2f}pp<extra></extra>",
    }], layout, { responsive: true, displayModeBar: false });

    const d = $("b-sel-date");
    if (d) d.textContent = DATES[D.sel] ? `· ${DATES[D.sel]}` : "";
  }

  /* ------------------------------------------------------------------ */

  if (typeof ModelBar !== "undefined") {
    ModelBar.register({
      key: "breakdown",
      label: "Breakdown",
      viewId: "breakdown-view",
      sub: "What the headline print is made of: contributions by major group, " +
           "split into the part a rolling AR benchmark expected and the part it did not.",
      init,
      refresh: () => { if (D.res) render(); },
    });
  }
})();
