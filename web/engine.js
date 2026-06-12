/* ISM engine — JavaScript port of the maths in src/ism/engine.py (Eqs. 3-8)
   plus the weighting schemes of scripts/export_web_data.py (size / stickiness).

   This file is the browser twin of the Python engine. It must stay in sync
   with the Python code; the contract is enforced by tests/test_web_engine_parity.py,
   which runs both implementations on the same synthetic panel and asserts the
   outputs match.

   Design notes
   ------------
   * rollingAR() solves each window's OLS via normal equations assembled from
     prefix sums of lagged cross-products, so a full pass over a category is
     O(n·(p + p³)) instead of O(n·W·p²). That is what makes a live window-length
     slider feasible in the browser.
   * Windows containing any non-finite value are skipped (residual = NaN),
     exactly like the Python engine (it requires a fully clean window).
   * Works in three runtimes: Web Worker (importScripts), <script>, and Node
     (module.exports) — Node is used by the parity test. No dependencies. */
"use strict";

const ISMEngine = (() => {

  // ---------------------------------------------------------------------
  // Linear algebra. The Python engine solves each window with
  // numpy.linalg.lstsq, which returns the MINIMUM-NORM solution when the
  // design is rank-deficient (e.g. a category whose price index is flat for
  // the whole window -> inflation identically 0 -> X'X singular, residual 0).
  // We mirror that: fast Gaussian elimination in the regular case, and a
  // pseudo-inverse fallback (Jacobi eigendecomposition of the symmetric
  // normal matrix) when the elimination hits a ~zero pivot.
  // ---------------------------------------------------------------------
  function solveSym(A, b, dim) {
    const A2 = Float64Array.from(A), b2 = Float64Array.from(b);
    return solveInPlace(A2, b2, dim) || pinvSolve(A, b, dim);
  }

  // Gaussian elimination with partial pivoting. Mutates A and b. Returns x
  // or null if the system is (numerically) singular.
  function solveInPlace(A, b, dim) {
    for (let col = 0; col < dim; col++) {
      // pivot
      let piv = col, best = Math.abs(A[col * dim + col]);
      for (let r = col + 1; r < dim; r++) {
        const v = Math.abs(A[r * dim + col]);
        if (v > best) { best = v; piv = r; }
      }
      if (!(best > 1e-12)) return null;
      if (piv !== col) {
        for (let j = col; j < dim; j++) {
          const t = A[col * dim + j]; A[col * dim + j] = A[piv * dim + j]; A[piv * dim + j] = t;
        }
        const t = b[col]; b[col] = b[piv]; b[piv] = t;
      }
      // eliminate below
      const d = A[col * dim + col];
      for (let r = col + 1; r < dim; r++) {
        const f = A[r * dim + col] / d;
        if (f === 0) continue;
        for (let j = col; j < dim; j++) A[r * dim + j] -= f * A[col * dim + j];
        b[r] -= f * b[col];
      }
    }
    // back substitution
    const x = new Float64Array(dim);
    for (let r = dim - 1; r >= 0; r--) {
      let s = b[r];
      for (let j = r + 1; j < dim; j++) s -= A[r * dim + j] * x[j];
      x[r] = s / A[r * dim + r];
    }
    return x;
  }

  // Minimum-norm solve of the (symmetric PSD) normal equations A x = b via
  // eigendecomposition: x = V diag(1/λ_i for λ_i > cut) V' b. Equivalent to
  // numpy.lstsq's pinv behaviour on the rank-deficient windows we hit in
  // practice (constant series). Cyclic Jacobi; dim ≤ 13, so cost is trivial.
  function pinvSolve(A, b, dim) {
    const M = Float64Array.from(A);
    const V = new Float64Array(dim * dim);
    for (let i = 0; i < dim; i++) V[i * dim + i] = 1;

    for (let sweep = 0; sweep < 60; sweep++) {
      let off = 0;
      for (let p = 0; p < dim - 1; p++)
        for (let q = p + 1; q < dim; q++) off += M[p * dim + q] * M[p * dim + q];
      if (off < 1e-30) break;
      for (let p = 0; p < dim - 1; p++) {
        for (let q = p + 1; q < dim; q++) {
          const apq = M[p * dim + q];
          if (apq === 0) continue;
          const tau = (M[q * dim + q] - M[p * dim + p]) / (2 * apq);
          const t = (tau >= 0 ? 1 : -1) / (Math.abs(tau) + Math.sqrt(1 + tau * tau));
          const c = 1 / Math.sqrt(1 + t * t), s = t * c;
          for (let i = 0; i < dim; i++) {           // M <- M J (columns p,q)
            const mip = M[i * dim + p], miq = M[i * dim + q];
            M[i * dim + p] = c * mip - s * miq;
            M[i * dim + q] = s * mip + c * miq;
          }
          for (let i = 0; i < dim; i++) {           // M <- J' M (rows p,q)
            const mpi = M[p * dim + i], mqi = M[q * dim + i];
            M[p * dim + i] = c * mpi - s * mqi;
            M[q * dim + i] = s * mpi + c * mqi;
          }
          for (let i = 0; i < dim; i++) {           // accumulate V <- V J
            const vip = V[i * dim + p], viq = V[i * dim + q];
            V[i * dim + p] = c * vip - s * viq;
            V[i * dim + q] = s * vip + c * viq;
          }
        }
      }
    }

    let lmax = 0;
    for (let j = 0; j < dim; j++) lmax = Math.max(lmax, M[j * dim + j]);
    const x = new Float64Array(dim);
    if (!(lmax > 0)) return x;                      // A == 0 -> min-norm x = 0
    const cut = lmax * dim * 1e-13;                 // rank tolerance
    for (let j = 0; j < dim; j++) {
      const lam = M[j * dim + j];
      if (!(lam > cut)) continue;
      let vb = 0;
      for (let i = 0; i < dim; i++) vb += V[i * dim + j] * b[i];
      const f = vb / lam;
      for (let i = 0; i < dim; i++) x[i] += f * V[i * dim + j];
    }
    return x;
  }

  // ---------------------------------------------------------------------
  // Eq. (3): rolling AR(p) residuals for one category.
  //
  // y : Float64Array of monthly inflation (NaN = missing), length n.
  // p : AR order.  W : window length in months (min_obs = W, like the export).
  //
  // Returns { resid, slope } where resid[t] is the regression residual at the
  // window END date (NaN where no clean window) and slope[t] is the first-lag
  // coefficient (= rho-hat when p === 1, used by the stickiness scheme).
  //
  // The per-window normal equations are assembled in O(p²) from prefix sums:
  //   s1[u]    = Σ_{s<u} y[s]
  //   sd[d][u] = Σ_{s<u} y[s]·y[s+d]          (lag-d cross-products)
  // For regression rows t = a..end (a = start+p, m = W-p rows):
  //   (X'X)[0][0] = m
  //   (X'X)[0][j] = Σ_t y[t-j]          = s1[end-j+1]   - s1[a-j]
  //   (X'X)[i][j] = Σ_t y[t-i]·y[t-j]   = sd[i-j][end-i+1] - sd[i-j][a-i]  (i≥j≥1)
  //   (X'y)[0]    = Σ_t y[t]            = s1[end+1]     - s1[a]
  //   (X'y)[j]    = Σ_t y[t-j]·y[t]     = sd[j][end-j+1]   - sd[j][a-j]
  // NaNs are written as 0 into the prefix sums; that is safe because windows
  // containing any NaN are detected via the finite-count prefix and skipped.
  // ---------------------------------------------------------------------
  function rollingAR(y, p, W) {
    const n = y.length;
    const resid = new Float64Array(n).fill(NaN);
    const slope = new Float64Array(n).fill(NaN);
    const m = W - p;                       // regression rows per window
    if (W > n || m < p + 1) return { resid, slope };

    const cnt = new Int32Array(n + 1);
    const s1 = new Float64Array(n + 1);
    const sd = [];
    for (let d = 0; d <= p; d++) sd.push(new Float64Array(n + 1));
    for (let s = 0; s < n; s++) {
      const v = y[s], f = Number.isFinite(v);
      cnt[s + 1] = cnt[s] + (f ? 1 : 0);
      s1[s + 1] = s1[s] + (f ? v : 0);
      for (let d = 0; d <= p; d++) {
        const w = s + d < n ? y[s + d] : NaN;
        sd[d][s + 1] = sd[d][s] + (f && Number.isFinite(w) ? v * w : 0);
      }
    }

    const dim = p + 1;
    const A = new Float64Array(dim * dim);
    const b = new Float64Array(dim);

    for (let end = W - 1; end < n; end++) {
      const start = end - W + 1;
      if (cnt[end + 1] - cnt[start] !== W) continue;     // window not fully clean
      const a = start + p;                               // first regression row

      A[0] = m;
      b[0] = s1[end + 1] - s1[a];
      for (let j = 1; j <= p; j++) {
        const sj = s1[end - j + 1] - s1[a - j];
        A[j] = sj; A[j * dim] = sj;
        b[j] = sd[j][end - j + 1] - sd[j][a - j];
        for (let i = j; i <= p; i++) {
          const v = sd[i - j][end - i + 1] - sd[i - j][a - i];
          A[i * dim + j] = v; A[j * dim + i] = v;
        }
      }

      const beta = solveSym(A, b, dim);
      let fit = beta[0];
      for (let j = 1; j <= p; j++) fit += beta[j] * y[end - j];
      resid[end] = y[end] - fit;
      slope[end] = beta[1];
    }
    return { resid, slope };
  }

  // ---------------------------------------------------------------------
  // Eqs. (4)-(5): momentum indicators — K consecutive same-signed residuals.
  // NaN residuals break a run (Python: NaN > 0 is False -> indicator 0).
  // ---------------------------------------------------------------------
  function momentum(resid, K) {
    const n = resid.length;
    const mp = new Uint8Array(n), mn = new Uint8Array(n);
    let runP = 0, runN = 0;
    for (let t = 0; t < n; t++) {
      const r = resid[t];
      runP = Number.isFinite(r) && r > 0 ? runP + 1 : 0;
      runN = Number.isFinite(r) && r < 0 ? runN + 1 : 0;
      if (runP >= K) mp[t] = 1;
      if (runN >= K) mn[t] = 1;
    }
    return { mp, mn };
  }

  // ---------------------------------------------------------------------
  // Full computation: Eqs. (3)-(8) + weighting scheme + driver decomposition.
  //
  // panel : { infl: Float64Array[ncat], w: Float64Array[ncat], n }
  //         (per-category series of equal length n; NaN = missing)
  // params: { ar, W, k, scheme, rhoCap, excluded, cacheTag, driverMonths }
  //         scheme ∈ {"extensive","size","stickiness"}; excluded = iterable of
  //         category indices to drop (weights renormalise over the rest).
  // cache : optional Map; residual / rho panels are cached under keys derived
  //         from (cacheTag, ar, W) so parameter changes that do not alter the
  //         regressions (k, scheme, weights, exclusions) recompute instantly.
  //
  // Returns { ISM, S_pos, S_neg, drivers } where the series are plain arrays
  // (null where no category has a valid weight+residual that month) and
  // drivers = [{ t, contrib: [[catIdx, value], ...] }] for the last
  // `driverMonths` valid months (newest last), contrib sorted by |value| desc,
  // values = w̃_i·(M+_i − M−_i), which sum exactly to ISM_t.
  // ---------------------------------------------------------------------
  const DRIVER_MIN = 1e-6;

  function compute(panel, params, cache) {
    const { infl, w, n } = panel;
    const ncat = infl.length;
    const { ar, W, k } = params;
    const scheme = params.scheme || "extensive";
    const rhoCap = params.rhoCap == null ? 0.9 : params.rhoCap;
    const driverMonths = params.driverMonths == null ? 22 : params.driverMonths;
    const excluded = new Set(params.excluded || []);
    const tag = params.cacheTag || "";

    // Eq. (3) — cached: depends only on (panel, ar, W).
    const rkey = `R|${tag}|${ar}|${W}`;
    let R = cache ? cache.get(rkey) : null;
    if (!R) {
      R = infl.map(y => rollingAR(y, ar, W));
      if (cache) cache.set(rkey, R);
    }

    // rho-hat for the stickiness scheme is ALWAYS the AR(1) slope over the
    // same window (mirrors appendix.rho_panel / rolling_rho in Python).
    let rho = null;
    if (scheme === "stickiness") {
      if (ar === 1) {
        rho = R.map(o => o.slope);
      } else {
        const key = `rho|${tag}|${W}`;
        rho = cache ? cache.get(key) : null;
        if (!rho) {
          rho = infl.map(y => rollingAR(y, 1, W).slope);
          if (cache) cache.set(key, rho);
        }
      }
    }

    // Eqs. (4)-(5) + scheme strength. Mp/Mn hold w-independent magnitudes:
    //   extensive : 1
    //   size      : |Σ of the last k residuals|
    //   stickiness: 1 / (1 − min(ρ̂, cap))
    const Mp = [], Mn = [];
    for (let c = 0; c < ncat; c++) {
      const resid = R[c].resid;
      const { mp, mn } = momentum(resid, k);
      const sp = new Float64Array(n), sn = new Float64Array(n);
      for (let t = 0; t < n; t++) {
        if (!mp[t] && !mn[t]) continue;
        let s = 1;
        if (scheme === "size") {
          let acc = 0;
          for (let j = 0; j < k; j++) acc += resid[t - j];
          s = Math.abs(acc);
        } else if (scheme === "stickiness") {
          s = 1 / (1 - Math.min(rho[c][t], rhoCap));
        }
        if (!Number.isFinite(s)) s = 0;     // mirrors Python's .fillna(0)
        if (mp[t]) sp[t] = s; else sn[t] = s;
      }
      Mp.push(sp); Mn.push(sn);
    }

    // Eqs. (6)-(8): per-month renormalised weights over the categories that
    // are valid this month (finite inflation, weight AND residual; not excluded).
    const ISM = new Array(n).fill(null);
    const S_pos = new Array(n).fill(null);
    const S_neg = new Array(n).fill(null);
    const validMonths = [];

    const valid = (c, t) =>
      !excluded.has(c) &&
      Number.isFinite(infl[c][t]) && Number.isFinite(w[c][t]) &&
      Number.isFinite(R[c].resid[t]);

    for (let t = 0; t < n; t++) {
      let wsum = 0;
      for (let c = 0; c < ncat; c++) if (valid(c, t)) wsum += w[c][t];
      if (!(wsum > 0)) continue;
      let sp = 0, sn = 0;
      for (let c = 0; c < ncat; c++) {
        if (!valid(c, t)) continue;
        const wn = w[c][t] / wsum;
        sp += wn * Mp[c][t];
        sn += wn * Mn[c][t];
      }
      S_pos[t] = sp; S_neg[t] = sn; ISM[t] = sp - sn;
      validMonths.push(t);
    }

    // Driver decomposition for the most recent valid months.
    const drivers = [];
    const tail = validMonths.slice(-driverMonths);
    for (const t of tail) {
      let wsum = 0;
      for (let c = 0; c < ncat; c++) if (valid(c, t)) wsum += w[c][t];
      const contrib = [];
      for (let c = 0; c < ncat; c++) {
        if (!valid(c, t)) continue;
        const v = (w[c][t] / wsum) * (Mp[c][t] - Mn[c][t]);
        if (Math.abs(v) > DRIVER_MIN) contrib.push([c, Math.round(v * 1e5) / 1e5]);
      }
      contrib.sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]));
      drivers.push({ t, contrib });
    }

    return { ISM, S_pos, S_neg, drivers };
  }

  // Convert JSON columns (numbers + nulls) into the typed panel `compute` wants.
  function toPanel(inflation, weights) {
    const conv = col => Float64Array.from(col, v => (v == null ? NaN : v));
    return { infl: inflation.map(conv), w: weights.map(conv), n: inflation[0].length };
  }

  return { rollingAR, momentum, compute, toPanel, DRIVER_MIN };
})();

/* eslint-disable no-undef */
if (typeof module !== "undefined" && module.exports) module.exports = ISMEngine;
