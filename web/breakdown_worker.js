/* breakdown_worker.js — contributions to headline inflation, split into the
   part an AR benchmark expected and the part it did not.
   ===========================================================================

   THE DECOMPOSITION
   -----------------
   For category i in month t the panel gives monthly inflation pi[i,t] and an
   expenditure weight w[i,t]. Weights are renormalised each month over the
   categories that are valid that month — finite inflation, finite weight,
   finite residual — exactly as engine.js does for the ISM (Eqs. 6-8), so the
   two views never disagree about what the basket is:

       wn[i,t] = w[i,t] / sum_j w[j,t]           over valid j

   The contribution of i to headline monthly inflation is then

       c[i,t] = wn[i,t] * pi[i,t]

   The AR(p) rolling benchmark from engine.js supplies the residual e[i,t], so
   pi[i,t] = pihat[i,t] + e[i,t] and the contribution splits ADDITIVELY:

       c[i,t] = wn*pihat   +   wn*e
                (expected)     (surprise)

   That is the whole idea of the view: every bar can be cut into the part the
   benchmark saw coming and the part it did not, and the two pieces always sum
   back to the bar. "Surprise" here means precisely "deviation from the
   category's own rolling AR(p) forecast" — the paper's definition of a shock —
   not a deviation from any published consensus.

   Over 12 months the split is only APPROXIMATELY additive: true 12-month
   inflation compounds, whereas summing 12 monthly contributions is a linear
   approximation. It is the standard one, and the error is second-order at
   these magnitudes, but it is why the totals here will not tie exactly to the
   published headline. The app shows both and reports the gap rather than
   hiding it.

   Protocol
     -> { type:"init", inflation, weights, groupOf:[groupIndex per category] }
     <- { type:"ready", n, ncat }
     -> { type:"compute", id, p, W, horizon, detailMonths }
     <- { type:"result", id, groupContrib, groupSurprise, total, totalSurprise,
          catContrib, catSurprise, detailFrom, ms }
   =========================================================================== */
"use strict";
importScripts("engine.js");

let PANEL = null;      // { infl, w, n } from ISMEngine.toPanel
let GROUP_OF = null;   // Int32Array: category index -> group index
let NGROUP = 0;
const RESID_CACHE = new Map();   // "p|W" -> array of {resid}

function residuals(p, W) {
  const key = `${p}|${W}`;
  if (RESID_CACHE.has(key)) return RESID_CACHE.get(key);
  const out = [];
  for (let c = 0; c < PANEL.infl.length; c++) {
    out.push(ISMEngine.rollingAR(PANEL.infl[c], p, W).resid);
  }
  if (RESID_CACHE.size > 6) RESID_CACHE.delete(RESID_CACHE.keys().next().value);
  RESID_CACHE.set(key, out);
  return out;
}

/* Rolling sum over `h` periods, NaN-aware: a window with any gap yields null
   rather than silently summing a short window, which would understate the
   contribution and make the bars stop tying to the total. */
function rollingSum(arr, h) {
  const n = arr.length;
  const out = new Array(n).fill(null);
  if (h <= 1) {
    for (let t = 0; t < n; t++) out[t] = Number.isFinite(arr[t]) ? arr[t] : null;
    return out;
  }
  for (let t = h - 1; t < n; t++) {
    let s = 0, ok = true;
    for (let j = 0; j < h; j++) {
      const v = arr[t - j];
      if (!Number.isFinite(v)) { ok = false; break; }
      s += v;
    }
    out[t] = ok ? s : null;
  }
  return out;
}

onmessage = (e) => {
  const msg = e.data;
  try {
    if (msg.type === "init") {
      PANEL = ISMEngine.toPanel(msg.inflation, msg.weights);
      GROUP_OF = Int32Array.from(msg.groupOf);
      NGROUP = msg.ngroup;
      postMessage({ type: "ready", n: PANEL.n, ncat: PANEL.infl.length });
      return;
    }

    if (msg.type === "compute") {
      const t0 = Date.now();
      const { p, W, horizon } = msg;
      const detailMonths = msg.detailMonths || 60;
      const R = residuals(p, W);
      const { infl, w, n } = PANEL;
      const ncat = infl.length;

      // Monthly contribution and surprise, per category.
      const cMonthly = [];
      const sMonthly = [];
      for (let c = 0; c < ncat; c++) {
        cMonthly.push(new Float64Array(n).fill(NaN));
        sMonthly.push(new Float64Array(n).fill(NaN));
      }

      for (let t = 0; t < n; t++) {
        let wsum = 0;
        for (let c = 0; c < ncat; c++) {
          if (Number.isFinite(infl[c][t]) && Number.isFinite(w[c][t]) &&
              Number.isFinite(R[c][t])) wsum += w[c][t];
        }
        if (!(wsum > 0)) continue;
        for (let c = 0; c < ncat; c++) {
          if (!(Number.isFinite(infl[c][t]) && Number.isFinite(w[c][t]) &&
                Number.isFinite(R[c][t]))) continue;
          const wn = w[c][t] / wsum;
          cMonthly[c][t] = wn * infl[c][t];
          sMonthly[c][t] = wn * R[c][t];
        }
      }

      // Aggregate to groups, then apply the horizon.
      const gC = [], gS = [];
      for (let g = 0; g < NGROUP; g++) {
        gC.push(new Float64Array(n));
        gS.push(new Float64Array(n));
      }
      const anyValid = new Uint8Array(n);
      for (let t = 0; t < n; t++) {
        let seen = 0;
        for (let c = 0; c < ncat; c++) {
          const v = cMonthly[c][t];
          if (!Number.isFinite(v)) continue;
          seen = 1;
          gC[GROUP_OF[c]][t] += v;
          gS[GROUP_OF[c]][t] += sMonthly[c][t];
        }
        anyValid[t] = seen;
      }
      for (let t = 0; t < n; t++) {
        if (anyValid[t]) continue;
        for (let g = 0; g < NGROUP; g++) { gC[g][t] = NaN; gS[g][t] = NaN; }
      }

      const groupContrib = gC.map((a) => rollingSum(a, horizon));
      const groupSurprise = gS.map((a) => rollingSum(a, horizon));

      const totMonthly = new Float64Array(n);
      const totSMonthly = new Float64Array(n);
      for (let t = 0; t < n; t++) {
        if (!anyValid[t]) { totMonthly[t] = NaN; totSMonthly[t] = NaN; continue; }
        let a = 0, b = 0;
        for (let g = 0; g < NGROUP; g++) { a += gC[g][t]; b += gS[g][t]; }
        totMonthly[t] = a; totSMonthly[t] = b;
      }
      const total = rollingSum(totMonthly, horizon);
      const totalSurprise = rollingSum(totSMonthly, horizon);

      // Per-category detail, only for the recent window the UI lets you select.
      // Shipping all 70 x 800 would dwarf the useful payload.
      const from = Math.max(0, n - detailMonths);
      const catContrib = [], catSurprise = [];
      for (let c = 0; c < ncat; c++) {
        catContrib.push(rollingSum(cMonthly[c], horizon).slice(from));
        catSurprise.push(rollingSum(sMonthly[c], horizon).slice(from));
      }

      postMessage({
        type: "result", id: msg.id,
        groupContrib, groupSurprise, total, totalSurprise,
        catContrib, catSurprise, detailFrom: from,
        ms: Date.now() - t0,
      });
    }
  } catch (err) {
    postMessage({ type: "error", id: msg.id, message: String((err && err.message) || err) });
  }
};
