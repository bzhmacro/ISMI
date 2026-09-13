/* refresh.js — per-gauge freshness panel + on-demand refresh button.
 *
 * Renders under the "Data through …" line: one row per gauge showing the
 * vintage the page is currently serving, the newest vintage that should be
 * public, and the next release date. When something has published that the
 * site has not picked up yet, the button enables and names it; otherwise it
 * greys out.
 *
 * Pressing it POSTs to /api/refresh, which dispatches the GitHub Action (see
 * api/refresh.js for the gate). The rebuild takes a few minutes and ends with a
 * commit, which triggers a Vercel redeploy — so the panel polls, and when the
 * deployed data file finally carries a newer build than the one this tab
 * loaded, it offers a reload.
 *
 * Degrades cleanly: with no /api/refresh (plain static hosting, file://, a fork
 * without the token) the panel still renders freshness from
 * data/release_calendar.json and simply shows no button. The calendar is the
 * only hard dependency, and if that is missing the panel hides itself entirely
 * rather than showing a broken control. */

(() => {
  "use strict";

  const POLL_MS = 20000;          // while a run is in flight
  const CAL_URL = "data/release_calendar.json";
  const API_URL = "api/refresh";

  let CAL = null;       // release_calendar.json
  let STATUS = null;    // last /api/refresh payload (null if no backend)
  let POLL = null;
  let LOADED_BUILD = null;   // meta.generated_utc of the ism.json this tab has

  /* ----------------------------- utilities ----------------------------- */

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

  const fmtDate = (iso) => {
    const d = new Date(iso + (iso.length === 10 ? "T00:00:00Z" : ""));
    return d.toLocaleDateString(undefined,
      { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
  };

  const relative = (iso) => {
    const days = Math.round((new Date(iso) - Date.now()) / 86400000);
    if (days === 0) return "today";
    if (days === 1) return "tomorrow";
    if (days === -1) return "yesterday";
    return days > 0 ? `in ${days}d` : `${-days}d ago`;
  };

  /* Newest reference period already fetchable, per gauge.
     Mirrors ism.release_calendar and api/refresh.js — three copies of one rule,
     so any change has to be made in all three. The JSON ships precomputed UTC
     instants precisely so this stays a date comparison and never a timezone
     calculation. */
  function evaluate(g, now) {
    let expected = null, release = null;
    for (const r of g.releases) {
      if (new Date(r.availableUtc) <= now && (!expected || r.ref > expected)) {
        expected = r.ref; release = r;
      }
    }
    let next = null;
    for (const r of g.releases) {
      if (new Date(r.availableUtc) > now && (!next || r.ref < next.ref)) next = r;
    }
    const behind = Boolean(expected && (!g.committed || g.committed < expected));
    return { ...g, expected, release, next, behind, due: behind && g.ci };
  }

  /* -------------------------------- styles ------------------------------- */

  function injectStyles() {
    if (document.getElementById("refresh-styles")) return;
    const s = el("style");
    s.id = "refresh-styles";
    s.textContent = `
      .freshbar { margin:-2px 0 14px; font-size:13px; }
      .freshbar summary { cursor:pointer; list-style:none; display:flex;
        align-items:center; gap:10px; flex-wrap:wrap; }
      .freshbar summary::-webkit-details-marker { display:none; }
      .freshbar .chev { color:#8b98a5; font-size:11px; transition:transform .15s; }
      .freshbar[open] .chev { transform:rotate(90deg); }
      .freshbar .pill { padding:2px 8px; border-radius:999px; font-weight:600;
        font-size:11.5px; letter-spacing:.02em; }
      .freshbar .pill.ok   { background:#16301f; color:#6ee7a8; }
      .freshbar .pill.due  { background:#3a2a10; color:#f5a623; }
      .freshbar .pill.run  { background:#132b3d; color:#4c9aff; }
      .freshbar button.refresh { font:inherit; font-weight:600; padding:4px 12px;
        border-radius:6px; border:1px solid #2c3a48; background:#1d2732;
        color:#e6edf3; cursor:pointer; }
      .freshbar button.refresh:hover:not(:disabled) { border-color:#4c9aff; }
      .freshbar button.refresh:disabled { opacity:.45; cursor:default; }
      .freshbar table { border-collapse:collapse; margin:10px 0 0; width:100%;
        max-width:760px; }
      .freshbar th, .freshbar td { text-align:left; padding:3px 14px 3px 0;
        border-bottom:1px solid #1e2833; white-space:nowrap; }
      .freshbar th { color:#8b98a5; font-weight:600; font-size:11.5px;
        text-transform:uppercase; letter-spacing:.04em; }
      .freshbar td.behind { color:#f5a623; }
      .freshbar td.muted, .freshbar .muted { color:#8b98a5; }
      .freshbar .est { color:#6b7784; font-style:italic; }
      .freshbar .msg { margin-top:8px; }
      .freshbar .msg.err { color:#f0958a; }
      .freshbar .msg.ok  { color:#6ee7a8; }
      .freshbar .note { margin-top:8px; color:#c8b384; max-width:760px;
        white-space:normal; line-height:1.45; }
    `;
    document.head.appendChild(s);
  }

  /* -------------------------------- render ------------------------------- */

  function render() {
    if (!CAL) return;
    const host = document.getElementById("freshbar");
    if (!host) return;
    const now = new Date();
    const gauges = CAL.gauges.map((g) => evaluate(g, now));
    const due = gauges.filter((g) => g.due);
    const localBehind = gauges.filter((g) => g.behind && !g.ci);
    const active = STATUS && STATUS.active;
    const wasOpen = host.hasAttribute("open");

    host.innerHTML = "";

    /* ---- summary line ---- */
    const sum = el("summary");
    sum.appendChild(el("span", "chev", "▶"));

    if (active) {
      sum.appendChild(el("span", "pill run", "REFRESHING"));
    } else if (due.length) {
      sum.appendChild(el("span", "pill due", `${due.length} BEHIND`));
    } else {
      sum.appendChild(el("span", "pill ok", "ALL CURRENT"));
    }

    const headline = due.length
      ? `${due.map((g) => `${g.label.split(" (")[0]} ${g.expected}`).join(", ")} available`
      : "every gauge holds the newest published vintage";
    sum.appendChild(el("span", "muted", headline));

    /* ---- the button ---- */
    if (STATUS && STATUS.configured) {
      const btn = el("button", "refresh");
      btn.type = "button";
      const cooling = STATUS.cooldownMsRemaining > 0;
      if (active) {
        btn.textContent = "Refreshing…";
        btn.disabled = true;
      } else if (!due.length) {
        btn.textContent = "Up to date";
        btn.disabled = true;
      } else if (cooling) {
        btn.textContent = `Wait ${Math.ceil(STATUS.cooldownMsRemaining / 60000)} min`;
        btn.disabled = true;
        btn.title = "A refresh ran very recently.";
      } else {
        btn.textContent = `Refresh ${due.map((g) => g.name).join(", ")}`;
        btn.disabled = false;
        btn.addEventListener("click", (e) => { e.preventDefault(); dispatch(btn); });
      }
      sum.appendChild(btn);

      /* Force: for a print you know is out before the calendar agrees, an
         off-schedule revision, or an annual update. Needs the shared token,
         because the calendar gate is what makes the plain button safe to leave
         unauthenticated. Hidden entirely unless the server has REFRESH_TOKEN
         set, so a stock deployment shows no dead control. */
      // Only on an activated device, so ordinary visitors never see a control
      // they cannot use.
      if (STATUS.forceAvailable && readToken() && !active) {
        const f = el("button", "refresh");
        f.type = "button";
        f.textContent = "Force";
        f.title = "Rebuild now regardless of the release calendar (requires the token)";
        f.addEventListener("click", (e) => { e.preventDefault(); forceRefresh(f); });
        sum.appendChild(f);
      }
    }
    host.appendChild(sum);

    /* ---- the table ---- */
    const table = el("table");
    const thead = el("thead");
    const hr = el("tr");
    ["gauge", "loaded", "available", "next release", ""].forEach((h) =>
      hr.appendChild(el("th", null, h)));
    thead.appendChild(hr);
    table.appendChild(thead);

    const tb = el("tbody");
    for (const g of gauges) {
      const tr = el("tr");
      tr.appendChild(el("td", null, g.label.split(" (")[0]));
      tr.appendChild(el("td", g.behind ? "behind" : null, g.committed || "—"));
      tr.appendChild(el("td", g.behind ? "behind" : "muted", g.expected || "—"));

      const next = el("td", "muted");
      if (g.next) {
        next.textContent = `${fmtDate(g.next.date)} (${relative(g.next.date)})`;
        if (!g.next.published) {
          next.appendChild(document.createTextNode(" "));
          const est = el("span", "est", "est");
          est.title = "Beyond the agency's published calendar — conservative estimate.";
          next.appendChild(est);
        }
      } else next.textContent = "—";
      tr.appendChild(next);

      const how = el("td", "muted");
      if (!g.ci) {
        how.textContent = g.behind ? "local — run by hand" : "local";
        if (g.manualCommand) how.title = g.manualCommand;
      }
      tr.appendChild(how);
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    host.appendChild(table);

    if (localBehind.length) {
      const n = el("div", "msg muted",
        `${localBehind.map((g) => g.label.split(" (")[0]).join(", ")} cannot be ` +
        `refreshed from the browser — the source is unreachable from CI, so it is ` +
        `rebuilt locally.`);
      host.appendChild(n);
    }

    /* Methodology events worth seeing before trusting a fresh print. */
    const soon = (CAL.notes || []).filter((n) => {
      const m = /\b(20\d\d-\d\d-\d\d)\b/.exec(n.note);
      if (!m) return false;
      const days = (new Date(m[1] + "T00:00:00Z") - now) / 86400000;
      return days > -45 && days < 45;
    });
    for (const n of soon) {
      host.appendChild(el("div", "note", `⚠ ${n.note.replace(/\s+/g, " ").trim()}`));
    }

    const msg = el("div", "msg");
    msg.id = "refresh-msg";
    host.appendChild(msg);

    if (wasOpen || due.length || active) host.setAttribute("open", "");
  }

  function say(text, kind) {
    const m = document.getElementById("refresh-msg");
    if (!m) return;
    m.textContent = text || "";
    m.className = "msg" + (kind ? " " + kind : "");
  }

  /* ------------------------------- actions ------------------------------- */

  async function dispatch(btn) {
    btn.disabled = true;
    say("Dispatching…");
    try {
      const res = await fetch(API_URL, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      STATUS = body && body.gauges ? body : STATUS;
      if (res.ok || res.status === 202) {
        say(body.detail || "Refresh started.", "ok");
        startPolling();
      } else {
        say(body.detail || body.error || `Refresh failed (${res.status}).`, "err");
      }
    } catch (e) {
      say(`Could not reach the refresh endpoint. ${e}`, "err");
    }
    render();
  }

  const TOKEN_KEY = "bzh.refreshToken";

  /* The token is a convenience credential for one operator, not an identity —
     it only permits "rebuild the public data now", which the schedule would do
     anyway. Kept in localStorage so it is not retyped on every print; wrapped
     because storage throws in some privacy modes. */
  const readToken = () => {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
  };
  const saveToken = (t) => {
    try { localStorage.setItem(TOKEN_KEY, t); } catch { /* non-persistent */ }
  };

  /* One-time device activation: open the site once as
       https://…/?key=YOUR_REFRESH_TOKEN
     and the token is stored and stripped from the URL. From then on Force is
     an ordinary button on that device — no prompt, ever. Bookmark the plain
     URL, not the ?key= one.

     The key is removed from the address bar immediately so it does not linger
     in history, in a screenshot, or in the Referer header of the next request. */
  function captureKeyFromUrl() {
    const m = /[?&]key=([^&]*)/.exec(location.search);
    if (!m) return;
    const token = decodeURIComponent(m[1] || "").trim();
    if (token) saveToken(token);
    const url = new URL(location.href);
    url.searchParams.delete("key");
    history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  async function forceRefresh(btn) {
    const token = readToken();
    if (!token) {
      say("This device is not activated. Open the site once with " +
          "?key=YOUR_TOKEN appended to the address, then Force works here " +
          "permanently.", "err");
      return;
    }
    btn.disabled = true;
    say("Forcing a rebuild…");
    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true, token }),
      });
      const body = await res.json().catch(() => ({}));
      if (body && body.gauges) STATUS = body;
      if (res.ok || res.status === 202) {
        saveToken(token);
        say(body.detail || "Forced refresh started.", "ok");
        startPolling();
      } else {
        // A rejected token must not stay cached, or every later attempt fails
        // silently with no way to correct it from the UI.
        if (res.status === 403) { saveToken(""); }
        say(body.detail || body.error || `Force failed (${res.status}).`, "err");
      }
    } catch (e) {
      say(`Could not reach the refresh endpoint. ${e}`, "err");
    }
    btn.disabled = false;
    render();
  }

  async function loadStatus() {
    try {
      const res = await fetch(API_URL, { cache: "no-store" });
      if (!res.ok) { STATUS = null; return; }
      STATUS = await res.json();
    } catch {
      STATUS = null;          // no backend: panel stays informational
    }
  }

  /* A finished run commits new data, which redeploys the site. Detect that by
     watching the deployed calendar's build stamp rather than guessing from the
     Action's status — the data is only really live once Vercel has served it. */
  async function checkForNewBuild() {
    try {
      const res = await fetch(`${CAL_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) return false;
      const fresh = await res.json();
      if (LOADED_BUILD && fresh.generated_utc > LOADED_BUILD) {
        CAL = fresh;
        say("New data is live. Reload to see it.", "ok");
        const m = document.getElementById("refresh-msg");
        if (m) {
          const a = el("button", "refresh", "Reload");
          a.type = "button";
          a.style.marginLeft = "10px";
          a.addEventListener("click", () => location.reload());
          m.appendChild(a);
        }
        return true;
      }
      CAL = fresh;
    } catch { /* transient during redeploy */ }
    return false;
  }

  /* Keep polling for a while AFTER the Action reports success: the run ends
     with a commit, and the data is only actually live once Vercel has built and
     served the new deployment, which takes another minute or two. Stopping as
     soon as the run went inactive meant the panel never noticed the refresh it
     had just triggered. */
  const GRACE_POLLS = 15;               // ~5 min of polling past run completion
  let gracePolls = 0;

  function startPolling() {
    if (POLL) return;
    gracePolls = 0;
    POLL = setInterval(async () => {
      await loadStatus();
      const landed = await checkForNewBuild();
      const running = Boolean(STATUS && STATUS.active);
      if (running) gracePolls = 0; else gracePolls += 1;

      if (landed || gracePolls >= GRACE_POLLS) {
        clearInterval(POLL);
        POLL = null;
        if (!landed && gracePolls >= GRACE_POLLS) {
          const concluded = STATUS && STATUS.run && STATUS.run.status;
          say(concluded && concluded !== "success"
              ? `The refresh run finished as "${concluded}". Check the Action log.`
              : "Refresh finished, but no new data appeared — the sources may not "
                + "have published a new vintage yet.",
              concluded && concluded !== "success" ? "err" : null);
        }
      }
      render();
    }, POLL_MS);
  }

  /* --------------------------------- boot -------------------------------- */

  async function boot() {
    captureKeyFromUrl();          // before anything renders
    const anchor = document.getElementById("asof");
    if (!anchor) return;

    try {
      const res = await fetch(`${CAL_URL}?t=${Date.now()}`, { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      CAL = await res.json();
    } catch {
      // No calendar published yet (run scripts/export_release_calendar.py).
      // Show nothing rather than a broken control.
      return;
    }
    LOADED_BUILD = CAL.generated_utc;

    injectStyles();
    const host = el("details", "freshbar");
    host.id = "freshbar";
    anchor.insertAdjacentElement("afterend", host);

    await loadStatus();
    render();
    if (STATUS && STATUS.active) startPolling();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else boot();
})();
