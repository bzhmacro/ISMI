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

  /* The bar is the house `.section-nav`. Because the four models are toggled
     views rather than four regions of one scrolling document, the links switch
     views instead of scrolling to anchors — but they keep real `href="#key"`
     so each model is deep-linkable and the browser's back button works. */
  function build() {
    const host = $("model");
    if (!host) return;
    host.innerHTML = "";
    MODELS.forEach(m => {
      const a = document.createElement("a");
      a.className = "snav-link";
      a.textContent = m.label;
      a.href = `#${m.key}`;
      a.dataset.model = m.key;
      if (m.key === (current || MODELS[0].key)) a.classList.add("active");
      a.addEventListener("click", e => { e.preventDefault(); show(m.key, true); });
      host.appendChild(a);
    });
  }

  function show(key, pushHash) {
    const model = MODELS.find(m => m.key === key);
    if (!model) return;
    current = key;

    const host = $("model");
    if (host) [...host.children].forEach(c =>
      c.classList.toggle("active", c.dataset.model === key));

    MODELS.forEach(m => {
      const view = $(m.viewId);
      if (view) view.hidden = m.key !== key;
    });

    const sub = $("model-sub");
    if (sub && model.sub) sub.textContent = model.sub;

    if (pushHash && location.hash.slice(1) !== key) {
      history.replaceState(null, "", `#${key}`);
    }

    if (!model._inited) {
      model._inited = true;
      if (typeof model.init === "function") model.init();
    } else if (typeof model.refresh === "function") {
      model.refresh();
    }

    /* chart_export.js attaches its toolbar to whichever charts exist; views are
       built lazily, so tell it a new one just appeared. */
    document.dispatchEvent(new CustomEvent("modelshown", { detail: { key } }));
  }

  function mount() {
    if (mounted || !MODELS.length) return;
    mounted = true;
    build();
    // Honour a deep link (#trim) on first load, else the first model.
    const wanted = decodeURIComponent(location.hash.slice(1));
    show(MODELS.some(m => m.key === wanted) ? wanted : MODELS[0].key);
    window.addEventListener("hashchange", () => {
      const k = decodeURIComponent(location.hash.slice(1));
      if (k && k !== current && MODELS.some(m => m.key === k)) show(k);
    });
  }

  return { register, mount, show, models: MODELS };
})();

if (document.readyState === "loading")
  document.addEventListener("DOMContentLoaded", () => ModelBar.mount());
else ModelBar.mount();
