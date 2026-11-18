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
  // The same thirteen countries, in the same order, on every page. A country
  // with no data on a page is still shown, greyed out and disabled. The euro
  // area sits just before its four largest members.
  const COUNTRIES = [
    ["us", "US"], ["ca", "Canada"], ["gb", "UK"], ["ea", "Euro area"], ["fr", "France"],
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

  /* ONE COUNTRY ACROSS PAGES. The reader's last explicit pick (flag, and the
     variant label within it, e.g. US · PCE) is kept here and re-applied to
     every page's bar: on a page that has that country it is selected (same
     variant when the page has it, else the country's first); on a page that
     does not (UK on Supply vs Demand), its flag stays highlighted and the view
     says there is no data for it instead of silently showing another
     country. In memory only: a reload starts from each page's default. */
  const PICK = { country: null, variant: null };
  const BARS = [];
  const syncAll = () => BARS.forEach(f => f());

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

    const view = bar.closest(".model-view");
    let busy = false;
    function sync() {
      if (busy) return;
      busy = true;
      try { draw(); } finally { busy = false; }
    }
    BARS.push(sync);

    /* "No data for <country> on this page" state, toggled on the view. */
    function noData(code, name) {
      if (!view) return;
      let msg = view.querySelector(":scope .cb-nodata-msg");
      if (!code) {
        view.classList.remove("cb-nodata");
        if (msg) msg.hidden = true;
        return;
      }
      if (!msg) {
        msg = document.createElement("div");
        msg.className = "cb-nodata-msg";
        const anchor = bar.closest(".viewbar") || bar;
        anchor.after(msg);
      }
      const page = (document.querySelector(".snav-link.active") || {}).textContent || "this page";
      msg.textContent = `No ${page.trim()} data for ${name === "UK" || name === "US" || name === "NZ" ? "the " + name : name}` +
        " — pick another country above.";
      msg.hidden = false;
      view.classList.add("cb-nodata");
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
      let cur = pressed ? resolve(pressed.dataset.key)[0] : null;

      // Carry the reader's pick over from another page.
      if (PICK.country && btns.length) {
        const opts = byCountry.get(PICK.country);
        if (opts) {
          // Same variant where this page has it; otherwise the country's
          // first series — but only switch for that when the country itself
          // differs, so a variant the reader chose here is left alone.
          const exact = opts.find(o => (o.variant || BASE[PICK.country] || null) === PICK.variant);
          const want = exact || opts[0];
          if (pressed !== want.btn && (cur !== PICK.country || exact)) {
            want.btn.click();             // the app's own selection logic runs
            return;                       // its re-render re-syncs this bar
          }
          noData(null);
        } else {
          cur = PICK.country;             // highlight it, greyed, below
          const nm = (COUNTRIES.find(c => c[0] === PICK.country) || [])[1] || PICK.country;
          noData(PICK.country, nm);
        }
      } else noData(null);

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
          b.setAttribute("aria-pressed", String(code === cur));
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
          if (code === cur && view && !view.classList.contains("cb-nodata")) return;
          PICK.country = code;
          const o = opts.find(x => (x.variant || BASE[code] || null) === PICK.variant) || opts[0];
          PICK.variant = o.variant || BASE[code] || null;
          noData(null);
          o.btn.click();
          syncAll();
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
          b.onclick = () => {
            PICK.country = cur;
            PICK.variant = o.variant || BASE[cur] || null;
            if (b.getAttribute("aria-pressed") !== "true") o.btn.click();
          };
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
    // A page shown for the first time builds its segment then; re-apply the
    // pick whenever a page is shown.
    document.addEventListener("modelshown", () => setTimeout(syncAll, 0));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();

  return { attach };
})();
