/* chart_export.js — every chart is takeable.
   ===========================================================================
   Same five buttons, same order, on every figure (the house model, as on the
   eurex-offbook explorer):

       ⧉ copy   the chart as a PNG on the clipboard, ready to paste
       png      2x PNG download
       svg      vector SVG — scales, and stays editable
       csv      the numbers actually plotted
       ⧉ data   the same numbers as TSV on the clipboard, for a spreadsheet

   A single "light exports" switch in the model nav decides the palette of
   every image export: off = the dark screen palette, on = the paper palette
   for notes and PDFs (house rule: never emit a dark PDF). Session-only and
   deliberately not persisted — a toggle that silently remembers last week is
   worse than one that does not remember at all.

   EXPORT WHAT IS PLOTTED
   ----------------------
   Plotly stores the current figure on the graph div itself (`gd.data`,
   `gd.layout`), so this file reads what is on screen at click time and the
   view apps need no changes. That includes the zoom: an image is the window
   the reader is looking at, and csv / data keep only the points inside the
   current x range of a date axis.

   PAPER RENDERING
   ---------------
   The figure is deep-cloned, recoloured against the light token set when
   "light exports" is on, and rendered on an offscreen stage before
   Plotly.toImage. The stage is pushed off-canvas rather than display:none —
   Plotly cannot measure a zero-size node and would emit a blank image.
   =========================================================================== */

