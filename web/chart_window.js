/* chart_window.js — the main time-series chart on each model page opens on the
   last two years; zoom out in the chart itself to see more.

   Wraps Plotly.react for the registered charts only. Before each draw it sets
   the x range (the default two-year window, or whatever the reader last zoomed
   to) and fits each y axis to the data inside that window, so the default view
   is not squashed by the full history's extremes. A range selector
   (2y / 5y / 10y / All) sits on the x axis; drag to zoom, double-click for the
   full history.

   One timeline for every country. Each app calls ChartWindow.span(id, gauges)
   once its payload has loaded; the window then ends at the latest month held
   by ANY gauge on that page, not the selected one, and "All" (or a
   double-click) spans the earliest-to-latest month across all of them. A
   country whose data stops earlier shows the gap instead of silently ending
   its axis sooner, and a zoom is kept when switching country. */
"use strict";

(() => {
  if (!window.Plotly) return;
  const CHARTS = new Set(["b-chart", "chart", "d-chart", "t-chart", "t-weights-chart"]);
  // Secondary charts get the two-year window but no range buttons (their
  // legend sits where the buttons would); drag to zoom, double-click for all.
  const NO_BUTTONS = new Set(["t-weights-chart"]);
  const YEARS = 2;
  const DAY = 864e5;
  const state = {};          // id -> { domain, range: null | "all" | [a, b] }
  const SPAN = {};           // id -> [t0, t1] shared across every gauge on the page

  const ms = v => {
    if (v == null) return NaN;
    if (v instanceof Date) return v.getTime();
    if (typeof v === "number") return v;
    const s = String(v);
    return Date.parse(s.length === 7 ? s + "-01" : s.slice(0, 10));
  };
  const iso = t => new Date(t).toISOString().slice(0, 10);
  const isVisible = tr => tr.visible !== false && tr.visible !== "legendonly";

  function domainOf(data) {
    let lo = Infinity, hi = -Infinity;
    data.forEach(tr => (tr.x || []).forEach(v => {
      const t = ms(v); if (t < lo) lo = t; if (t > hi) hi = t;
    }));
    return Number.isFinite(lo) ? [lo, hi] : null;
  }

  /* y extent of each axis over [a, b]: stacked bars and stackgroups are summed
     per x (positives and negatives separately), everything else taken as is. */
  function fitY(data, layout, a, b) {
    const ext = {};                         // axis key -> [lo, hi]
    const stacks = {};                      // axis|group -> Map(x -> [pos, neg])
    const barStack = ["relative", "stack"].includes(layout.barmode);
    const put = (ax, v) => {
      if (!Number.isFinite(v)) return;
      const e = ext[ax] || (ext[ax] = [Infinity, -Infinity]);
      if (v < e[0]) e[0] = v; if (v > e[1]) e[1] = v;
    };
    data.forEach(tr => {
      if (!isVisible(tr) || !tr.x || !tr.y || tr.orientation === "h") return;
      const ax = "yaxis" + String(tr.yaxis || "y").slice(1);
      const isBar = tr.type === "bar";
      const group = isBar && barStack ? "bars" : tr.stackgroup ? "sg:" + tr.stackgroup : null;
      if (isBar) put(ax, 0);
      tr.x.forEach((xv, i) => {
        const t = ms(xv), y = tr.y[i];
        if (!(t >= a && t <= b) || y == null || !Number.isFinite(+y)) return;
        if (!group) { put(ax, +y); return; }
        const key = ax + "|" + group;
        const m = stacks[key] || (stacks[key] = new Map());
        const s = m.get(t) || [0, 0];
        if (+y >= 0) s[0] += +y; else s[1] += +y;
        m.set(t, s);
      });
    });
    Object.entries(stacks).forEach(([key, m]) => {
      const ax = key.split("|")[0];
      m.forEach(([p, n]) => { put(ax, p); put(ax, n); });
    });
    const out = {};
    Object.entries(ext).forEach(([ax, [lo, hi]]) => {
      if (!(hi >= lo)) return;
      const pad = (hi - lo || Math.abs(hi) || 1) * 0.07;
      out[ax] = [lo - pad, hi + pad];
    });
    return out;
  }

  /* `gauges` is the payload's map of series, each with a `dates` array of
     "YYYY-MM" (DATA.backbones on the ISM pages, DATA.scopes elsewhere). */
  function span(ids, gauges) {
    let lo = Infinity, hi = -Infinity;
    Object.values(gauges || {}).forEach(g => {
      const d = g && g.dates;
      if (!d || !d.length) return;
      const a = ms(d[0]), b = ms(d[d.length - 1]);
      if (a < lo) lo = a; if (b > hi) hi = b;
    });
    if (!Number.isFinite(lo)) return;
    [].concat(ids).forEach(id => { SPAN[id] = [lo, hi]; });
  }

  function windowFor(id, data) {
    const dom = SPAN[id] || domainOf(data);
    if (!dom) return null;
    const st = state[id] || (state[id] = { domain: null, range: null });
    const key = dom.join("|");
    if (st.domain !== key) { st.domain = key; st.range = null; }
    if (st.range === "all") return { all: true };
    const r = st.range || [Math.max(dom[0], dom[1] - YEARS * 365.25 * DAY) - 20 * DAY,
                           dom[1] + 20 * DAY];
    return { range: r };
  }

  const SELECTOR = {
    buttons: [
      { count: 2, label: "2y", step: "year", stepmode: "backward" },
      { count: 5, label: "5y", step: "year", stepmode: "backward" },
      { count: 10, label: "10y", step: "year", stepmode: "backward" },
      { step: "all", label: "All" },
    ],
    x: 1, y: 1.0, yanchor: "bottom", xanchor: "right",
    bgcolor: "rgba(0,0,0,0)", activecolor: "rgba(200,60,60,0.35)",
    bordercolor: "rgba(140,150,165,0.4)", borderwidth: 1,
    font: { size: 10 },
  };

  function decorate(id, data, layout) {
    const w = windowFor(id, data);
    if (!w) return layout;
    const L = Object.assign({}, layout);
    L.xaxis = Object.assign({}, layout.xaxis, { type: "date" },
      NO_BUTTONS.has(id) ? {} : { rangeselector: SELECTOR });
    L.dragmode = L.dragmode || "zoom";
    // Autorange ("All", double-click) always reaches both ends of the page's
    // shared span, whichever country is drawn.
    if (SPAN[id]) L.xaxis.autorangeoptions = { include: SPAN[id].map(iso) };
    if (w.all) {
      L.xaxis.autorange = true; delete L.xaxis.range;
      return L;
    }
    L.xaxis.range = w.range.map(iso);
    L.xaxis.autorange = false;
    const ys = fitY(data, L, w.range[0], w.range[1]);
    Object.entries(ys).forEach(([ax, r]) => {
      if (layout[ax] && layout[ax].range) return;      // the app fixed it
      L[ax] = Object.assign({}, layout[ax], { range: r, autorange: false });
    });
    return L;
  }

  function bind(gd) {
    if (gd._cwBound) return;
    gd._cwBound = true;
    gd.on("plotly_relayout", ev => {
      if (gd._cwBusy || !ev) return;
      const st = state[gd.id] || (state[gd.id] = { domain: null, range: null });
      let a, b;
      if (ev["xaxis.autorange"]) {
        st.range = "all";
        // The "All" button only autoranges x; let y follow the full history.
        if (!Object.keys(ev).some(k => k.startsWith("yaxis"))) {
          const upd = {};
          Object.keys(gd.layout || {}).filter(k => /^yaxis\d*$/.test(k))
            .forEach(k => { upd[k + ".autorange"] = true; });
          gd._cwBusy = true;
          Promise.resolve(Plotly.relayout(gd, upd)).finally(() => { gd._cwBusy = false; });
        }
        return;
      }
      if (ev["xaxis.range"]) [a, b] = ev["xaxis.range"];
      else if ("xaxis.range[0]" in ev) { a = ev["xaxis.range[0]"]; b = ev["xaxis.range[1]"]; }
      else return;
      a = ms(a); b = ms(b);
      if (!(b > a)) return;
      st.range = [a, b];
      // A box zoom also sets y: respect it. An x-only change (range buttons,
      // axis drag) refits y to what is now visible.
      if (Object.keys(ev).some(k => k.startsWith("yaxis"))) return;
      refit(gd, a, b);
    });
    gd.on("plotly_restyle", () => {
      const st = state[gd.id];
      if (gd._cwBusy || !st || !Array.isArray(st.range)) return;
      refit(gd, st.range[0], st.range[1]);
    });
  }

  function refit(gd, a, b) {
    const ys = fitY(gd.data || [], gd.layout || {}, a, b);
    const upd = {};
    Object.entries(ys).forEach(([ax, r]) => { upd[ax + ".range"] = r; upd[ax + ".autorange"] = false; });
    if (!Object.keys(upd).length) return;
    gd._cwBusy = true;
    Promise.resolve(Plotly.relayout(gd, upd)).finally(() => { gd._cwBusy = false; });
  }

  window.ChartWindow = { span };

  const orig = Plotly.react;
  Plotly.react = function (gd, data, layout, config) {
    const el = typeof gd === "string" ? document.getElementById(gd) : gd;
    if (!el || !CHARTS.has(el.id) || !Array.isArray(data) || !data.length || !layout)
      return orig.apply(this, arguments);
    const L = decorate(el.id, data, layout);
    el._cwBusy = true;
    const p = orig.call(this, el, data, L, config);
    return Promise.resolve(p).then(r => { bind(el); return r; })
      .finally(() => { el._cwBusy = false; });
  };
})();
