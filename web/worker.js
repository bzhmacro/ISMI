/* Web Worker that runs the ISM engine off the main thread.

   Protocol (postMessage):
     -> { type:"init", panels: { pce: {inflation, weights}, cpi: {...} } }
     <- { type:"ready", backbones: [...] }
     -> { type:"compute", id, backbone,
          params: { ar, W, k, scheme, rhoCap, excluded } }
     <- { type:"result", id, backbone, ISM, S_pos, S_neg, drivers, ms }
     <- { type:"error", id, message }

   Residual / rho panels are cached (see engine.compute), so only changes to
   (backbone, AR order, window W) trigger a regression pass; everything else
   is a near-instant re-aggregation. */
"use strict";
importScripts("engine.js");

const PANELS = {};
const CACHE = new Map();
const CACHE_MAX = 24;          // each entry ~ a residual panel (~1 MB); bound it

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
        if (p && p.inflation && p.weights) PANELS[name] = ISMEngine.toPanel(p.inflation, p.weights);
      }
      postMessage({ type: "ready", backbones: Object.keys(PANELS) });
      return;
    }
    if (msg.type === "compute") {
      const panel = PANELS[msg.backbone];
      if (!panel) throw new Error(`no panel for backbone "${msg.backbone}"`);
      const t0 = Date.now();
      const res = ISMEngine.compute(panel, { ...msg.params, cacheTag: msg.backbone }, cacheView);
      postMessage({
        type: "result", id: msg.id, backbone: msg.backbone,
        ISM: res.ISM, S_pos: res.S_pos, S_neg: res.S_neg, drivers: res.drivers,
        ms: Date.now() - t0,
      });
    }
  } catch (err) {
    postMessage({ type: "error", id: msg.id, message: String(err && err.message || err) });
  }
};