(() => {
  "use strict";

  /* Charts to decorate: [graph div id, filename stem, human title].
     A chart whose div is absent (view not built yet) is simply skipped and
     picked up on the next pass. */
  const CHARTS = [
    ["b-chart",         "breakdown-groups",     "Contributions by major group"],
    ["b-groups",        "breakdown-expected",   "Expected vs surprise, by group"],
    ["b-surprises",     "breakdown-surprises",  "Biggest surprises vs AR benchmark"],
    ["chart",           "ism-index",            "Inflation Shock Momentum"],
    ["bars",            "ism-last22",           "Last 22 ISM prints"],
    ["drivers",         "ism-drivers",          "Top drivers"],
    ["d-chart",         "decomp-contributions", "Supply vs demand"],
    ["d-bars",          "decomp-last22",        "Last 22 periods, supply vs demand"],
    ["d-drivers",       "decomp-drivers",       "Top category drivers"],
    ["t-chart",         "trim-index",           "Trimmed mean & median"],
    ["t-cross",         "trim-cross-section",   "Cross-section"],
    ["t-weights-chart", "trim-weights",         "Weights that moved most"],
    ["x-chart",         "cpipce-bridge",        "CPI to PCE"],
    ["x-bars",          "cpipce-contributions", "Implied contributions"],
  ];

  /* Light palette for the paper export. These are the bzh print tokens — the
     accents auto-darkened until they clear 4.5:1 on white — hard-coded because
     Plotly needs literal colours, not CSS variables. Keep in step with the
     @generated:print block in bzh.css. */
  const PAPER = {
    bg: "#FFFFFF",
    panel: "#F7F4EC",
    ink: "#191D26",
    dim: "#4E5464",
    grid: "#DAD2C0",
    /* Dark-screen colour -> paper equivalent. Anything not listed is passed
       through, so a series colour we have not mapped still exports, just
       unadjusted. */
    map: {
      "#171e26": "#FFFFFF", "#161D2C": "#FFFFFF", "#0E1420": "#FFFFFF",
      "#243240": "#DAD2C0", "#2A3448": "#DAD2C0",
      "#e6edf3": "#191D26", "#EDE6D6": "#191D26",
      "#8b98a5": "#4E5464", "#B9B2A0": "#4E5464", "#6B7488": "#7B8192",
      "#CE5533": "#C75130", "#BE8A31": "#956D27", "#2AA695": "#218174",
      "#4FBFAE": "#218174", "#E07B5F": "#B4492A",
      "#f5a623": "#956D27", "#4c9aff": "#2A5FA8",
      "#d05ce3": "#8E35A0", "#2dd4bf": "#218174",
      "#5E9CD8": "#2A5FA8", "#8A85E8": "#5450C0", "#7FB069": "#4C7A38",
      // Breakdown spending themes (breakdown_app.js THEMES)
      "#9B6BB0": "#7A4B90", "#2E8B7A": "#226B5E", "#EFA3C8": "#B8507F",
      "#4C7FD0": "#2F5FA8", "#F2B134": "#A87412", "#A68A64": "#7A6240",
      "#EF5B5B": "#C23A3A", "#E8833A": "#B85A1A", "#4FD1C5": "#1F8F86",
      "#D9D36A": "#8A8420", "#9FA8FF": "#5A64C8", "#7D8BA6": "#55617A",
      "#8E8778": "#66604F",
    },
  };

  const $ = (id) => document.getElementById(id);
  const nowStamp = () => new Date().toISOString().slice(0, 10);

  /* ------------------------------------------------------------------ */
  /* provenance                                                          */
  /* ------------------------------------------------------------------ */

  /* What the image should say about itself once it is out of the browser:
     which model, which parameter combo, data through when. Read from the DOM
     so it reflects the live controls without the apps reporting anything. */
  function provenance() {
    const active = document.querySelector(".snav-link.active");
    const model = active ? active.textContent.trim() : "";

    // The readout strip carries "Spec" (ISM) or the equivalent combo label.
    let spec = "";
    const view = document.querySelector(".model-view:not([hidden])");
    if (view) {
      const stats = view.querySelectorAll(".statrow .stat");
      for (const s of stats) {
        const lbl = s.querySelector("span");
        const val = s.querySelector("b");
        if (lbl && val && /spec|combo|param/i.test(lbl.textContent)) {
          spec = val.textContent.trim();
          break;
        }
      }
    }

    // "Data through YYYY-MM" from the as-of line.
    let through = "";
    const asof = $("asof");
    if (asof) {
      const m = /through\s+(\d{4}-\d{2})/i.exec(asof.textContent || "");
      if (m) through = m[1];
    }
    return { model, spec, through };
  }

  function captionFor(title) {
    const p = provenance();
    const bits = [];
    if (p.model) bits.push(p.model);
    if (p.spec) bits.push(p.spec);
    if (p.through) bits.push(`data through ${p.through}`);
    return {
      title: title + (p.spec ? `  ·  ${p.spec}` : ""),
      sub: bits.join("  ·  "),
      source: "bzhmacro.com — derived from public sources. Estimates, not official publications.",
    };
  }

  /* ------------------------------------------------------------------ */
  /* colour rewriting                                                    */
  /* ------------------------------------------------------------------ */

  const toPaper = (c) => {
    if (typeof c !== "string") return c;
    const hit = PAPER.map[c] || PAPER.map[c.toLowerCase()] || PAPER.map[c.toUpperCase()];
    return hit || c;
  };

  /* Walk an arbitrary Plotly object and rewrite any colour-ish string. Plotly
     puts colours under a lot of keys (color, bgcolor, line.color, marker.color,
     gridcolor, ...), so match on the key name rather than enumerating paths. */
  function recolour(obj) {
    if (Array.isArray(obj)) return obj.map(recolour);
    if (obj && typeof obj === "object") {
      const out = {};
      for (const [k, v] of Object.entries(obj)) {
        if (/color$/i.test(k)) {
          out[k] = Array.isArray(v) ? v.map(toPaper) : toPaper(v);
        } else if (k === "ticktext" && Array.isArray(v)) {
          // coloured category labels carry their colour inside the HTML
          out[k] = v.map((t) => (typeof t === "string"
            ? t.replace(/color:\s*(#[0-9a-f]{6})/gi, (m, c) => "color:" + toPaper(c)) : t));
        } else out[k] = recolour(v);
      }
      return out;
    }
    return obj;
  }

  /* ------------------------------------------------------------------ */
  /* export                                                              */
  /* ------------------------------------------------------------------ */

  function stage() {
    let s = $("chart-export-stage");
    if (!s) {
      s = document.createElement("div");
      s.id = "chart-export-stage";
      document.body.appendChild(s);
    }
    return s;
  }

  function triggerDownload(href, filename, revoke) {
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    if (revoke) setTimeout(() => URL.revokeObjectURL(href), 2000);
  }
  const downloadBlob = (blob, name) => triggerDownload(URL.createObjectURL(blob), name, true);

  /* Session-only palette switch (see header). */
  let LIGHT = false;

  const slug = (t) => String(t || "chart").toLowerCase()
    .replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  const fileStem = (title) => `${slug(title)}_${nowStamp()}`;

  /* The clone that gets rendered: the live figure, its current zoom included,
     plus title, standfirst and source furniture. */
  function exportFigure(gd, title, light) {
    if (!window.Plotly || !gd || !gd.data) throw new Error("chart not ready");
    const cap = captionFor(title);
    const data = light ? recolour(gd.data) : JSON.parse(JSON.stringify(gd.data));
    const layout = light ? recolour(gd.layout) : JSON.parse(JSON.stringify(gd.layout));

    const ink = light ? PAPER.ink : "#EDE6D6";
    const dim = light ? PAPER.dim : "#B9B2A0";
    const bg = light ? PAPER.bg : "#161D2C";

    layout.paper_bgcolor = bg;
    layout.plot_bgcolor = light ? PAPER.bg : (layout.plot_bgcolor || bg);
    layout.font = Object.assign({}, layout.font, { color: ink,
      family: "'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif" });
    layout.margin = Object.assign({}, layout.margin, { t: 86, b: 62 });
    layout.title = {
      text: `<b>${cap.title}</b>` + (cap.sub ? `<br><span style="font-size:11px">${cap.sub}</span>` : ""),
      x: 0, xanchor: "left", y: 0.97, yanchor: "top",
      font: { size: 16, color: ink },
    };
    layout.annotations = (layout.annotations || []).concat([{
      text: cap.source,
      showarrow: false, xref: "paper", yref: "paper",
      x: 0, xanchor: "left", y: -0.14, yanchor: "top",
      font: { size: 10, color: dim, family: "'IBM Plex Mono', monospace" },
    }]);
    // The on-screen range buttons are interaction, not content.
    Object.keys(layout).filter((k) => /^xaxis\d*$/.test(k)).forEach((k) => {
      if (layout[k] && layout[k].rangeselector) layout[k].rangeselector = { visible: false };
    });
    layout.showlegend = layout.showlegend !== false;
    layout.width = 1200;
    layout.height = 675;
    return { data, layout, bg };
  }

  async function renderImage(gd, title, format) {
    const { data, layout } = exportFigure(gd, title, LIGHT);
    const host = stage();
    await window.Plotly.newPlot(host, data, layout, { staticPlot: true, displayModeBar: false });
    try {
      return await window.Plotly.toImage(host,
        { format, width: 1200, height: 675, scale: format === "png" ? 2 : 1 });
    } finally {
      window.Plotly.purge(host);
    }
  }

  const dataUrlToBlob = async (url) => (await fetch(url)).blob();
  const suffix = () => (LIGHT ? "_light" : "");

  async function exportPng(gd, stem, title) {
    const url = await renderImage(gd, title, "png");
    triggerDownload(url, `${fileStem(title)}${suffix()}.png`, false);
  }

  async function exportSvg(gd, stem, title) {
    const url = await renderImage(gd, title, "svg");
    // Plotly returns a URI-encoded data URL for svg
    const svg = decodeURIComponent(url.replace(/^data:image\/svg\+xml,/, ""));
    downloadBlob(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }),
      `${fileStem(title)}${suffix()}.svg`);
  }

  async function copyPng(gd, stem, title) {
    const url = await renderImage(gd, title, "png");
    const blob = await dataUrlToBlob(url);
    if (!navigator.clipboard || !window.ClipboardItem) {
      downloadBlob(blob, `${fileStem(title)}${suffix()}.png`);
      return "saved instead";
    }
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      return "copied";
    } catch (e) {
      downloadBlob(blob, `${fileStem(title)}${suffix()}.png`);
      return "saved instead";
    }
  }

  /* The plotted numbers, as {head, rows}. Traces become columns keyed on the
     union of their category values (x, or y for horizontal bars), so series of
     different lengths still line up. On a date axis only the points inside
     the current x range are kept: export what is on screen. */
  function plottedRows(gd) {
    if (!gd || !gd.data || !gd.data.length) throw new Error("chart not ready");
    const traces = gd.data.filter((t) => t && t.x && t.y &&
      t.visible !== false && t.visible !== "legendonly");
    if (!traces.length) return null;
    const horiz = traces.every((t) => t.orientation === "h");
    const keyOf = (v) => (v instanceof Date ? v.toISOString().slice(0, 10) : String(v));
    const catsOf = (t) => (horiz ? t.y : t.x);
    const valsOf = (t) => (horiz ? t.x : t.y);

    let lo = -Infinity, hi = Infinity;
    const xa = gd.layout && gd.layout.xaxis;
    if (!horiz && xa && xa.type === "date" && Array.isArray(xa.range)) {
      lo = Date.parse(String(xa.range[0]).slice(0, 10));
      hi = Date.parse(String(xa.range[1]).slice(0, 10));
    }
    const inWindow = (k) => {
      if (lo === -Infinity) return true;
      const t = Date.parse(k.length === 7 ? k + "-01" : k.slice(0, 10));
      return !Number.isFinite(t) || (t >= lo && t <= hi);
    };

    const keys = [], seen = new Set();
    traces.forEach((t) => catsOf(t).forEach((x) => {
      const k = keyOf(x);
      if (!seen.has(k) && inWindow(k)) { seen.add(k); keys.push(k); }
    }));
    const sortable = keys.every((k) => /^\d{4}-\d{2}/.test(k) || /^-?\d+(\.\d+)?$/.test(k));
    if (sortable) keys.sort();
    const lookup = traces.map((t) => {
      const m = new Map(), v = valsOf(t);
      catsOf(t).forEach((x, i) => m.set(keyOf(x), v[i]));
      return m;
    });
    const xTitle = horiz ? "category" : "x";
    return {
      head: [xTitle, ...traces.map((t, i) => t.name || `series_${i + 1}`)],
      rows: keys.map((k) => [k, ...lookup.map((m) => (m.get(k) == null ? "" : m.get(k)))]),
    };
  }

  function toDelimited(d, sep) {
    const q = (v) => {
      v = v == null ? "" : String(v);
      return sep === "," && /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
    };
    return [d.head.map(q).join(sep)].concat(d.rows.map((r) => r.map(q).join(sep))).join("\n");
  }

  function exportCsv(gd, stem, title) {
    const d = plottedRows(gd);
    if (!d || !d.rows.length) return "no data";
    const p = provenance();
    const meta = [`# ${title}${p.spec ? ` — ${p.spec}` : ""}`];
    if (p.model) meta.push(`# model: ${p.model}`);
    if (p.through) meta.push(`# data through: ${p.through}`);
    meta.push(`# exported: ${new Date().toISOString()}`);
    meta.push("# source: bzhmacro.com — derived from public sources. Estimates, not official publications.");
    // BOM, or Excel mangles the UTF-8 in the labels
    downloadBlob(new Blob(["﻿" + meta.join("\n") + "\n" + toDelimited(d, ",")],
      { type: "text/csv;charset=utf-8" }), `${fileStem(title)}.csv`);
    return "saved";
  }

  async function copyData(gd) {
    const d = plottedRows(gd);
    if (!d || !d.rows.length) return "no data";
    await navigator.clipboard.writeText(toDelimited(d, "\t"));
    return "copied";
  }

  /* ------------------------------------------------------------------ */
  /* toolbar                                                             */
  /* ------------------------------------------------------------------ */

  function flash(btn, text, bad) {
    const original = btn.dataset.label || btn.textContent;
    btn.dataset.label = original;
    btn.textContent = text;
    btn.classList.toggle("done", !bad);
    btn.classList.toggle("bad", Boolean(bad));
    clearTimeout(btn._t);
    btn._t = setTimeout(() => {
      btn.textContent = original;
      btn.classList.remove("done", "bad");
    }, 1400);
  }

  const TOOLS = [
    ["copy", "⧉ copy", "Copy the chart as an image, ready to paste", copyPng],
    ["png", "png", "Download a 2× PNG", async (...a) => { await exportPng(...a); return "saved"; }],
    ["svg", "svg", "Download vector SVG — scales, and stays editable",
      async (...a) => { await exportSvg(...a); return "saved"; }],
    ["csv", "csv", "Download the numbers actually plotted (the current zoom window)", exportCsv],
    ["data", "⧉ data", "Copy the numbers as TSV, for a spreadsheet", copyData],
  ];

  function addTools(id, stem, title) {
    const gd = $(id);
    if (!gd || gd.dataset.exportReady === "1") return;

    // Wrap so the toolbar sits over the chart without disturbing the chart's
    // own box (Plotly owns the graph div's children).
    const wrap = document.createElement("div");
    wrap.className = "chart-wrap";
    gd.parentNode.insertBefore(wrap, gd);
    wrap.appendChild(gd);

    const tools = document.createElement("div");
    tools.className = "chart-tools fig-tools";
    TOOLS.forEach(([key, label, hint, fn]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tbtn";
      b.textContent = label;
      b.title = hint;
      b.dataset.x = key;
      b.addEventListener("click", async (e) => {
        e.preventDefault();
        b.disabled = true;
        try {
          const msg = await fn(gd, stem, title);
          flash(b, msg || "saved", msg === "no data");
        } catch (err) {
          flash(b, "failed", true);
          console.error(`[chart_export] ${id}:`, err);
        } finally {
          b.disabled = false;
        }
      });
      tools.appendChild(b);
    });

    wrap.insertBefore(tools, gd);
    gd.dataset.exportReady = "1";
  }

  /* "light exports" switch, appended to the model nav (which models.js builds
     at load). Idempotent. */
  function lightToggle() {
    const nav = $("model");
    if (!nav || $("lightToggle")) return;
    const lab = document.createElement("label");
    lab.className = "lighttog";
    lab.title = "Export figures on white, for documents";
    lab.innerHTML = '<input type="checkbox" id="lightToggle"> light exports';
    nav.appendChild(lab);
    const t = $("lightToggle");
    t.checked = LIGHT;
    t.addEventListener("change", () => { LIGHT = t.checked; });
  }

  function scan() {
    lightToggle();
    for (const [id, stem, title] of CHARTS) addTools(id, stem, title);
  }

  /* Views are built lazily the first time a model is shown, so a single pass at
     load would only ever find the first view's charts. Re-scan on model switch
     (ModelBar fires this) and keep a cheap periodic sweep as a backstop for
     charts created asynchronously after a worker returns. */
  function boot() {
    scan();
    document.addEventListener("modelshown", scan);
    let sweeps = 0;
    const iv = setInterval(() => {
      scan();
      if (++sweeps > 40) clearInterval(iv);   // ~2 min, then stop
    }, 3000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else boot();

  window.ChartExport = {
    scan, exportPng, exportSvg, exportCsv, plottedRows, toDelimited,
    get light() { return LIGHT; }, set light(v) { LIGHT = Boolean(v); },
  };
})();
