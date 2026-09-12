/* chart_export.js — per-chart PNG and CSV export.
   ===========================================================================
   Adds a small hover toolbar to every Plotly chart on the page:

       PNG        dark palette, matches the screen
       PNG PAPER  light palette, for notes and PDFs (house rule: never emit a
                  dark PDF)
       CSV        the plotted series, as rendered

   HOW IT AVOIDS TOUCHING THE FOUR VIEW APPS
   -----------------------------------------
   Plotly stores the current figure on the graph div itself — `gd.data` and
   `gd.layout`. So this file reads what is on screen rather than asking the
   apps to hand it over, which means app.js / decomp_app.js / trim_app.js /
   cpipce_app.js need no changes at all. The apps call Plotly.react() freely;
   we always read the state at click time.

   The charts are created with `displayModeBar: false`, so Plotly's own toolbar
   never appears and this replaces it. We deliberately do not re-enable the
   modebar: its PNG export has no paper palette, no branding furniture, and
   ignores the parameter combo the figure was computed with — which is the part
   that actually gets lost once an image leaves the site.

   PAPER RENDERING
   ---------------
   Plotly cannot restyle a figure to a different palette in place without
   disturbing what the user is looking at, so the paper export deep-clones the
   figure, rewrites colours against the light token set, and renders the clone
   on an offscreen stage before calling Plotly.toImage. The stage is positioned
   far off-canvas rather than display:none — Plotly cannot measure a zero-size
   node and would emit a blank image.
   =========================================================================== */

(() => {
  "use strict";

  /* Charts to decorate: [graph div id, filename stem, human title].
     A chart whose div is absent (view not built yet) is simply skipped and
     picked up on the next pass. */
  const CHARTS = [
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

  async function exportPng(gd, stem, title, paper) {
    if (!window.Plotly || !gd || !gd.data) throw new Error("chart not ready");
    const cap = captionFor(title);

    const data = paper ? recolour(gd.data) : JSON.parse(JSON.stringify(gd.data));
    const layout = paper ? recolour(gd.layout) : JSON.parse(JSON.stringify(gd.layout));

    const ink = paper ? PAPER.ink : "#EDE6D6";
    const dim = paper ? PAPER.dim : "#B9B2A0";
    const bg = paper ? PAPER.bg : "#0E1420";

    // Branding furniture. Top margin grows to fit title + standfirst; a source
    // line is pinned under the plot. Both are paper-annotations so they sit in
    // figure space and survive any axis range.
    layout.paper_bgcolor = bg;
    layout.plot_bgcolor = paper ? PAPER.bg : (layout.plot_bgcolor || bg);
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
    layout.showlegend = layout.showlegend !== false;
    layout.width = 1200;
    layout.height = 675;

    const host = stage();
    await window.Plotly.newPlot(host, data, layout,
      { staticPlot: true, displayModeBar: false });
    const url = await window.Plotly.toImage(host,
      { format: "png", width: 1200, height: 675, scale: 2 });
    window.Plotly.purge(host);

    triggerDownload(url, `${stem}${paper ? "-paper" : ""}-${nowStamp()}.png`, false);
  }

  /* CSV of exactly what is plotted. Traces are emitted as columns keyed on the
     union of their x values, so a chart mixing series of different lengths (the
     author overlay starts later than the index, for instance) still lines up
     instead of silently truncating to the shortest. */
  function exportCsv(gd, stem, title) {
    if (!gd || !gd.data || !gd.data.length) throw new Error("chart not ready");
    const traces = gd.data.filter((t) => t && t.x && t.y);
    if (!traces.length) throw new Error("no x/y series on this chart");

    const keys = [];
    const seen = new Set();
    for (const t of traces) {
      for (const x of t.x) {
        const k = x instanceof Date ? x.toISOString().slice(0, 10) : String(x);
        if (!seen.has(k)) { seen.add(k); keys.push(k); }
      }
    }
    // Only sort when every key looks like a date/number; category axes (driver
    // bar charts) must keep the order Plotly was given.
    const sortable = keys.every((k) => /^\d{4}-\d{2}/.test(k) || /^-?\d+(\.\d+)?$/.test(k));
    if (sortable) keys.sort();

    const lookup = traces.map((t) => {
      const m = new Map();
      t.x.forEach((x, i) => {
        const k = x instanceof Date ? x.toISOString().slice(0, 10) : String(x);
        m.set(k, t.y[i]);
      });
      return m;
    });

    const esc = (s) => {
      const v = s == null ? "" : String(s);
      return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
    };
    const names = traces.map((t, i) => t.name || `series_${i + 1}`);
    const p = provenance();

    const lines = [];
    lines.push(`# ${title}${p.spec ? ` — ${p.spec}` : ""}`);
    if (p.model) lines.push(`# model: ${p.model}`);
    if (p.through) lines.push(`# data through: ${p.through}`);
    lines.push(`# exported: ${new Date().toISOString()}`);
    lines.push("# source: bzhmacro.com — derived from public sources. Estimates, not official publications.");
    lines.push(["x", ...names].map(esc).join(","));
    for (const k of keys) {
      lines.push([k, ...lookup.map((m) => {
        const v = m.get(k);
        return v == null ? "" : v;
      })].map(esc).join(","));
    }

    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    triggerDownload(URL.createObjectURL(blob), `${stem}-${nowStamp()}.csv`, true);
  }

  /* ------------------------------------------------------------------ */
  /* toolbar                                                             */
  /* ------------------------------------------------------------------ */

  function flash(btn, text, ok) {
    const original = btn.textContent;
    btn.textContent = text;
    btn.classList.toggle("done", Boolean(ok));
    setTimeout(() => {
      btn.textContent = original;
      btn.classList.remove("done");
    }, 1600);
  }

  function addTools(id, stem, title) {
    const gd = $(id);
    if (!gd || gd.dataset.exportReady === "1") return;

    // Wrap so the toolbar can be absolutely positioned over the chart without
    // disturbing the chart's own box (Plotly owns the graph div's children).
    const wrap = document.createElement("div");
    wrap.className = "chart-wrap";
    gd.parentNode.insertBefore(wrap, gd);
    wrap.appendChild(gd);

    const tools = document.createElement("div");
    tools.className = "chart-tools";

    const mk = (label, hint, fn) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.title = hint;
      b.addEventListener("click", async (e) => {
        e.preventDefault();
        b.disabled = true;
        try {
          await fn();
          flash(b, "✓", true);
        } catch (err) {
          flash(b, "failed", false);
          console.error(`[chart_export] ${id}:`, err);
        } finally {
          b.disabled = false;
        }
      });
      return b;
    };

    tools.appendChild(mk("PNG", "Download as PNG (dark, matches the screen)",
      () => exportPng(gd, stem, title, false)));
    tools.appendChild(mk("PAPER", "Download as PNG on a light background, for notes and PDFs",
      () => exportPng(gd, stem, title, true)));
    tools.appendChild(mk("CSV", "Download the plotted series as CSV",
      () => exportCsv(gd, stem, title)));

    wrap.appendChild(tools);
    gd.dataset.exportReady = "1";
  }

  function scan() {
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

  window.ChartExport = { scan, exportPng, exportCsv };
})();
