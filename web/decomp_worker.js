/* Web Worker that runs the supply/demand decomposition engine off the main
   thread (Shapiro 2022-18). Twin of worker.js.

   Protocol (postMessage):
     -> { type:"init", panels:{ headline:{logp,logq,w}, core:{...} } }
     <- { type:"ready", scopes:[...] }
     -> { type:"compute", id, scope, params:{ J, W, h, precisionCut, excluded } }
     <- { type:"result", id, scope, ...series..., drivers, ms }
     <- { type:"error", id, message }

   Residual panels are cached in the engine (keyed by scope, J, W, h), so only
   changes to those trigger a regression pass; the precision cut-off, category
   exclusions and the view switch re-aggregate near-instantly. */
"use strict";
importScripts("decomp_engine.js");

const PANELS = {};
const CACHE = new Map();
const CACHE_MAX = 8;          // each residual panel is large; bound it

function cachePut(key, val) {
  if (CACHE.size >= CACHE_MAX) CACHE.delete(CACHE.keys().next().value);
  CACHE.set(key, val);
}
const cacheView = { get: k => CACHE.get(k), set: cachePut };

onmessage = e => {
  const msg = e.data;
  try {
    if (msg.type === "init") {
      for (const [name, p] of Object.entries(msg.panels || {})) {
        if (p && p.logp && p.logq && p.w)
          PANELS[name] = DecompEngine.toPanel(p.logp, p.logq, p.infl || null, p.w);
      }
      postMessage({ type: "ready", scopes: Object.keys(PANELS) });
      return;
    }
    if (msg.type === "compute") {
      const panel = PANELS[msg.scope];
      if (!panel) throw new Error(`no panel for scope "${msg.scope}"`);
      const t0 = Date.now();
      const r = DecompEngine.compute(panel, { ...msg.params, cacheTag: msg.scope }, cacheView);
      postMessage({
        type: "result", id: msg.id, scope: msg.scope,
        supply: r.supply, demand: r.demand, ambiguous: r.ambiguous, total: r.total,
        supply_yoy: r.supply_yoy, demand_yoy: r.demand_yoy,
        ambiguous_yoy: r.ambiguous_yoy, total_yoy: r.total_yoy,
        sh_supply: r.sh_supply, sh_demand: r.sh_demand, sh_ambiguous: r.sh_ambiguous,
        drivers: r.drivers, ms: Date.now() - t0,
      });
    }
  } catch (err) {
    postMessage({ type: "error", id: msg.id, message: String(err && err.message || err) });
  }
};
