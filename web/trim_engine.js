/* Trimmed-mean / median inflation engine — JavaScript port of the maths in
   src/ism/trim_engine.py (Eqs. T1-T4).

   This file is the browser twin of the Python engine. It must stay in sync
   with it; the contract is enforced by tests/test_trim_parity.py, which runs
   both implementations on the same synthetic panel and asserts the outputs
   match to 1e-9.

   Design notes
   ------------
   * The expensive part is not the trim (one sort per month) but the ROLLING
     seasonal adjustment, which re-estimates twelve month effects at every
     (category, month). We keep per-calendar-month prefix sums of the value and
     of the finite-count, so a window's month effects come out in O(12) instead
     of O(W) — that is what lets the SA control stay live.
   * The seasonal factors depend only on (panel, method, window), never on the
     trim fractions or the weights, so they are cached by the worker and a
     trim-slider drag costs one pass of sorts.
   * Columns are Float64Array. NaN means "not available this month"; a category
     with a NaN value or a non-positive weight simply leaves the cross-section,
     exactly as in the Python engine.
   * Works in a Web Worker (importScripts), a <script> tag, and Node
     (module.exports) — Node is what the parity test drives. No dependencies. */
"use strict";

const TrimEngine = (() => {

  // -------------------------------------------------------------------
  // Panel plumbing
  // -------------------------------------------------------------------
  /* rows = months, cols = categories. `inflation` and `weights` arrive as
     arrays-of-columns (one array per category), matching the JSON payload. */
  function toPanel(inflation, weights, months) {
    const k = inflation.length, n = k ? inflation[0].length : 0;
    const infl = new Array(k), w = new Array(k);
    for (let j = 0; j < k; j++) {
      infl[j] = Float64Array.from(inflation[j], v => (v == null ? NaN : v));
      w[j] = Float64Array.from(weights[j], v => (v == null ? NaN : v));
    }
    return { infl, w, n, k, months: months || null };
  }

  /* Calendar slot (0-based) of each row. `months` is an array of "YYYY-MM"
     strings; without it we fall back to position within the year, which is
     what the Python engine does for exotic frequencies. */
  function seasonOf(months, n, ppy) {
    const out = new Int32Array(n);
    if (months && months.length === n && ppy === 12) {
      for (let i = 0; i < n; i++) out[i] = (parseInt(months[i].slice(5, 7), 10) - 1) | 0;
      return out;
    }
    if (months && months.length === n && ppy === 4) {
      for (let i = 0; i < n; i++) out[i] = ((parseInt(months[i].slice(5, 7), 10) - 1) / 3) | 0;
      return out;
    }
    for (let i = 0; i < n; i++) out[i] = i % ppy;
    return out;
  }

  // -------------------------------------------------------------------
  // (T1) Seasonal adjustment
  // -------------------------------------------------------------------
  /* Month effects, re-centred to sum to zero so the annual average is
     untouched. Returns null when any calendar slot has no finite observation
     in the window — a partial factor vector would shift the annual average,
     which is exactly what the centring prevents (mirrors _centred_season_means
     returning None). */
  function centredSeasonMeans(sum, cnt, ppy, out) {
    let total = 0;
    for (let m = 0; m < ppy; m++) {
      if (cnt[m] === 0) return false;
      out[m] = sum[m] / cnt[m];
      total += out[m];
    }
    const mean = total / ppy;
    for (let m = 0; m < ppy; m++) out[m] -= mean;
    return true;
  }

  /* Factors to SUBTRACT, one value per (month, category). NaN where none
     could be estimated; deseasonalise() then leaves the raw value alone. */
  function seasonalFactors(panel, method, window, ppy) {
    const { infl, n, k } = panel;
    const out = new Array(k);
    if (method === "none") {
      for (let j = 0; j < k; j++) out[j] = new Float64Array(n);   // zeros
      return out;
    }
    const season = seasonOf(panel.months, n, ppy);
    const fac = new Float64Array(ppy);

    for (let j = 0; j < k; j++) {
      const col = infl[j], res = new Float64Array(n).fill(NaN);

      if (method === "dummy") {
        // One set of effects from the whole sample.
        const sum = new Float64Array(ppy), cnt = new Float64Array(ppy);
        for (let i = 0; i < n; i++) {
          const v = col[i];
          if (Number.isFinite(v)) { sum[season[i]] += v; cnt[season[i]]++; }
        }
        if (centredSeasonMeans(sum, cnt, ppy, fac))
          for (let i = 0; i < n; i++) res[i] = fac[season[i]];
        out[j] = res;
        continue;
      }

      // "rolling": trailing window, no future data. Prefix sums per calendar
      // slot turn each window into O(ppy) work.
      const psum = new Array(ppy), pcnt = new Array(ppy);
      for (let m = 0; m < ppy; m++) {
        psum[m] = new Float64Array(n + 1);
        pcnt[m] = new Float64Array(n + 1);
      }
      for (let i = 0; i < n; i++) {
        for (let m = 0; m < ppy; m++) { psum[m][i + 1] = psum[m][i]; pcnt[m][i + 1] = pcnt[m][i]; }
        const v = col[i];
        if (Number.isFinite(v)) { psum[season[i]][i + 1] += v; pcnt[season[i]][i + 1]++; }
      }
      const minRows = 2 * ppy;
      const sum = new Float64Array(ppy), cnt = new Float64Array(ppy);
      for (let i = 0; i < n; i++) {
        const start = Math.max(0, i - window + 1);
        if (i - start + 1 < minRows) continue;
        for (let m = 0; m < ppy; m++) {
          sum[m] = psum[m][i + 1] - psum[m][start];
          cnt[m] = pcnt[m][i + 1] - pcnt[m][start];
        }
        if (centredSeasonMeans(sum, cnt, ppy, fac)) res[i] = fac[season[i]];
      }
      out[j] = res;
    }
    return out;
  }

  /* panel.infl minus its factors, then annualised (Eqs. T1 + T2). Returns
     arrays-of-columns of the cross-section actually trimmed. */
  function seasonallyAdjustedAnnual(panel, opts) {
    const { sa = "rolling", saWindow = 120, annualize = "compound", ppy = 12 } = opts || {};
    const fac = seasonalFactors(panel, sa, saWindow, ppy);
    const { infl, n, k } = panel;
    const out = new Array(k);
    for (let j = 0; j < k; j++) {
      const col = infl[j], f = fac[j], res = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        const adj = col[i] - (Number.isFinite(f[i]) ? f[i] : 0);
        res[i] = annualize === "log" ? adj * ppy
                                     : 100 * (Math.pow(1 + adj / 100, ppy) - 1);
      }
      out[j] = res;
    }
    return out;
  }

  function deannualise(rate, annualize, ppy) {
    if (!Number.isFinite(rate)) return NaN;
    return annualize === "log" ? rate / ppy
                               : 100 * (Math.pow(1 + rate / 100, 1 / ppy) - 1);
  }

  // -------------------------------------------------------------------
  // (T3) The cross-sectional estimator
  // -------------------------------------------------------------------
  /* Weighted trimmed mean of one cross-section. `idx` is scratch: the indices
     of the usable categories, already sorted by value. Categories straddling a
     trim point enter partially, which keeps the estimator continuous in the
     trim fractions. lower + upper == 1 degenerates to the weighted median and
     is handled as that limit. */
  function trimOne(values, weights, idx, m, lower, upper, wnorm) {
    if (m === 0) return NaN;
    if (lower + upper >= 1 - 1e-12) {
      // weighted percentile at `lower`: the value of the category holding that
      // quantile of the weight — a real category's rate, never an interpolation
      let cum = 0;
      for (let t = 0; t < m; t++) {
        cum += wnorm[t];
        if (cum >= lower - 1e-15) return values[idx[t]];
      }
      return values[idx[m - 1]];
    }
    const hi = 1 - upper;
    let cumLo = 0, num = 0, den = 0;
    for (let t = 0; t < m; t++) {
      const cumHi = cumLo;
      cumLo += wnorm[t];
      const keep = Math.min(cumLo, hi) - Math.max(cumHi, lower);
      if (keep > 0) { num += keep * values[idx[t]]; den += keep; }
    }
    return den > 0 ? num / den : NaN;
  }

  /* Per-category label for the cross-section chart, plus the weight each
     category actually contributed.

       -1  entirely below the lower trim point — cut from the bottom
        0  entirely inside the retained interval — included
       +1  entirely above the upper trim point — cut from the top
        2  STRADDLES a trim point: part of its weight was retained
       -2  unusable

     The straddling label matters. Because boundary categories enter partially
     (Eq. T3), a category can supply a large share of the retained weight while
     most of its own weight sits in a tail — on the shipped panels at the
     published trim points that happens in roughly seven months out of ten, and
     the straddling category has contributed up to 17% of the basket. Colouring
     it "cut" would tell the reader a category that drove the number had been
     thrown away. The Dallas Fed's own component table marks that row
     "Trim point" for the same reason.

     `kept` receives the retained weight share per category, so the bars can be
     sized by what each one actually contributed rather than by its full
     weight. */
  function membershipOne(idx, m, lower, upper, wnorm, out, k, kept) {
    out.fill(-2, 0, k);
    if (kept) kept.fill(0, 0, k);
    const hi = Math.max(lower, 1 - upper);
    const tol = 1e-12;
    let cumLo = 0;
    for (let t = 0; t < m; t++) {
      const cumHi = cumLo;
      cumLo += wnorm[t];
      const inside = Math.max(0, Math.min(cumLo, hi) - Math.max(cumHi, lower));
      const j = idx[t];
      if (kept) kept[j] = inside;
      if (inside >= wnorm[t] - tol) out[j] = 0;            // fully retained
      else if (inside > tol) out[j] = 2;                   // the trim point
      else if (cumHi >= hi - tol) out[j] = 1;              // cut from the top
      else out[j] = -1;                                    // cut from the bottom
    }
  }

  // -------------------------------------------------------------------
  // (T4) Chaining
  // -------------------------------------------------------------------
  function chainIndex(rate, annualize, ppy, base) {
    const n = rate.length, out = new Float64Array(n).fill(NaN);
    let level = null;
    for (let i = 0; i < n; i++) {
      const per = deannualise(rate[i], annualize, ppy);
      if (level === null) {
        if (!Number.isFinite(per)) continue;
        level = base;                       // first usable period anchors it
        out[i] = level;
        continue;
      }
      if (Number.isFinite(per)) level = level * (1 + per / 100);
      out[i] = level;
    }
    return out;
  }

  function horizonRate(index, horizon, ppy) {
    const n = index.length, out = new Float64Array(n).fill(NaN);
    for (let i = horizon; i < n; i++) {
      const a = index[i - horizon], b = index[i];
      if (Number.isFinite(a) && Number.isFinite(b) && a > 0)
        out[i] = 100 * (Math.pow(b / a, ppy / horizon) - 1);
    }
    return out;
  }

  // -------------------------------------------------------------------
  // Top level
  // -------------------------------------------------------------------
  /* opts: { lower, upper, sa, saWindow, annualize, ppy, weightLag,
             minCategories, excluded:Set|Array, horizons:[1,3,6,12],
             weightVintage: "versioned" | "latest" | "first" }
     cache (optional): { get(key), set(key, value) } for the SA panel, which is
     the only part that does not depend on the trim fractions. */
  function compute(panel, opts, cache) {
    const o = Object.assign({
      lower: 0.08, upper: 0.08, sa: "rolling", saWindow: 120,
      annualize: "compound", ppy: 12, weightLag: 0, minCategories: 10,
      excluded: null, horizons: [1, 3, 6, 12], weightVintage: "versioned",
      cacheTag: "",
    }, opts || {});
    const { n, k } = panel;

    const saKey = `${o.cacheTag}|${o.sa}|${o.saWindow}|${o.annualize}|${o.ppy}`;
    let values = cache && cache.get ? cache.get(saKey) : null;
    if (!values) {
      values = seasonallyAdjustedAnnual(panel, o);
      if (cache && cache.set) cache.set(saKey, values);
    }

    const excluded = o.excluded instanceof Set ? o.excluded
                   : new Set(o.excluded || []);
    const weights = weightVintage(panel, o.weightVintage, o.weightLag);

    const rate = new Float64Array(n).fill(NaN);
    const counts = new Int32Array(n);
    const idx = new Int32Array(k), wnorm = new Float64Array(k);
    const vrow = new Float64Array(k);
    const member = new Int8Array(k);
    const keptW = new Float64Array(k);
    let lastMembership = null, lastKept = null, lastRow = -1;

    for (let i = 0; i < n; i++) {
      let m = 0, tot = 0;
      for (let j = 0; j < k; j++) {
        if (excluded.has(j)) continue;
        const v = values[j][i], wv = weights[j][i];
        if (!Number.isFinite(v) || !Number.isFinite(wv) || wv <= 0) continue;
        idx[m] = j; vrow[j] = v; tot += wv; m++;
      }
      counts[i] = m;
      if (m < o.minCategories || tot <= 0) continue;

      // stable sort by value: ties keep panel order, matching numpy mergesort
      const slice = Array.prototype.slice.call(idx.subarray(0, m));
      slice.sort((a, b) => (vrow[a] - vrow[b]) || (a - b));
      for (let t = 0; t < m; t++) { idx[t] = slice[t]; wnorm[t] = weights[slice[t]][i] / tot; }

      rate[i] = trimOne(vrow, weights, idx, m, o.lower, o.upper, wnorm);
      if (Number.isFinite(rate[i])) {
        membershipOne(idx, m, o.lower, o.upper, wnorm, member, k, keptW);
        lastMembership = Array.from(member);
        lastKept = Array.from(keptW);
        lastRow = i;
      }
    }

    const index = chainIndex(rate, o.annualize, o.ppy, 100);
    const out = {
      rate: toNullable(rate), index: toNullable(index),
      n: Array.from(counts), horizons: {},
      latest: lastRow < 0 ? null : {
        row: lastRow,
        membership: lastMembership,
        retained: lastKept,
        values: Array.from({ length: k }, (_, j) =>
          Number.isFinite(values[j][lastRow]) ? values[j][lastRow] : null),
        weights: Array.from({ length: k }, (_, j) =>
          Number.isFinite(weights[j][lastRow]) ? weights[j][lastRow] : null),
      },
    };
    // the year-over-year horizon is ppy periods, whatever the frequency — make
    // sure it is always computed even if the caller's horizon list omits it
    const horizons = new Set([...(o.horizons || []), o.ppy]);
    for (const h of horizons) out.horizons[h] = toNullable(horizonRate(index, h, o.ppy));
    out.yoy = out.horizons[o.ppy];
    return out;
  }

  /* Weight vintage: the shipped panel is the real month-by-month weight path;
     "latest" and "first" freeze one row and broadcast it, which is how you see
     what a static weight vector does to the history. */
  function weightVintage(panel, vintage, lag) {
    const { w, n, k } = panel;
    if (vintage === "versioned" && !lag) return w;

    const out = new Array(k);
    if (vintage === "latest" || vintage === "first") {
      let row = -1;
      const ok = i => {
        let s = 0;
        for (let j = 0; j < k; j++) if (Number.isFinite(w[j][i])) s += w[j][i];
        return s > 0;
      };
      if (vintage === "latest") { for (let i = n - 1; i >= 0 && row < 0; i--) if (ok(i)) row = i; }
      else { for (let i = 0; i < n && row < 0; i++) if (ok(i)) row = i; }
      for (let j = 0; j < k; j++) out[j] = new Float64Array(n).fill(row < 0 ? NaN : w[j][row]);
      return out;
    }
    for (let j = 0; j < k; j++) {
      const col = new Float64Array(n).fill(NaN);
      for (let i = lag; i < n; i++) col[i] = w[j][i - lag];
      out[j] = col;
    }
    return out;
  }

  function toNullable(a) {
    const out = new Array(a.length);
    for (let i = 0; i < a.length; i++) out[i] = Number.isFinite(a[i]) ? a[i] : null;
    return out;
  }

  return { toPanel, compute, seasonalFactors, seasonallyAdjustedAnnual,
           chainIndex, horizonRate, trimOne, membershipOne, deannualise };
})();

if (typeof module !== "undefined" && module.exports) module.exports = TrimEngine;
