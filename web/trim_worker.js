/* Web Worker that runs the trimmed-mean engine off the main thread.

   Protocol (postMessage):
     -> { type:"init", panels: { cpi45: {inflation, weights, months}, ... } }
     <- { type:"ready", scopes: [...] }
     -> { type:"compute", id, scope, params: { lower, upper, sa, saWindow,
                                               ppy, weightVintage, excluded } }
     <- { type:"result", id, scope, rate, index, yoy, horizons, n, latest, ms }
     <- { type:"error", id, message }

   The seasonally adjusted panel is the only expensive object and it depends
   only on (scope, sa method, window, annualisation), never on the trim
   fractions — so it is cached here and a trim-slider drag costs one sort per
   month. */
"use strict";
importScripts("trim_engine.js");

const PANELS = {};
const CACHE = new Map();
const CACHE_MAX = 8;           // each entry is a full SA panel (~1 MB); bound it

function cachePut(key, val) {
  if (CACHE.size >= CACHE_MAX) CACHE.delete(CACHE.keys().next().value); // oldest
  CACHE.set(key, val);
}
const cacheView = { get: k => CACHE.get(k), set: cachePut };

onmessage = e => {
  const msg = e.data;
  try {
    if (msg.type === "init") {
      for (const [name, p] of Object.entries(msg.panels || {})) {
        if (p && p.inflation && p.weights)
          PANELS[name] = TrimEngine.toPanel(p.inflation, p.weights, p.months);
      }
      postMessage({ type: "ready", scopes: Object.keys(PANELS) });
      return;
    }
    if (msg.type === "compute") {
      const panel = PANELS[msg.scope];
      if (!panel) throw new Error(`no panel for scope "${msg.scope}"`);
      const t0 = Date.now();
      const res = TrimEngine.compute(panel, { ...msg.params, cacheTag: msg.scope },
                                     cacheView);
      postMessage({
        type: "result", id: msg.id, scope: msg.scope,
        rate: res.rate, index: res.index, yoy: res.yoy,
        horizons: res.horizons, n: res.n, latest: res.latest,
        ms: Date.now() - t0,
      });
    }
  } catch (err) {
    postMessage({ type: "error", id: msg.id, message: String(err && err.message || err) });
  }
};
