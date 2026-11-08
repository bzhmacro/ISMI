/* category_colours.js — one colour per kind of spending, on every page.
   ===========================================================================
   The Breakdown page groups each gauge's categories by its official top-level
   taxonomy and gives each group a colour from a shared set of spending themes
   (food, housing, health, transport, ...), the same hue in every country. This
   file owns that taxonomy and those colours so every other chart that lists
   categories — ISM drivers, the trimmed-mean cross-section, supply-vs-demand
   drivers, the CPI->PCE bridge — colours a category exactly as the Breakdown
   does.

   API (window.CategoryColours):
     GAUGES, gaugeSpec(key)       per-gauge taxonomy (Breakdown's gauge list)
     groupsFor(spec, categories)  {list: [[id, name, colour]], of: [groupIdx]}
                                  or null when the gauge cannot be grouped
     colourOf(gauge, cat)         colour of one category {key, label, group}:
                                  the Breakdown colour of its group when the
                                  gauge is in ism.json, else the theme of its
                                  own group / label, else null
     themeColour(name)            the theme colour a group name maps to
     colouredTicks(labels, cols)  Plotly tick text in those colours
     ready                        promise: ism.json loaded (colourOf exact)

   Loaded before the view apps. ism.json is shared with app.js and
   breakdown_app.js through window.__ismJsonPromise, so it is fetched once.
   =========================================================================== */
"use strict";

