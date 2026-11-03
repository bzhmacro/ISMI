/* country_bar.js — one country picker, the same on every model page.

   Each model app still builds its own gauge/scope segment (b-gauge, backbone,
   d-scope, t-scope) exactly as before, with one button per data key. That
   segment is now hidden; this file mirrors it as a row of flags, one per
   country, plus a second row of variants when a country has more than one
   (US CPI vs PCE, Canada total/goods/services, Australia quarterly vs monthly).

   Picking a flag or a variant just clicks the matching hidden button, so the
   apps' own selection logic runs unchanged. A MutationObserver re-syncs the bar
   whenever the app rebuilds its segment or moves the pressed state.

   Each hidden button must carry `data-key` (the data key it selects). */
"use strict";

const CountryBar = (() => {
  // The same twelve countries, in the same order, on every page. A country
  // with no data on a page is still shown, greyed out and disabled.
  const COUNTRIES = [
    ["us", "US"], ["ca", "Canada"], ["gb", "UK"], ["fr", "France"],
    ["de", "Germany"], ["it", "Italy"], ["es", "Spain"], ["no", "Norway"],
    ["se", "Sweden"], ["jp", "Japan"], ["au", "Australia"], ["nz", "NZ"],
  ];

  // Data key -> [country, variant label]. Keys not listed map to themselves
  // (uk -> gb) with no variant label.
  const KEYS = {
    cpi: ["us", "CPI"], pce: ["us", "PCE"],
    cpi45: ["us", "CPI · Cleveland cut"], cpi70: ["us", "CPI · 70 strata"],
    headline: ["us", "Headline"], core: ["us", "Core"],
    goods: ["us", "Goods"], services: ["us", "Services"],
    ca_goods: ["ca", "Goods"], ca_services: ["ca", "Services"],
    au_m: ["au", "Monthly"], uk: ["gb", null],
  };
  // Variant label for a key that is its country's base series, used only when
  // the country has several variants on that page.
  const BASE = { ca: "Total", au: "Quarterly" };

  const resolve = key => {
    const k = KEYS[key];
    if (k) return k;
    return [key, null];
  };

  function attach(segId, barId) {
    const seg = document.getElementById(segId);
    const bar = document.getElementById(barId);
    if (!seg || !bar) return;
    bar.classList.add("countrybar");
    const flags = document.createElement("div");
    flags.className = "cb-flags";
    const variants = document.createElement("div");
    variants.className = "seg cb-variants";
    bar.append(flags, variants);

    let busy = false;
    function sync() {
      if (busy) return;
      busy = true;
      try { draw(); } finally { busy = false; }
    }

    function draw() {
      const btns = [...seg.querySelectorAll("button[data-key]")];
      const byCountry = new Map();
      btns.forEach(b => {
        const [c, v] = resolve(b.dataset.key);
        if (!byCountry.has(c)) byCountry.set(c, []);
        byCountry.get(c).push({ btn: b, key: b.dataset.key, variant: v });
      });
      const pressed = btns.find(b => b.getAttribute("aria-pressed") === "true");
      const cur = pressed ? resolve(pressed.dataset.key)[0] : null;

      flags.innerHTML = "";
      COUNTRIES.forEach(([code, name]) => {
        const opts = byCountry.get(code);
        const b = document.createElement("button");
        b.type = "button";
        b.className = "cb-flag";
        b.innerHTML = `<span class="cb-name">${name}</span>` +
          `<img src="assets/flags/${code}.svg" alt="" width="24" height="18" loading="lazy">`;
        if (!opts) {
          b.disabled = true;
          b.classList.add("na");
          b.title = "No data for this country on this page";
          b.setAttribute("aria-pressed", "false");
          flags.appendChild(b);
          return;
        }
        b.setAttribute("aria-pressed", String(code === cur));
        // Japan/Germany/... on the supply-demand page are flagged "caution".
        if (opts.every(o => o.btn.classList.contains("caution"))) {
          b.classList.add("caution");
          b.title = opts[0].btn.title || "";
        }
        b.onclick = () => {
          if (code === cur) return;
          opts[0].btn.click();
        };
        flags.appendChild(b);
      });

      variants.innerHTML = "";
      const curOpts = cur ? byCountry.get(cur) : null;
      variants.hidden = !curOpts || curOpts.length < 2;
      if (!variants.hidden) {
        curOpts.forEach(o => {
          const b = document.createElement("button");
          b.type = "button";
          b.textContent = o.variant || BASE[cur] || o.btn.textContent;
          b.setAttribute("aria-pressed", o.btn.getAttribute("aria-pressed"));
          if (o.btn.title) b.title = o.btn.title;
          if (o.btn.classList.contains("caution")) b.classList.add("caution");
          b.onclick = () => { if (b.getAttribute("aria-pressed") !== "true") o.btn.click(); };
          variants.appendChild(b);
        });
      }
    }

    new MutationObserver(sync).observe(seg, {
      childList: true, subtree: true, attributes: true, attributeFilter: ["aria-pressed"],
    });
    sync();
  }

  /* Settings panels: one button per view opens the panel of levers below the
     country row. Open/closed is remembered per view (a per-viewer convenience;
     storage can throw, so every access is guarded). */
  function drawers() {
    document.querySelectorAll(".settings-toggle").forEach(btn => {
      const panel = document.getElementById(btn.getAttribute("aria-controls"));
      if (!panel) return;
      const k = "ismi.settings." + panel.id;
      const set = open => {
        panel.hidden = !open;
        btn.setAttribute("aria-expanded", String(open));
      };
      try { set(localStorage.getItem(k) === "1"); } catch (e) { set(false); }
      btn.addEventListener("click", () => {
        const open = panel.hidden;
        set(open);
        try { localStorage.setItem(k, open ? "1" : "0"); } catch (e) {}
        // Range sliders inside a hidden panel measure 0 wide; and a scrollbar
        // appearing can change the chart width — let everything re-measure.
        window.dispatchEvent(new Event("resize"));
      });
    });
  }

  function mount() {
    attach("b-gauge", "b-country");
    attach("backbone", "ism-country");
    attach("d-scope", "d-country");
    attach("t-scope", "t-country");
    drawers();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();

  return { attach };
})();
