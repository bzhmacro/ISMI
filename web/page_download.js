/* page_download.js — "Download all data" (an arrow icon) on every model page.
   ===========================================================================
   One button per page, in the page's control bar. It writes ONE CSV holding
   the page's data for EVERY country at once, in long format:

       country, dataset, dataset_label, group, date, measure, value

   (one row per country x series x date x measure; empty values are dropped),
   which opens straight into Excel / pandas and pivots any way you like.

   What each page exports — the published payload, i.e. the DEFAULT settings
   the site precomputes for every country, not whatever the sliders on screen
   say. The per-chart csv buttons (chart_export.js) export the on-screen view.

     Breakdown            per gauge: headline 12m; per group, the monthly
                          contribution (w_i * pi_i summed over the group's
                          categories, weights renormalised over the priced
                          basket) and its 12-month (4-quarter) rolling sum;
                          HICP gauges also by special aggregate.
                          Note: on screen, a long gauge's basket also waits for
                          each category's AR benchmark to exist, so the first
                          W months can differ slightly from this file.
     Shock Momentum       per gauge: ISM, S+ and S- at the baseline spec, and
                          the headline.
     Supply vs Demand     per scope: contributions (supply, demand, ambiguous,
                          total), their 12m / 4q versions, the shares, and the
                          published headline.
     Trimmed mean         per scope: every preset (median, trim10/15/16/20,
                          trim_pce) as period rate and y/y, the headline, and
                          the official counterpart where one exists.
     CPI -> PCE           US only: the bridge table, CPI and PCE m/m, and the
                          implied-vs-actual series for both measures.
   =========================================================================== */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);

  /* ---------------------------------------------------------------- data */
  const cache = {};
  const load = (file) => {
    if (file === "ism.json") {
      window.__ismJsonPromise = window.__ismJsonPromise ||
        fetch("data/ism.json", { cache: "no-cache" }).then((r) => {
          if (!r.ok) throw new Error(`ism.json ${r.status}`);
          return r.json();
        });
      return window.__ismJsonPromise;
    }
    return (cache[file] = cache[file] || fetch(`data/${file}`, { cache: "no-cache" })
      .then((r) => { if (!r.ok) throw new Error(`${file} ${r.status}`); return r.json(); }));
  };

  /* Data key -> country name. */
  const COUNTRY = {
    cpi: "United States", pce: "United States", cpi45: "United States",
    cpi70: "United States", headline: "United States", core: "United States",
    goods: "United States", services: "United States",
    uk: "United Kingdom", ea: "Euro area", fr: "France", de: "Germany",
    it: "Italy", es: "Spain", no: "Norway", se: "Sweden", jp: "Japan",
    ca: "Canada", ca_goods: "Canada", ca_services: "Canada",
    au: "Australia", au_m: "Australia", nz: "New Zealand",
  };
  const country = (k) => COUNTRY[k] || k;

  /* ------------------------------------------------------------- writer */
  const HEAD = ["country", "dataset", "dataset_label", "group", "date", "measure", "value"];
  function Rows() {
    const out = [];
    return {
      out,
      /* one series: dates[] and values[] aligned */
      series(ds, label, group, dates, measure, values) {
        if (!values) return;
        for (let t = 0; t < dates.length; t++) {
          const v = values[t];
          if (v == null || !Number.isFinite(+v)) continue;
          out.push([country(ds), ds, label, group || "", dates[t], measure, +v]);
        }
      },
    };
  }
  const q = (v) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  function save(rows, stem, scope = "all_countries") {
    // Built in pieces: the Breakdown file runs to a few hundred thousand rows.
    const parts = ["﻿" + HEAD.join(",") + "\n"];
    const CH = 5000;
    for (let i = 0; i < rows.length; i += CH) {
      parts.push(rows.slice(i, i + CH).map((r) => r.map(q).join(",")).join("\n") + "\n");
    }
    const blob = new Blob(parts, { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${stem}_${scope}_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  const rolling = (arr, h) => arr.map((_, t) => {
    if (t < h - 1) return null;
    let s = 0;
    for (let j = 0; j < h; j++) {
      const v = arr[t - j];
      if (v == null || !Number.isFinite(v)) return null;
      s += v;
    }
    return s;
  });

  /* ----------------------------------------------------------- per page */

  /* Breakdown: group contributions from the panels, as the worker does it
     (wn = w / sum of priced weights; c = wn * pi), every priced category. */
  function groupContrib(b, of, ngroup) {
    const infl = b.panel.inflation, w = b.panel.weights, n = b.dates.length;
    const g = Array.from({ length: ngroup }, () => new Array(n).fill(null));
    for (let t = 0; t < n; t++) {
      let ws = 0;
      for (let c = 0; c < infl.length; c++) {
        if (infl[c][t] != null && w[c][t] != null) ws += w[c][t];
      }
      if (!(ws > 0)) continue;
      for (let k = 0; k < ngroup; k++) g[k][t] = 0;
      for (let c = 0; c < infl.length; c++) {
        if (infl[c][t] == null || w[c][t] == null || of[c] == null || of[c] < 0) continue;
        g[of[c]][t] += (w[c][t] / ws) * infl[c][t];
      }
    }
    return g;
  }

  const AGG = { FOOD: "Food, alcohol & tobacco", NRG: "Energy",
                IGD_NNRG: "Non-energy industrial goods", SERV: "Services" };

  async function breakdown() {
    const d = await load("ism.json");
    const CC = window.CategoryColours;
    const R = Rows();
    for (const [key, b] of Object.entries(d.backbones || {})) {
      if (!b.panel || !b.categories) continue;
      const ppy = b.ppy || 12, hz = ppy === 4 ? "4q" : "12m", per = ppy === 4 ? "1q" : "1m";
      const label = b.label || key;
      if (b.headline) R.series(key, label, "", b.dates, `headline ${b.headline.label || "12m %"}`,
                               b.headline.series);
      const views = [];
      const res = CC && CC.groupsFor(CC.gaugeSpec(key), b.categories);
      if (res) views.push(["", res.list.map((x) => x[1]), res.of]);
      if (b.categories.every((c) => c.agg)) {
        const order = Object.keys(AGG);
        views.push(["special aggregate: ", order.map((k) => AGG[k]),
                    b.categories.map((c) => order.indexOf(c.agg))]);
      }
      for (const [prefix, names, of] of views) {
        const g = groupContrib(b, of, names.length);
        const total = b.dates.map((_, t) => (g[0] && g[0][t] != null
          ? g.reduce((s, a) => s + (a[t] || 0), 0) : null));
        names.forEach((nm, k) => {
          R.series(key, label, prefix + nm, b.dates, `contribution ${per} (pp)`, g[k]);
          R.series(key, label, prefix + nm, b.dates, `contribution ${hz} (pp)`, rolling(g[k], ppy));
        });
        R.series(key, label, prefix + "Total (sum of groups)", b.dates, `contribution ${per} (pp)`, total);
        R.series(key, label, prefix + "Total (sum of groups)", b.dates, `contribution ${hz} (pp)`, rolling(total, ppy));
      }
    }
    save(R.out, "breakdown");
  }

  async function ism() {
    const d = await load("ism.json");
    const R = Rows();
    for (const [key, b] of Object.entries(d.backbones || {})) {
      if (b.pages && !b.pages.includes("ism")) continue;      // breakdown-only gauges
      const label = b.label || key;
      for (const [spec, c] of Object.entries(b.combos || {})) {
        for (const m of ["ISM", "S_pos", "S_neg"]) R.series(key, label, "", b.dates, `${m} [${spec}]`, c[m]);
      }
      if (b.headline) R.series(key, label, "", b.dates, `headline ${b.headline.label || "12m %"}`, b.headline.series);
      if (b.author) for (const m of ["ISM", "S_pos", "S_neg"]) R.series(key, label, "", b.dates, `author ${m}`, b.author[m]);
    }
    save(R.out, "ism");
  }

  async function decomp() {
    const d = await load("decomp.json");
    const R = Rows();
    for (const [key, s] of Object.entries(d.scopes || {})) {
      const label = s.label || key, B = s.baseline || {};
      const hz = s.ppy === 4 ? "4q" : "12m", per = s.ppy === 4 ? "1q" : "1m";
      for (const [k, v] of Object.entries(B.contrib || {})) R.series(key, label, k, s.dates, `contribution ${per} (pp)`, v);
      for (const [k, v] of Object.entries(B.contrib_yoy || {})) R.series(key, label, k, s.dates, `contribution ${hz} (pp)`, v);
      for (const [k, v] of Object.entries(B.shares || {})) R.series(key, label, k, s.dates, "share", v);
      R.series(key, label, "", s.dates, `headline ${hz} (%)`, s.headline_yoy);
    }
    save(R.out, "supply_demand");
  }

  async function trim() {
    const d = await load("trim.json");
    const R = Rows();
    for (const [key, s] of Object.entries(d.scopes || {})) {
      const label = s.label || key;
      for (const [p, v] of Object.entries(s.baseline || {})) {
        R.series(key, label, p, s.dates, "rate (annualised %)", v.rate);
        R.series(key, label, p, s.dates, "y/y (%)", v.yoy);
      }
      if (s.headline) R.series(key, label, "", s.dates, `headline ${s.headline.label || ""}`.trim(), s.headline.series);
      for (const [p, v] of Object.entries(s.official || {})) {
        const g = `official: ${v.label || p}`;
        R.series(key, label, g, s.dates, "rate (annualised %)", v.rate);
        R.series(key, label, g, s.dates, "y/y (%)", v.yoy);
      }
    }
    save(R.out, "trimmed_mean");
  }

  async function cpipce() {
    const d = (await load("trim.json")).cpipce;
    const R = Rows();
    const ds = "us_cpi_pce", label = "CPI to PCE bridge (US)";
    for (const [k, v] of Object.entries(d.table || {})) {
      if (Array.isArray(v) && v.length === d.dates.length) R.series(ds, label, "table", d.dates, k, v);
    }
    for (const [k, v] of Object.entries(d.mom || {})) R.series(ds, label, "m/m", d.dates, k, v);
    for (const [scope, b] of Object.entries((d.bridge && d.bridge.scopes) || {})) {
      for (const [k, v] of Object.entries(b.monthly || {})) R.series(ds, label, `bridge ${scope}`, d.dates, `${k} m/m`, v);
      for (const [k, v] of Object.entries(b.yoy || {})) R.series(ds, label, `bridge ${scope}`, d.dates, `${k} y/y`, v);
    }
    R.out.forEach((r) => { r[0] = "United States"; });
    save(R.out, "cpi_to_pce", "us");
  }

  /* ------------------------------------------------------------- buttons */
  const PAGES = [
    ["breakdown-view", breakdown, "Breakdown: headline and group contributions (monthly and 12-month) for every gauge, at the default settings"],
    ["ism-view", ism, "Shock Momentum: ISM, S+ and S- at the baseline spec, and the headline, for every gauge"],
    ["decomp-view", decomp, "Supply vs Demand: contributions, shares and headline for every scope, at the default settings"],
    ["trim-view", trim, "Trimmed mean: every preset (period rate and y/y), headline and official series, for every scope"],
    ["cpipce-view", cpipce, "CPI → PCE (US only): bridge table, m/m rates and implied vs actual series"],
  ];

  function place(viewId, fn, hint) {
    const view = $(viewId);
    if (!view || view.querySelector(".dl-all")) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "dl-all";
    // Icon only, so the country bar stays on one line; the label lives in the
    // hover tooltip (CSS, from data-tip) and in aria-label for screen readers.
    const label = viewId === "cpipce-view" ? "Download all data" : "Download all data · every country";
    b.setAttribute("aria-label", label);
    b.dataset.tip = `${label}\n${hint}.\nOne CSV, long format.`;
    const ICON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">' +
      '<path d="M9 3h6v8h4.5L12 19.5 4.5 11H9z" fill="currentColor"/>' +
      '<rect x="4" y="20" width="16" height="2.4" rx="1.2" fill="currentColor"/></svg>';
    const state = (html, cls) => { b.innerHTML = html; b.dataset.state = cls || ""; };
    state(ICON);
    b.addEventListener("click", async () => {
      b.disabled = true;
      state("…", "busy");
      try { await fn(); state("✓", "ok"); }
      catch (e) { console.error("[page_download]", e); state("!", "fail"); }
      setTimeout(() => { state(ICON); b.disabled = false; }, 1800);
    });
    // In the control bar next to Settings when the page has one; otherwise a
    // small bar at the top of the page.
    const bar = view.querySelector(".viewbar");
    if (bar) {
      const settings = bar.querySelector(".settings-toggle");
      if (settings) settings.before(b); else bar.appendChild(b);
    } else {
      const wrap = document.createElement("div");
      wrap.className = "dl-bar";
      wrap.appendChild(b);
      view.prepend(wrap);
    }
  }

  function boot() { PAGES.forEach(([id, fn, hint]) => place(id, fn, hint)); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.PageDownload = { breakdown, ism, decomp, trim, cpipce };
})();