window.CategoryColours = (() => {
  const INK = "#EDE6D6", MUTED = "#B9B2A0";
  const UNCLASSIFIED = "Unclassified";

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

  // COICOP divisions. Two vintages are live at once:
  //   COICOP 1999 — ONS MM23 (uk), 12 divisions, 12 = miscellaneous.
  //   COICOP 2018 — Eurostat ECOICOP v2 (every HICP gauge since Jan 2026),
  //                 13 divisions: 12 = insurance & financial services and
  //                 13 = personal care & miscellaneous. Using the 1999 names on
  //                 HICP data labelled insurance "miscellaneous".
  const COICOP = {
    "01": "Food & non-alcoholic drinks", "02": "Alcohol & tobacco",
    "03": "Clothing & footwear", "04": "Housing, water & fuels",
    "05": "Furnishings & household equipment", "06": "Health",
    "07": "Transport", "08": "Communication", "09": "Recreation & culture",
    "10": "Education", "11": "Restaurants & hotels",
    "12": "Miscellaneous goods & services",
  };
  const COICOP18 = {
    "01": "Food & non-alcoholic drinks", "02": "Alcohol, tobacco & narcotics",
    "03": "Clothing & footwear", "04": "Housing, water & fuels",
    "05": "Furnishings & household equipment", "06": "Health",
    "07": "Transport", "08": "Information & communication",
    "09": "Recreation, sport & culture", "10": "Education",
    "11": "Restaurants & accommodation", "12": "Insurance & financial services",
    "13": "Personal care & miscellaneous",
  };
  const hicp = (key, label) => ({ key, label, names: COICOP18,
    from: (k) => (/^CP\d{2}/i.test(k) && COICOP18[k.slice(2, 4)] ? k.slice(2, 4) : null) });

  /* Per-gauge taxonomy. `from(key)` returns a group code, or null when this
     gauge does not encode one — in which case the view falls back to the
     `group` field on the category if the exporter has started shipping it, and
     otherwise reports the gauge as ungrouped rather than inventing bins. */
  const GAUGES = [
    { key: "cpi", label: "US CPI", names: BLS,
      from: (k) => (/^SE/i.test(k) && BLS[k[2]] ? k[2] : null) },
    { key: "uk", label: "UK", names: COICOP,
      from: (k) => (/^\d{2}\./.test(k) && COICOP[k.slice(0, 2)] ? k.slice(0, 2) : null) },
    hicp("ea", "Euro area"),
    hicp("fr", "France"), hicp("de", "Germany"), hicp("it", "Italy"),
    hicp("es", "Spain"), hicp("no", "Norway"), hicp("se", "Sweden"),
    // Quarterly gauges. Their exporter ships the official top-level group with
    // each category (ABS CPI groups, Stats NZ CPI groups), so `from` is unused.
    { key: "au", label: "Australia", names: null, from: () => null },
    // Complete monthly CPI, April 2024 on. Breakdown page only; the other
    // models use the quarterly `au` series (see the backbone's note).
    { key: "au_m", label: "Australia (monthly)", names: null, from: () => null },
    { key: "nz", label: "New Zealand", names: null, from: () => null },
    // Flat codes; the exporter ships the official parent as `group`.
    { key: "pce", label: "US PCE", names: null, from: () => null },
    { key: "jp", label: "Japan", names: null, from: () => null },
    { key: "ca", label: "Canada", names: null, from: () => null },
  ];

  /* ONE COLOUR PER KIND OF SPENDING, ACROSS COUNTRIES
     -------------------------------------------------
     Every gauge names its top-level groups its own way ("Medical care",
     "Health", "Health & personal care"), so colours by position made the same
     thing teal in one country and red in the next. Instead each group name is
     matched to a shared theme and the theme owns the colour. Order matters:
     the first match wins, which settles combined groups (JP "Transportation &
     communication" -> transport, NZ "Housing and household utilities" ->
     housing, CA "Recreation, education & reading" -> recreation). A name that
     matches nothing falls back to the positional palette. */
  const THEMES = [
    ["alcohol",       /^alcohol|tobacco|cannabis/i,             "#9B6BB0"],
    ["restaurants",   /restaurant|hotel|food services|accommodat/i,                      "#2E8B7A"],
    ["food",          /food/i,                                  "#7FB069"],
    ["clothing",      /cloth|footwear|apparel/i,                "#EFA3C8"],
    ["housing",       /housing|shelter|rent/i,                  "#4C7FD0"],
    ["utilities",     /fuel|light|electric|utilit|energy|water/i, "#F2B134"],
    ["furnishings",   /furnish|furniture|household/i,           "#A68A64"],
    ["health",        /health|medical/i,                        "#EF5B5B"],
    ["transport",     /transport|motor vehicle|^(purchase|operation) of vehicles/i,                             "#E8833A"],
    ["recreation",    /recreat|culture/i,                       "#4FD1C5"],
    ["education",     /educat/i,                                "#D9D36A"],
    ["communication", /communicat/i,                            "#9FA8FF"],
    ["insurance",     /insurance|financ/i,                      "#7D8BA6"],
    ["personal",      /personal care|social protection/i,       "#8E8778"],
    ["misc",          /misc|other|nonprofit/i,                            "#B9B2A0"],
  ];
  const themeColour = (name) => {
    const t = THEMES.find(([, re]) => re.test(String(name || "")));
    return t ? t[2] : null;
  };

  /* When one gauge has several groups on the same theme (US PCE: motor
     vehicles AND transportation services; four "other" lines), the repeats
     keep the hue but step lighter / darker so the stack stays readable. */
  const shade = (hex, f) => {
    const n = parseInt(hex.slice(1), 16);
    const ch = [n >> 16, (n >> 8) & 255, n & 255].map((c) =>
      Math.round(f >= 0 ? c + (255 - c) * f : c * (1 + f)));
    return "#" + ch.map((c) => c.toString(16).padStart(2, "0")).join("");
  };
  const SHADES = [0, 0.4, -0.35, 0.65, -0.55];

  /* Plotly cannot colour individual tick labels via tickfont, but tick text
     accepts <span style="color:...">, so category axes get coloured labels by
     passing tickvals = the categories and ticktext = the same, wrapped. */
  const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const colouredTicks = (cats, colours) => ({
    tickmode: "array", tickvals: cats,
    ticktext: cats.map((c, i) => `<span style="color:${colours[i] || INK}">${esc(c)}</span>`),
  });

  /* Group list + per-category group index for a gauge (the Breakdown's
     COICOP / major-group view). Returns null when nothing can be grouped. */
  function groupsFor(spec, cats) {
    cats = cats || [];
    spec = spec || { names: null, from: () => null };
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
      // JS lists integer-like keys ("10".."13") before "01".."09", so COICOP
      // divisions are re-sorted; BLS letter codes keep their release order.
      const keys = Object.keys(names);
      if (keys.every((k) => /^\d+$/.test(k))) keys.sort();
      const known = keys.filter((k) => seen.has(k));
      const rest = order.filter((k) => !names[k]);
      order.length = 0;
      order.push(...known, ...rest);
      seen.clear();
      order.forEach((id, i) => seen.set(id, i));
    }
    // Themed colour where the name is recognised; otherwise the positional
    // palette, skipping colours a theme has already taken in this gauge.
    const named = order.map((id) => (id === "?" ? UNCLASSIFIED : (names[id] || id)));
    const reps = new Map();
    const themed = named.map((n, i) => {
      if (order[i] === "?") return MUTED;
      const base = themeColour(n);
      if (!base) return null;
      const k = reps.get(base) || 0;
      reps.set(base, k + 1);
      return shade(base, SHADES[k % SHADES.length]);
    });
    const taken = new Set(themed.filter(Boolean));
    let next = 0;
    const list = order.map((id, i) => {
      let col = themed[i];
      while (!col) { const c = colourFor(next++); if (!taken.has(c) || next > 40) { col = c; taken.add(c); } }
      return [id, named[i], col];
    });
    return { list, of: codes.map((c) => seen.get(c == null ? "?" : c)) };
  }

  const gaugeSpec = (key) => GAUGES.find((g) => g.key === key);

  /* Other pages name their series differently from ism.json's backbones. */
  const ALIAS = { cpi45: "cpi", cpi70: "cpi", headline: "pce", core: "pce",
                  goods: "pce", services: "pce" };

  let DATA = null;
  const cache = new Map();          // gauge -> Map(key -> colour)

  function mapFor(gauge) {
    const g = ALIAS[gauge] || gauge;
    if (cache.has(g)) return cache.get(g);
    const b = DATA && DATA.backbones && DATA.backbones[g];
    if (!b) return null;
    const res = groupsFor(gaugeSpec(g), b.categories);
    const m = new Map();
    if (res) b.categories.forEach((c, i) => {
      const grp = res.list[res.of[i]];
      if (grp && grp[0] !== "?") m.set(String(c.key), grp[2]);
    });
    cache.set(g, m);
    return m;
  }

  function colourOf(gauge, cat) {
    if (!cat) return null;
    const m = mapFor(gauge);
    const hit = m && m.get(String(cat.key));
    if (hit) return hit;
    return themeColour(cat.group) || themeColour(cat.label) || null;
  }

  const ready = (window.__ismJsonPromise = window.__ismJsonPromise ||
    fetch("data/ism.json", { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`ism.json ${r.status}`);
      return r.json();
    }));
  ready.then((d) => {
    DATA = d; cache.clear();
    document.dispatchEvent(new CustomEvent("categorycolours"));
    // A page drawn before ism.json arrived used the name-based fallback;
    // redraw the visible one now that the exact colours are known.
    const models = (window.ModelBar && window.ModelBar.models) || [];
    const vis = models.find((m) => { const v = document.getElementById(m.viewId);
                                     return v && !v.hidden; });
    if (vis && typeof vis.refresh === "function") { try { vis.refresh(); } catch (e) { /* not built yet */ } }
  }).catch(() => {});

  return { GAUGES, gaugeSpec, groupsFor, colourOf, themeColour, shade,
           colouredTicks, esc, ready, INK, MUTED, UNCLASSIFIED };
})();
