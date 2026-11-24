/* wage_engine.js -- browser twin of src/ism/wage_engine.py.

   The wage page recomputes the model in the visitor's browser rather than
   plotting stored results, for the same reason the other four models do: a
   parameter you can move is worth more than a chart you can only look at, and
   a reader who can refit the equation can check it.

   Every function here mirrors one in the Python module and carries the same
   equation number. `tests/test_wage_parity.py` drives both with identical
   inputs and requires agreement to 1e-9, so any change made here must be made
   there, and vice versa. Two consequences shape the code:

     * No linear-algebra library. `inv` is Gauss-Jordan with partial pivoting,
       written to match `_inv` in the Python step for step -- including the
       ridge and the pivot rule -- because numpy's SVD-based pinv has no
       reproducible counterpart here.
     * No clever short-cuts. Where the Python loops, this loops, in the same
       order, so floating-point association matches.

   Everything is plain arrays of numbers with `null` for missing, which is what
   the JSON payload carries. */
"use strict";

const WageEngine = (() => {
  const PPY = 4;                       // quarterly throughout

  const DEFAULT_ELASTICITIES = {
    automatic: 0.90,   // Card (1986): marginal escalator elasticity 0.75-0.95
    public: 1.00,      // statutory indexation of public pay is mechanical
    minwage: 0.35,     // Cengiz et al. (2019): spillovers ~40% of the gain
    benchmark: 0.30,   // ECB OP 299: 0.3-0.5pp private response per 1pp public
  };

  const DEFAULT_CONFIG = {
    lags: 4,
    anchorQ: 0.05,
    homogeneity: true,
    horizon: 3 * PPY,
    elasticities: { ...DEFAULT_ELASTICITIES },
  };

  const isNum = v => v !== null && v !== undefined && Number.isFinite(v);

  /* ---------------------------------------------------------------- Eq. W1 */
  /* Steady-state Kalman gain of a random-walk-plus-noise model:
     k^2 + q k - q = 0  =>  k = (sqrt(q^2 + 4q) - q) / 2.
     q = 0 is a perfectly anchored trend; q -> infinity is last quarter's
     inflation. This is the page's "anchoring" slider. */
  function kalmanGain(q) {
    if (!(q > 0)) return 0;
    return (Math.sqrt(q * q + 4 * q) - q) / 2;
  }

  function trendInflation(pi, q, init) {
    const k = kalmanGain(q);
    const out = new Array(pi.length);
    let level = init;
    if (!isNum(level)) {
      let s = 0, n = 0;
      for (let i = 0; i < Math.min(PPY, pi.length); i++)
        if (isNum(pi[i])) { s += pi[i]; n++; }
      level = n ? s / n : 0;
    }
    for (let i = 0; i < pi.length; i++) {
      if (isNum(pi[i])) level = level + k * (pi[i] - level);
      out[i] = level;
    }
    return out;
  }

  /* ---------------------------------------------------------------- Eq. W2 */
  /* Deviation from a one-sided local linear trend: fit a + b*t on the `window`
     observations ending at t-1, project one period forward, subtract. Nothing
     after t enters, which is what makes it computable here. */
  function rollingTrendGap(x, window, minPeriods) {
    window = window || 40;
    minPeriods = minPeriods || 20;
    const n = x.length, out = new Array(n).fill(null);
    for (let t = 0; t < n; t++) {
      if (!isNum(x[t])) continue;
      const lo = Math.max(0, t - window);
      let cnt = 0, sx = 0, sy = 0;
      for (let i = lo; i < t; i++) if (isNum(x[i])) { cnt++; sx += i; sy += x[i]; }
      if (cnt < minPeriods) continue;
      const xm = sx / cnt, ym = sy / cnt;
      let num = 0, den = 0;
      for (let i = lo; i < t; i++) {
        if (!isNum(x[i])) continue;
        num += (i - xm) * (x[i] - ym);
        den += (i - xm) * (i - xm);
      }
      if (!(den > 0)) continue;
      const b = num / den, a = ym - b * xm;
      out[t] = x[t] - (a + b * t);
    }
    return out;
  }

  /* catchup_t = -(log real wage - its one-sided trend), positive when the real
     wage has fallen below the path it was on. Replaces Bernanke & Blanchard's
     inflation-surprise term, which is collinear with a filtered trend by
     construction -- see the Python docstring for the algebra. */
  function realWageGap(wage, prices, window) {
    const rw = wage.map((w, i) =>
      (isNum(w) && isNum(prices[i]) && w > 0 && prices[i] > 0)
        ? 100 * Math.log(w / prices[i]) : null);
    const gap = rollingTrendGap(rw, window || 40);
    return gap.map(v => (isNum(v) ? -v : null));
  }

  /* ---------------------------------------------------------------- Eq. W3 */
  /* lambda_t = sum_j c_{j,t} e_j, clipped to [0,1]. The channels are not
     mutually exclusive (a French employee can sit in a SMIC-benchmarked
     agreement AND one with a formal inflation reference), so the raw sum can
     exceed one; clipping keeps lambda readable as "the share of the wage bill
     that moves one-for-one with past prices". */
  function indexationIntensity(coverage, elasticities) {
    const el = { ...DEFAULT_ELASTICITIES, ...(elasticities || {}) };
    const keys = Object.keys(el).filter(k => coverage[k]);
    if (!keys.length) return [];
    const n = coverage[keys[0]].length;
    const out = new Array(n).fill(0);
    for (const k of keys) {
      const col = coverage[k];
      for (let i = 0; i < n; i++) out[i] += (isNum(col[i]) ? col[i] : 0) * el[k];
    }
    return out.map(v => Math.min(1, Math.max(0, v)));
  }

  /* --------------------------------------------------- restricted least squares */
  /* Gauss-Jordan inverse with partial pivoting and a trace-scaled ridge --
     the twin of `_inv` in Python. Not a general-purpose routine: it exists so
     that two languages agree to 1e-9 on well-conditioned problems and fail
     visibly rather than silently pseudo-inverting on ill-conditioned ones. */
  function inv(A, ridge) {
    ridge = ridge === undefined ? 1e-10 : ridge;
    const k = A.length;
    let tr = 0;
    for (let i = 0; i < k; i++) tr += A[i][i];
    const scale = k ? tr / k : 1;
    const eps = ridge * (scale > 0 ? scale : 1);
    const aug = [];
    for (let i = 0; i < k; i++) {
      const row = new Array(2 * k).fill(0);
      for (let j = 0; j < k; j++) row[j] = A[i][j] + (i === j ? eps : 0);
      row[k + i] = 1;
      aug.push(row);
    }
    for (let col = 0; col < k; col++) {
      let piv = col, best = Math.abs(aug[col][col]);
      for (let r = col + 1; r < k; r++) {
        const v = Math.abs(aug[r][col]);
        if (v > best) { best = v; piv = r; }
      }
      if (best < 1e-300) continue;
      if (piv !== col) { const t = aug[col]; aug[col] = aug[piv]; aug[piv] = t; }
      const p = aug[col][col];
      for (let j = 0; j < 2 * k; j++) aug[col][j] /= p;
      for (let r = 0; r < k; r++) {
        if (r === col) continue;
        const f = aug[r][col];
        if (f === 0) continue;
        for (let j = 0; j < 2 * k; j++) aug[r][j] -= f * aug[col][j];
      }
    }
    return aug.map(row => row.slice(k));
  }

  /* Least squares subject to linear restrictions R'b = r.

     R is either one restriction (a flat array of length k) or several (an
     array of m such arrays, i.e. columns). The closed form is the same:

       b_r = b + V R (R'VR)^{-1} (r - R'b),   V = (X'X)^{-1}

     with (R'VR) a scalar in the one-restriction case and m x m otherwise.
     Several are needed as soon as each country has its own dynamics: long-run
     homogeneity then has to bind once per country.

     Standard errors are classical and understate uncertainty on overlapping
     year-on-year data; the site says so where it prints them. */
  function restrictedOls(y, X, names, R, r) {
    const n = X.length, k = X[0].length;
    const XtX = [];
    for (let i = 0; i < k; i++) {
      XtX.push(new Array(k).fill(0));
      for (let j = 0; j < k; j++) {
        let s = 0;
        for (let t = 0; t < n; t++) s += X[t][i] * X[t][j];
        XtX[i][j] = s;
      }
    }
    let V = inv(XtX);
    const Xty = new Array(k).fill(0);
    for (let i = 0; i < k; i++) {
      let s = 0;
      for (let t = 0; t < n; t++) s += X[t][i] * y[t];
      Xty[i] = s;
    }
    let beta = V.map(row => row.reduce((a, v, j) => a + v * Xty[j], 0));
    let dof = n - k;

    if (R) {
      const cols = Array.isArray(R[0]) ? R : [R];       // m columns of length k
      const m = cols.length;
      const rv = Array.isArray(r) ? r : new Array(m).fill(r === undefined ? 0 : r);
      // VR is k x m
      const VR = [];
      for (let i = 0; i < k; i++) {
        VR.push(new Array(m).fill(0));
        for (let a = 0; a < m; a++) {
          let s = 0;
          for (let j = 0; j < k; j++) s += V[i][j] * cols[a][j];
          VR[i][a] = s;
        }
      }
      // RVR is m x m
      const RVR = [];
      for (let a = 0; a < m; a++) {
        RVR.push(new Array(m).fill(0));
        for (let b2 = 0; b2 < m; b2++) {
          let s = 0;
          for (let i = 0; i < k; i++) s += cols[a][i] * VR[i][b2];
          RVR[a][b2] = s;
        }
      }
      /* A single restriction is a scalar divide; routing it through the
         ridged Gauss-Jordan inverse costs accuracy for nothing. */
      const RVRinv = (m === 1) ? [[1 / RVR[0][0]]] : inv(RVR);
      // resid_r = r - R'b
      const rb = new Array(m).fill(0);
      for (let a = 0; a < m; a++) {
        let s = 0;
        for (let i = 0; i < k; i++) s += cols[a][i] * beta[i];
        rb[a] = rv[a] - s;
      }
      const adj = RVRinv.map(row => row.reduce((acc, v, j) => acc + v * rb[j], 0));
      beta = beta.map((b2, i) => b2 + VR[i].reduce((acc, v, a) => acc + v * adj[a], 0));
      const V2 = [];
      for (let i = 0; i < k; i++) {
        V2.push(new Array(k));
        for (let j = 0; j < k; j++) {
          let s = 0;
          for (let a = 0; a < m; a++)
            for (let b2 = 0; b2 < m; b2++) s += VR[i][a] * RVRinv[a][b2] * VR[j][b2];
          V2[i][j] = V[i][j] - s;
        }
      }
      V = V2;
      dof = n - k + m;
    }

    let ssr = 0, ym = 0;
    for (let t = 0; t < n; t++) ym += y[t];
    ym /= n;
    let tss = 0;
    const resid = new Array(n);
    for (let t = 0; t < n; t++) {
      let fit = 0;
      for (let i = 0; i < k; i++) fit += X[t][i] * beta[i];
      resid[t] = y[t] - fit;
      ssr += resid[t] * resid[t];
      tss += (y[t] - ym) * (y[t] - ym);
    }
    const s2 = ssr / Math.max(dof, 1);
    const se = V.map((row, i) => Math.sqrt(Math.max(row[i] * s2, 0)));
    return {
      names, beta, se, resid, nobs: n,
      r2: tss > 0 ? 1 - ssr / tss : NaN,
      coef(name) { const i = this.names.indexOf(name); return i < 0 ? 0 : this.beta[i]; },
      /* Effective coefficients for one country: a block is either
         country-specific (`gw_l1__DE`) or common (`gw_l1`). Collapsing the two
         lets the gains and the simulator be written once. */
      forCountry(country) {
        const out = {};
        for (let i = 0; i < this.names.length; i++) {
          const n2 = this.names[i];
          const k2 = n2.indexOf("__");
          if (k2 >= 0) {
            if (country && n2.slice(k2 + 2) === country) out[n2.slice(0, k2)] = this.beta[i];
          } else if (!(n2 in out)) out[n2] = this.beta[i];
        }
        return out;
      },
      sumOf(prefix, country) {
        if (country) {
          const c = this.forCountry(country);
          let s = 0;
          for (const n2 of Object.keys(c)) if (n2.startsWith(prefix)) s += c[n2];
          return s;
        }
        let s = 0;
        for (let i = 0; i < this.names.length; i++)
          if (this.names[i].startsWith(prefix) && this.names[i].indexOf("__") < 0)
            s += this.beta[i];
        return s;
      },
      tstat() { return this.beta.map((b2, i) => (this.se[i] > 0 ? b2 / this.se[i] : NaN)); },
    };
  }

  /* ------------------------------------------------------------- design matrix */
  function lagged(series, lag) {
    const out = new Array(series.length).fill(null);
    for (let t = lag; t < series.length; t++) out[t] = series[t - lag];
    return out;
  }

  /* Build X, y from a column map. `blocks` is [[prefix, series, [lags]], ...].
     Rows with any missing regressor or a missing dependent variable are
     dropped, exactly as pandas' `.notna().all(axis=1)` does in Python. */
  function design(yCol, blocks, addConst, extraCols) {
    const names = [];
    const cols = [];
    if (addConst !== false) { names.push("const"); cols.push(null); }
    for (const [prefix, series, lags] of blocks) {
      if (!series) continue;
      for (const L of lags) { names.push(prefix + L); cols.push(lagged(series, L)); }
    }
    if (extraCols) for (const [nm, col] of extraCols) { names.push(nm); cols.push(col); }

    const n = yCol.length, X = [], y = [], rows = [];
    for (let t = 0; t < n; t++) {
      if (!isNum(yCol[t])) continue;
      const row = new Array(cols.length);
      let ok = true;
      for (let i = 0; i < cols.length; i++) {
        const v = cols[i] === null ? 1 : cols[i][t];
        if (!isNum(v)) { ok = false; break; }
        row[i] = v;
      }
      if (!ok) continue;
      X.push(row); y.push(yCol[t]); rows.push(t);
    }
    return { names, X, y, rows };
  }

  function mul(a, b) { return a.map((v, i) => (isNum(v) && isNum(b[i]) ? v * b[i] : null)); }
  function range1(p) { return Array.from({ length: p }, (_, i) => i + 1); }
  function range0(p) { return Array.from({ length: p + 1 }, (_, i) => i); }

  /* ---------------------------------------------------------------- Eq. W4 */
  function fitWageEquation(panel, cfg, interact) {
    cfg = { ...DEFAULT_CONFIG, ...(cfg || {}) };
    const p = cfg.lags;
    const blocks = [
      ["gw_l", panel.gw, range1(p)],
      ["pistar_l", panel.pistar, range1(p)],
    ];
    if (panel.slack) blocks.push(["slack_l", panel.slack, range1(p)]);
    blocks.push(["cu_l", panel.catchup, range1(p)]);
    if (interact !== false && panel.lambda)
      blocks.push(["cux_l", mul(panel.lambda, panel.catchup), range1(p)]);
    if (panel.gpty) blocks.push(["gpty_l", panel.gpty, [1]]);
    if (panel.dmw) blocks.push(["dmw_l", panel.dmw, [0]]);

    const d = design(panel.gw, blocks);
    if (d.y.length <= d.names.length + 2) return null;
    const R = cfg.homogeneity
      ? d.names.map(n => (n.startsWith("gw_l") || n.startsWith("pistar_l") ? 1 : 0))
      : null;
    return restrictedOls(d.y, d.X, d.names, R, 1);
  }

  /* ---------------------------------------------------------------- Eq. W5 */
  function fitPriceEquation(panel, cfg) {
    cfg = { ...DEFAULT_CONFIG, ...(cfg || {}) };
    const p = cfg.lags;
    const blocks = [["gp_l", panel.gp, range1(p)], ["gw_l", panel.gw, range0(p)]];
    if (panel.grpe) blocks.push(["grpe_l", panel.grpe, range0(p)]);
    if (panel.grpf) blocks.push(["grpf_l", panel.grpf, range0(p)]);
    if (panel.h) blocks.push(["h_l", panel.h, range0(p)]);
    if (panel.gpty) blocks.push(["gpty_l", panel.gpty, [1]]);

    const d = design(panel.gp, blocks);
    if (d.y.length <= d.names.length + 2) return null;
    const R = cfg.homogeneity
      ? d.names.map(n => (n.startsWith("gp_l") || n.startsWith("gw_l") ? 1 : 0))
      : null;
    return restrictedOls(d.y, d.X, d.names, R, 1);
  }

  /* --------------------------------------------------------------- Eq. W4' */
  /* The panel wage equation, PARTIALLY POOLED.

     Blocks named in `free` get their own coefficients in every country; the
     rest are common. The default frees the dynamics -- persistence, the trend
     weight, the slack response -- and pools only the catch-up level and its
     interaction with lambda.

     Pooling everything is not credible: wage-setting in Belgium, where half
     the private sector sits on a pivot-index trigger, and in the United
     States, where almost nobody does, are not the same process, and an
     estimator that says they are hands the catch-up term whatever the common
     persistence gets wrong. On this panel a Chow test rejects pooling at
     F = 2.9 on (120, 1030). Freeing everything is the opposite failure:
     lambda is constant in Belgium and spans 0.014 to 0.124 in sixty-five
     years of US data, so a country-by-country interaction is identified off
     nothing. The split follows the economics -- what differs by country is
     free, the one parameter the model is about is common, because that is
     where the cross-country variation lives.

     Because each country keeps its own persistence, the three-year catch-up
     Lambda is country-specific even though the catch-up coefficients are
     common: the same impulse propagates differently through different
     dynamics. Homogeneity is therefore imposed once per country. */
  function fitPanelWageEquation(panels, cfg, interact, free) {
    cfg = { ...DEFAULT_CONFIG, ...(cfg || {}) };
    const p = cfg.lags;
    const freeSet = new Set(free === undefined ? ["gw", "pistar", "slack"] : free);
    const codes = Object.keys(panels).sort();

    const perCountry = [];
    let union = [];
    for (const code of codes) {
      const panel = panels[code];
      const blocks = [
        ["gw_l", panel.gw, range1(p)],
        ["pistar_l", panel.pistar, range1(p)],
        ["cu_l", panel.catchup, range1(p)],
      ];
      if (panel.slack) blocks.push(["slack_l", panel.slack, range1(p)]);
      if (interact !== false && panel.lambda)
        blocks.push(["cux_l", mul(panel.lambda, panel.catchup), range1(p)]);

      const named = [];
      for (const [prefix, series, lags] of blocks) {
        if (!series) continue;
        const stem = prefix.split("_l")[0];
        for (const L of lags) {
          const nm = freeSet.has(stem) ? `${prefix}${L}__${code}` : `${prefix}${L}`;
          named.push([nm, lagged(series, L)]);
        }
      }
      perCountry.push({ code, named, y: panel.gw });
      for (const [nm] of named) if (!union.includes(nm)) union.push(nm);
    }
    if (!union.length) return null;
    const feNames = codes.map(c => "fe_" + c);
    const allNames = union.concat(feNames);

    const X = [], Y = [];
    for (const { code, named, y } of perCountry) {
      const map = new Map(named);
      const n = y.length;
      for (let t = 0; t < n; t++) {
        if (!isNum(y[t])) continue;
        const row = new Array(allNames.length).fill(0);
        let ok = true;
        for (let i = 0; i < union.length; i++) {
          const nm = union[i];
          const k2 = nm.indexOf("__");
          // A country's own column is structurally zero on other countries'
          // rows -- that is the design, not missing data.
          if (k2 >= 0 && nm.slice(k2 + 2) !== code) { row[i] = 0; continue; }
          const col = map.get(nm);
          if (!col) { ok = false; break; }
          const v = col[t];
          if (!isNum(v)) { ok = false; break; }
          row[i] = v;
        }
        if (!ok) continue;
        row[union.length + codes.indexOf(code)] = 1;
        X.push(row); Y.push(y[t]);
      }
    }
    if (Y.length <= allNames.length + 2) return null;

    let R = null, rv = 0;
    if (cfg.homogeneity) {
      const isDyn = n2 => n2.startsWith("gw_l") || n2.startsWith("pistar_l");
      if (freeSet.has("gw") || freeSet.has("pistar")) {
        R = codes.map(c => allNames.map(nm => {
          const k2 = nm.indexOf("__");
          const base = k2 >= 0 ? nm.slice(0, k2) : nm;
          const owner = k2 >= 0 ? nm.slice(k2 + 2) : null;
          return (isDyn(base) && (owner === null || owner === c)) ? 1 : 0;
        }));
        rv = codes.map(() => 1);
      } else {
        R = allNames.map(nm => (isDyn(nm) ? 1 : 0));
        rv = 1;
      }
    }
    return restrictedOls(Y, X, allNames, R, rv);
  }

  /* ----------------------------------------------------------- Eqs. W6-W8 */
  /* Response of an AR(p) to a permanent unit step in a driver, read at the
     end of the horizon. Three years, not the long run: the homogeneity
     restriction sets the long-run pass-through to one by assumption, so the
     long run cannot distinguish regimes. Three years can. */
  function cumulativeResponse(own, driver, horizon, stat) {
    horizon = horizon || 3 * PPY;
    const y = [];
    for (let t = 0; t < horizon; t++) {
      let v = 0;
      for (let k = 1; k <= own.length; k++) if (t - k >= 0) v += own[k - 1] * y[t - k];
      for (let k = 0; k < driver.length; k++) if (t - k >= 0) v += driver[k];
      y.push(v);
    }
    if (stat === "mean") return y.reduce((a, b) => a + b, 0) / y.length;
    return y[y.length - 1];
  }

  /* `country` selects that country's own dynamics in a partially pooled fit.
     The catch-up coefficients are common, but the persistence they propagate
     through is not, so Lambda differs across countries at the same lambda --
     and it should: an own-lag sum of 0.97 and one of 0.22 do not turn the same
     impulse into the same three-year response. */
  function priceToWageGain(wageFit, lam, p, horizon, country) {
    p = p || 4;
    const c = country ? wageFit.forCountry(country) : null;
    const get = n => (c ? (c[n] || 0) : wageFit.coef(n));
    const own = [], drv = [0];
    for (let k = 1; k <= p; k++) own.push(get("gw_l" + k));
    for (let k = 1; k <= p; k++) drv.push(get("cu_l" + k) + lam * get("cux_l" + k));
    return cumulativeResponse(own, drv, horizon);
  }

  function wageToPriceGain(priceFit, p, horizon) {
    p = p || 4;
    const own = [], drv = [];
    for (let k = 1; k <= p; k++) own.push(priceFit.coef("gp_l" + k));
    for (let k = 0; k <= p; k++) drv.push(priceFit.coef("gw_l" + k));
    return cumulativeResponse(own, drv, horizon);
  }

  function fiscalGain(priceFit, phiE, mpc, p, horizon) {
    p = p || 4;
    const own = [], drv = [];
    for (let k = 1; k <= p; k++) own.push(priceFit.coef("gp_l" + k));
    let any = false;
    for (let k = 0; k <= p; k++) {
      const c = priceFit.coef("h_l" + k);
      if (c !== 0) any = true;
      drv.push(c);
    }
    if (!any) return 0;
    return phiE * mpc * cumulativeResponse(own, drv, horizon);
  }

  /* G_t = Lambda(lambda_t) * M. G > 1 is the spiral condition: one turn of the
     loop more than reproduces itself inside the horizon. Time variation is
     entirely institutional, which is the claim being tested -- what changed
     between the 1970s and the 2020s is who is indexed, not how firms price. */
  function spiralGain(wageFit, priceFit, lambda, opts) {
    opts = opts || {};
    const M = wageToPriceGain(priceFit, opts.p, opts.horizon);
    const Phi = fiscalGain(priceFit, opts.phiE || 0, opts.mpc || 0, opts.p, opts.horizon);
    return lambda.map(l => {
      if (!isNum(l)) return { lambda: null, Lambda: null, M, G: null, G_fiscal: null };
      const L = priceToWageGain(wageFit, l, opts.p, opts.horizon, opts.country);
      return { lambda: l, Lambda: L, M, G: L * M, G_fiscal: (L + Phi) * M };
    });
  }

  /* -------------------------------------------------------------- Eq. W10 */
  /* Handouts enter ADDITIVELY. A recurring income source is weighted by its
     share of income; a one-off payment has no share -- it is a flow that
     exists in one year and not the next -- and its component index is already
     one plus the payment as a fraction of disposable income. Weighting it
     again by a "handout share" would shrink a EUR 300 Energiepreispauschale to
     a rounding error. */
  function effectiveWageIndex(components, shares, handoutCol) {
    handoutCol = handoutCol || "handout";
    const keys = Object.keys(shares).filter(k => k !== handoutCol && components[k]);
    let tot = 0;
    for (const k of keys) tot += shares[k];
    if (!(tot > 0)) return [];
    const n = components[keys[0]].length;
    const out = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      let s = 0, ok = true;
      for (const k of keys) {
        const v = components[k][i];
        if (!isNum(v)) { ok = false; break; }
        s += v * (shares[k] / tot);
      }
      if (!ok) continue;
      const h = components[handoutCol] ? components[handoutCol][i] : 100;
      out[i] = s + (isNum(h) ? h - 100 : 0);
    }
    return out;
  }

  /* -------------------------------------------------------------- Eq. W11 */
  /* Measured real deflates by the recorded CPI, which price-based support has
     already lowered. Subsidy-neutral real deflates by the index that would
     have been recorded without those measures. The gap between the two is the
     part of measured real income that is a consequence of HOW support was
     delivered rather than of what households received -- and it is a policy
     lever hiding inside a statistical convention. */
  function realEffectiveWage(ewi, cpi, wedge, baseIdx) {
    const n = ewi.length;
    const real = new Array(n).fill(null);
    const rsn = new Array(n).fill(null);
    let base = baseIdx;
    if (!isNum(base)) { base = 0; while (base < n && !isNum(ewi[base])) base++; }

    const ratio = ewi.map((v, i) => (isNum(v) && isNum(cpi[i]) && cpi[i] !== 0 ? v / cpi[i] : null));
    const b0 = ratio[base];
    if (isNum(b0)) for (let i = 0; i < n; i++) if (isNum(ratio[i])) real[i] = 100 * ratio[i] / b0;

    if (wedge) {
      const star = new Array(n).fill(null);
      let cum = 0;
      for (let i = 0; i < n; i++) {
        cum += (isNum(wedge[i]) ? wedge[i] : 0) / 100 / PPY;
        star[i] = isNum(cpi[i]) ? cpi[i] * Math.exp(-cum) : null;
      }
      const r2 = ewi.map((v, i) => (isNum(v) && isNum(star[i]) && star[i] !== 0 ? v / star[i] : null));
      const b2 = r2[base];
      if (isNum(b2)) for (let i = 0; i < n; i++) if (isNum(r2[i])) rsn[i] = 100 * r2[i] / b2;
    }
    return { nominal: ewi, real, real_subsidy_neutral: rsn };
  }

  /* -------------------------------------------------------------- Eq. W12 */
  /* Propagate an energy shock through prices, wages, the fiscal response and
     expectations. The monetary rule is a direct slack response rather than a
     rate rule: the estimated wage equation takes slack, not the policy rate,
     so a Taylor rule would need an IS curve we have not estimated. `taylor` is
     percentage points of slack opened per percentage point of inflation above
     trend -- a reduced-form sacrifice-rate dial. */
  function simulateLoop(wageFit, priceFit, params) {
    const pr = {
      lam: 0.10, anchorQ: 0.05, phiE: 0, mpc: 0.30, taylor: 0.5,
      shock: 10, shockLen: 4, horizon: 24, p: 4, country: null, ...(params || {}),
    };
    const p = pr.p;
    const wc = pr.country ? wageFit.forCountry(pr.country) : null;
    const wget = n => (wc ? (wc[n] || 0) : wageFit.coef(n));
    const a = [], b = [], c = [], d = [], B = [], M = [], E = [], P = [];
    for (let k = 1; k <= p; k++) {
      a.push(wget("gw_l" + k));
      b.push(wget("pistar_l" + k));
      c.push(wget("slack_l" + k));
      d.push(wget("cu_l" + k) + pr.lam * wget("cux_l" + k));
      B.push(priceFit.coef("gp_l" + k));
    }
    for (let k = 0; k <= p; k++) {
      M.push(priceFit.coef("gw_l" + k));
      E.push(priceFit.coef("grpe_l" + k));
      P.push(priceFit.coef("h_l" + k));
    }
    const kg = kalmanGain(pr.anchorQ);
    const H = pr.horizon;
    const gp = new Array(H).fill(0), gw = new Array(H).fill(0);
    const pis = new Array(H).fill(0), cu = new Array(H).fill(0);
    const h = new Array(H).fill(0), sl = new Array(H).fill(0);
    const rw = new Array(H).fill(0);
    const grpe = Array.from({ length: H }, (_, t) => (t < pr.shockLen ? pr.shock : 0));

    const lagsum = (co, arr, t, start) => {
      let s = 0;
      for (let i = 0; i < co.length; i++) { const j = t - (i + start); if (j >= 0) s += co[i] * arr[j]; }
      return s;
    };

    for (let t = 0; t < H; t++) {
      gw[t] = lagsum(a, gw, t, 1) + lagsum(b, pis, t, 1)
            + lagsum(c, sl, t, 1) + lagsum(d, cu, t, 1);
      gp[t] = lagsum(B, gp, t, 1) + lagsum(M, gw, t, 0)
            + lagsum(E, grpe, t, 0) + lagsum(P, h, t, 0);
      const prev = t > 0 ? pis[t - 1] : 0;
      pis[t] = prev + kg * (gp[t] - prev);
      /* The catch-up regressor has to be the SAME OBJECT the coefficients
         were estimated on -- the deviation of the log real wage from its
         trend, in percent -- not the Bernanke & Blanchard inflation surprise.
         In a deviation-from-baseline simulation the trend real wage IS the
         baseline, so the gap is the cumulated real-wage shortfall; gw and gp
         are four-quarter rates, so one quarter adds a quarter of the annual
         rate. */
      rw[t] = (t > 0 ? rw[t - 1] : 0) + (gw[t] - gp[t]) / PPY;
      cu[t] = -rw[t];
      const gap = gp[t] - pis[t];
      h[t] = pr.phiE * Math.max(gap, 0) * pr.mpc;
      sl[t] = -pr.taylor * gap;
    }
    return {
      quarter: Array.from({ length: H }, (_, i) => i),
      energy: grpe, price_inflation: gp, wage_growth: gw, trend: pis,
      catchup: cu, handout: h, slack: sl,
      real_wage: gw.map((v, i) => v - gp[i]),
      real_wage_level: rw,
    };
  }

  return {
    PPY, DEFAULT_CONFIG, DEFAULT_ELASTICITIES,
    kalmanGain, trendInflation, rollingTrendGap, realWageGap,
    indexationIntensity, inv, restrictedOls,
    fitWageEquation, fitPriceEquation, fitPanelWageEquation,
    cumulativeResponse, priceToWageGain, wageToPriceGain, fiscalGain, spiralGain,
    effectiveWageIndex, realEffectiveWage, simulateLoop,
  };
})();

/* A top-level `const` in a classic script creates a script-scoped binding, not
   a property of `window`, so wage_app.js cannot reach it as `window.WageEngine`
   without this line. Both spellings now work, in the browser and under node. */
if (typeof window !== "undefined") window.WageEngine = WageEngine;
if (typeof module !== "undefined" && module.exports) module.exports = WageEngine;
