/* Supply/demand decomposition engine — JavaScript port of the maths in
   src/ism/decomp_engine.py (Shapiro 2022-18, Eqs. 8-15).

   Browser twin of the Python engine; kept in sync via tests/test_decomp_parity.py,
   which runs both on the same synthetic panel and asserts the outputs match.

   Per category we estimate a rolling reduced-form VAR of log price and log
   quantity on J lags of both (Eqs. 12-13), collect the one-step residuals at the
   window end, sign-classify the category-month (Eqs. 8-11), then aggregate into
   supply/demand-driven CONTRIBUTIONS to inflation (Eq. 15, Laspeyres weights)
   and expenditure SHARES (Eq. 14).

   Runtimes: Web Worker (importScripts), <script>, and Node (module.exports). */
"use strict";

const DecompEngine = (() => {

  // ---- linear algebra: solve symmetric system, min-norm fallback ----------
  // (mirrors web/engine.js: Gaussian elimination, then a Jacobi pseudo-inverse
  // when the normal matrix is singular — e.g. a constant series in a window.)
  function solveSym(A, b, dim) {
    const A2 = Float64Array.from(A), b2 = Float64Array.from(b);
    return solveInPlace(A2, b2, dim) || pinvSolve(A, b, dim);
  }
  function solveInPlace(A, b, dim) {
    for (let col = 0; col < dim; col++) {
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
      const d = A[col * dim + col];
      for (let r = col + 1; r < dim; r++) {
        const f = A[r * dim + col] / d;
        if (f === 0) continue;
        for (let j = col; j < dim; j++) A[r * dim + j] -= f * A[col * dim + j];
        b[r] -= f * b[col];
      }
    }
    const x = new Float64Array(dim);
    for (let r = dim - 1; r >= 0; r--) {
      let s = b[r];
      for (let j = r + 1; j < dim; j++) s -= A[r * dim + j] * x[j];
      x[r] = s / A[r * dim + r];
    }
    return x;
  }
  function pinvSolve(A, b, dim) {
    const M = Float64Array.from(A);
    const V = new Float64Array(dim * dim);
    for (let i = 0; i < dim; i++) V[i * dim + i] = 1;
    for (let sweep = 0; sweep < 80; sweep++) {
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
          for (let i = 0; i < dim; i++) {
            const mip = M[i * dim + p], miq = M[i * dim + q];
            M[i * dim + p] = c * mip - s * miq;
            M[i * dim + q] = s * mip + c * miq;
          }
          for (let i = 0; i < dim; i++) {
            const mpi = M[p * dim + i], mqi = M[q * dim + i];
            M[p * dim + i] = c * mpi - s * mqi;
            M[q * dim + i] = s * mpi + c * mqi;
          }
          for (let i = 0; i < dim; i++) {
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
    if (!(lmax > 0)) return x;
    const cut = lmax * dim * 1e-13;
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

  // ---- Eqs. (12)-(13): rolling VAR residuals for one category -------------
  // p, q : Float64Array log price / log quantity (NaN = missing), length n.
  // Returns { rp, rq } residual arrays (NaN where no clean window), where the
  // residual at month `end` is the in-sample residual of the window's last row.
  function rollingVAR(p, q, J, W, h) {
    const n = p.length;
    const rp = new Float64Array(n).fill(NaN);
    const rq = new Float64Array(n).fill(NaN);
    const dim = 1 + 2 * J;                 // [const, p_{t-1..t-J}, q_{t-1..t-J}]
    const rows = W - J - h;                // regression rows per window
    if (W > n || rows < dim + 1) return { rp, rq };

    const A = new Float64Array(dim * dim);
    const b1 = new Float64Array(dim);      // X'Yp
    const b2 = new Float64Array(dim);      // X'Yq
    const xrow = new Float64Array(dim);

    for (let end = W - 1; end < n; end++) {
      const start = end - W + 1;
      // window must be fully finite (matches the Python engine)
      let ok = true;
      for (let t = start; t <= end; t++) {
        if (!Number.isFinite(p[t]) || !Number.isFinite(q[t])) { ok = false; break; }
      }
      if (!ok) continue;

      A.fill(0); b1.fill(0); b2.fill(0);
      // regression rows: local index r = J+h .. W-1 (absolute t = start + r)
      let lastXrow = null, lastYp = 0, lastYq = 0;
      for (let r = J + h; r < W; r++) {
        const t = start + r;
        // build the regressor row
        xrow[0] = 1;
        for (let lag = 1; lag <= J; lag++) {
          xrow[lag] = p[t - lag - h];
          xrow[J + lag] = q[t - lag - h];
        }
        let yp, yq;
        if (h === 0) { yp = p[t]; yq = q[t]; }
        else { yp = p[t] - p[t - h - 1]; yq = q[t] - q[t - h - 1]; }
        // accumulate normal equations
        for (let i = 0; i < dim; i++) {
          const xi = xrow[i];
          b1[i] += xi * yp;
          b2[i] += xi * yq;
          const base = i * dim;
          for (let j = i; j < dim; j++) A[base + j] += xi * xrow[j];
        }
        if (r === W - 1) { lastXrow = Float64Array.from(xrow); lastYp = yp; lastYq = yq; }
      }
      // symmetrise
      for (let i = 0; i < dim; i++)
        for (let j = i + 1; j < dim; j++) A[j * dim + i] = A[i * dim + j];

      const betaP = solveSym(A, b1, dim);
      const betaQ = solveSym(A, b2, dim);
      let fp = 0, fq = 0;
      for (let i = 0; i < dim; i++) { fp += lastXrow[i] * betaP[i]; fq += lastXrow[i] * betaQ[i]; }
      rp[end] = lastYp - fp;
      rq[end] = lastYq - fq;
    }
    return { rp, rq };
  }

  // ---- precision: per-category trailing rolling SD of a residual series ----
  // ppy = periods per year (12 monthly, 4 quarterly); min-periods floor is one
  // year of observations or window/4, whichever is larger (mirrors Python).
  function rollingSD(resid, window, ppy) {
    const n = resid.length;
    const out = new Float64Array(n).fill(NaN);
    const P = ppy || 12;
    const mp = Math.min(window, Math.max(P, Math.floor(window / 4)));
    for (let t = 0; t < n; t++) {
      let cnt = 0, sum = 0, sum2 = 0;
      for (let s = Math.max(0, t - window + 1); s <= t; s++) {
        const v = resid[s];
        if (Number.isFinite(v)) { cnt++; sum += v; sum2 += v * v; }
      }
      if (cnt >= mp && cnt > 1) {
        const mean = sum / cnt;
        // pandas std default ddof=1 (sample)
        out[t] = Math.sqrt(Math.max(0, (sum2 - cnt * mean * mean) / (cnt - 1)));
      }
    }
    return out;
  }

  // ---- Full computation: Eqs. (8)-(15) ------------------------------------
  // panel  : { logp, logq, infl, w, n }  (per-category Float64Array, length n)
  // params : { J, W, h, precisionCut, excluded, cacheTag, driverMonths }
  // cache  : optional Map; residual panels cached under (cacheTag, J, W, h).
  //
  // Returns { supply, demand, ambiguous, total,            (monthly, pp)
  //           supply_yoy, demand_yoy, ambiguous_yoy, total_yoy,
  //           sh_supply, sh_demand, sh_ambiguous,          (Eq. 14 shares)
  //           drivers }  (last driverMonths months; supply +, demand -)
  const DRIVER_MIN = 1e-6;

  function compute(panel, params, cache) {
    const { logp, logq, infl, w, n } = panel;
    const ncat = logp.length;
    const J = params.J, W = params.W, h = params.h || 0;
    const PPY = params.ppy || 12;          // periods per year (12 monthly, 4 quarterly)
    const cut = params.precisionCut || 0;
    const driverMonths = params.driverMonths == null ? 22 : params.driverMonths;
    const excluded = new Set(params.excluded || []);
    const tag = params.cacheTag || "";

    // Eqs. (12)-(13) — cached on (panel, J, W, h)
    const rkey = `R|${tag}|${J}|${W}|${h}`;
    let R = cache ? cache.get(rkey) : null;
    if (!R) {
      R = logp.map((lp, c) => rollingVAR(lp, logq[c], J, W, h));
      if (cache) cache.set(rkey, R);
    }

    // Eqs. (8)-(11) labels + Eq. (15) contributions + Eq. (14) shares
    const supply = new Array(n).fill(null);
    const demand = new Array(n).fill(null);
    const ambiguous = new Array(n).fill(null);
    const total = new Array(n).fill(null);
    const shS = new Array(n).fill(null);
    const shD = new Array(n).fill(null);
    const shA = new Array(n).fill(null);

    // optional per-category residual SDs for precision labeling
    let sdP = null, sdQ = null;
    if (cut > 0) {
      const skey = `SD|${tag}|${J}|${W}|${h}|${PPY}`;
      let sd = cache ? cache.get(skey) : null;
      if (!sd) {
        sd = R.map(o => ({ p: rollingSD(o.rp, W, PPY), q: rollingSD(o.rq, W, PPY) }));
        if (cache) cache.set(skey, sd);
      }
      sdP = sd.map(o => o.p); sdQ = sd.map(o => o.q);
    }

    const driverRows = [];
    for (let t = 0; t < n; t++) {
      let wsumS = 0;        // Σ contemporaneous weight over labelled cats (shares)
      let cS = 0, cD = 0, cA = 0, cT = 0;   // contributions (Laspeyres)
      let shCatW = 0, shS_ = 0, shD_ = 0, shA_ = 0;
      let any = false;
      const contribByCat = [];
      for (let c = 0; c < ncat; c++) {
        if (excluded.has(c)) continue;
        const rp = R[c].rp[t], rq = R[c].rq[t];
        if (!Number.isFinite(rp) || !Number.isFinite(rq)) continue;
        any = true;
        // label
        let isAmb = false;
        if (cut > 0) {
          if (Math.abs(rp) < cut * sdP[c][t] || Math.abs(rq) < cut * sdQ[c][t]) isAmb = true;
        }
        let isSup = false, isDem = false;
        if (!isAmb) {
          if ((rp < 0 && rq > 0) || (rp > 0 && rq < 0)) isSup = true;
          else if ((rp > 0 && rq > 0) || (rp < 0 && rq < 0)) isDem = true;
        }
        // shares (Eq. 14): contemporaneous weight
        const wc = w[c][t];
        if (Number.isFinite(wc)) {
          shCatW += wc;
          if (isSup) shS_ += wc; else if (isDem) shD_ += wc; else if (isAmb) shA_ += wc;
        }
        // contributions (Eq. 15): lagged weight × inflation
        const wl = t > 0 ? w[c][t - 1] : NaN;
        const pi = infl[c][t];
        if (Number.isFinite(wl) && Number.isFinite(pi)) {
          const contrib = wl * pi;
          cT += contrib;
          if (isSup) { cS += contrib; contribByCat.push([c, contrib]); }
          else if (isDem) { cD += contrib; contribByCat.push([c, -contrib]); }
          else if (isAmb) cA += contrib;
        }
      }
      if (!any) continue;
      supply[t] = cS; demand[t] = cD; ambiguous[t] = cA; total[t] = cT;
      if (shCatW > 0) {
        shS[t] = shS_ / shCatW; shD[t] = shD_ / shCatW; shA[t] = shA_ / shCatW;
      }
      driverRows.push({ t, contrib: contribByCat });
    }

    // year-over-year running product of the last PPY per-period contributions
    const yoy = arr => {
      const out = new Array(n).fill(null);
      for (let t = PPY - 1; t < n; t++) {
        let prod = 1, ok = true;
        for (let k = 0; k < PPY; k++) {
          const v = arr[t - k];
          if (v == null) { ok = false; break; }
          prod *= (1 + v / 100);
        }
        out[t] = ok ? 100 * (prod - 1) : null;
      }
      return out;
    };

    // drivers: last driverMonths months with a defined total, newest last
    const valid = driverRows.filter(d => total[d.t] != null);
    const drivers = valid.slice(-driverMonths).map(d => {
      const contrib = d.contrib
        .filter(p => Math.abs(p[1]) > DRIVER_MIN)
        .map(p => [p[0], Math.round(p[1] * 1e5) / 1e5]);
      contrib.sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]));
      return { t: d.t, contrib };
    });

    return {
      supply, demand, ambiguous, total,
      supply_yoy: yoy(supply), demand_yoy: yoy(demand),
      ambiguous_yoy: yoy(ambiguous), total_yoy: yoy(total),
      sh_supply: shS, sh_demand: shD, sh_ambiguous: shA,
      drivers,
    };
  }

  // Convert JSON columns (numbers + nulls) to the typed panel `compute` wants.
  // `infl` is optional: when omitted it is derived from logp as the MoM % change
  // of the price index P = exp(logp), i.e. 100·(P_t/P_{t-1} − 1) — identical to
  // the Python pipeline's monthly_inflation(price, "pct"), so the web payload
  // need only ship logp, logq and w.
  function toPanel(logp, logq, infl, w) {
    const conv = col => Float64Array.from(col, v => (v == null ? NaN : v));
    const LP = logp.map(conv), LQ = logq.map(conv), W = w.map(conv);
    let IN;
    if (infl) {
      IN = infl.map(conv);
    } else {
      IN = LP.map(col => {
        const out = new Float64Array(col.length).fill(NaN);
        for (let t = 1; t < col.length; t++) {
          if (Number.isFinite(col[t]) && Number.isFinite(col[t - 1]))
            out[t] = 100 * (Math.exp(col[t] - col[t - 1]) - 1);
        }
        return out;
      });
    }
    return { logp: LP, logq: LQ, infl: IN, w: W, n: LP[0].length };
  }

  return { rollingVAR, rollingSD, compute, toPanel, DRIVER_MIN };
})();

/* eslint-disable no-undef */
if (typeof module !== "undefined" && module.exports) module.exports = DecompEngine;
