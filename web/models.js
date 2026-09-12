/* The top-level Model bar.

   The site now carries four models — Inflation Shock Momentum, Supply vs
   Demand, Trimmed mean & median, and CPI -> PCE — each a self-contained
   controller over its own <div id="…-view">. Rather than have every app know
   about the others, each registers itself here and this file owns the bar, the
   show/hide, the subtitle, and the lazy first init.

   Registration order is display order:

     ModelBar.register({ key, label, viewId, sub, init });

   `init` is called the first time a model is shown (so the ISM page does not
   download the decomposition payload, and vice versa) and may be omitted for a
   model whose view is already live. `mount()` builds the bar once the DOM is
   ready and shows the first registered model. */
"use strict";

const ModelBar = (() => {
  const MODELS = [];
  let current = null, mounted = false;
  const $ = id => document.getElementById(id);

  function register(model) {
    MODELS.push(model);
    if (mounted) build();          // registered late: rebuild the bar
  }

  function build() {
    const host = $("model");
    if (!host) return;
    host.innerHTML = "";
    MODELS.forEach(m => {
      const b = document.createElement("button");
      b.textContent = m.label;
      b.dataset.model = m.key;
      b.setAttribute("aria-pressed", String(m.key === (current || MODELS[0].key)));
      b.onclick = () => show(m.key);
      host.appendChild(b);
    });
  }

  function show(key) {
    const model = MODELS.find(m => m.key === key);
    if (!model) return;
    current = key;

    const host = $("model");
    if (host) [...host.children].forEach(c =>
      c.setAttribute("aria-pressed", String(c.dataset.model === key)));

    MODELS.forEach(m => {
      const view = $(m.viewId);
      if (view) view.hidden = m.key !== key;
    });

    const sub = $("model-sub");
    if (sub && model.sub) sub.textContent = model.sub;

    if (!model._inited) {
      model._inited = true;
      if (typeof model.init === "function") model.init();
    } else if (typeof model.refresh === "function") {
      model.refresh();
    }
  }

  function mount() {
    if (mounted || !MODELS.length) return;
    mounted = true;
    build();
    show(MODELS[0].key);
  }

  return { register, mount, show, models: MODELS };
})();

if (document.readyState === "loading")
  document.addEventListener("DOMContentLoaded", () => ModelBar.mount());
else ModelBar.mount();
