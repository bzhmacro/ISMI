/* engine.js (TEMPLATE) -- the maths IN THE BROWSER.
 *
 * A line-for-line port of src/pkg/engine.py. It MUST stay in sync; the contract
 * is enforced by tests/test_web_engine_parity.py, which runs both on the same
 * synthetic panel (incl. missing data + rank-deficient windows) and asserts the
 * residuals, momentum, and index match. Match the Python's numerical choices:
 * the same rolling regression, the same lstsq/min-norm fallback.
 *
 * Exposed as a global `ISMEngine` so worker.js can importScripts() it.
 */
"use strict";
(function (global) {
  // panel: { dates:[...], units:[...], cols: { unit: [v,...] } }
  function toPanel(inflation, weights) {
    const cols = {}, wcols = {};
    inflation.units.forEach((u, i) => { cols[u] = inflation.values[i]; });
    weights.units.forEach((u, i) => { wcols[u] = weights.values[i]; });
    return { dates: inflation.dates, units: inflation.units, infl: cols, w: wcols };
  }

  // Solve min-norm least squares (normal equations + pseudo-inverse fallback).
  function lstsq(X, y) { /* implement to match numpy.lstsq for rank-deficient X */ }

  function rollingArResiduals(panel, p) { /* Eq.(3): per unit, W-month window */ }
  function momentumSignals(resid, K) { /* Eqs.(4)-(5): consecutive runs */ }
  function weightedShares(mPos, mNeg, w) { /* Eqs.(6)-(7): renormalise per month */ }

  // THE entry point the worker calls. Cache residual panels per (tag, AR, W).
  function compute(panel, params, cache) {
    const { ar = 1, W = 120, k = 3, scheme = "extensive", cacheTag = "" } = params;
    const key = `${cacheTag}|ar${ar}|W${W}`;
    let resid = cache && cache.get(key);
    if (!resid) { resid = rollingArResiduals(panel, ar /*, W */); cache && cache.set(key, resid); }
    const { mPos, mNeg } = momentumSignals(resid, k);
    const { sPos, sNeg } = weightedShares(mPos, mNeg, panel.w /*, scheme */);
    const Index = sPos.map((v, i) => v - sNeg[i]);   // Eq.(8)
    return { Index, S_pos: sPos, S_neg: sNeg, drivers: [] };
  }

  global.ISMEngine = { toPanel, compute };
})(typeof self !== "undefined" ? self : this);
