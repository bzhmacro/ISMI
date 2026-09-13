/* api/refresh.js — dispatch the data-refresh GitHub Action from the website.
 *
 * The site is static: the browser cannot run the Python exporters, so the
 * "Refresh" button asks this function to fire `.github/workflows/refresh-data.yml`
 * via workflow_dispatch. The Action rebuilds web/data/*.json, commits, and
 * Vercel redeploys — so the page updates a few minutes later on its own.
 *
 * GET  /api/refresh  -> status: what is due, whether a run is in flight, cooldown
 * POST /api/refresh  -> dispatch, if and only if the gate below allows it
 *
 * THE GATE (why there is no password)
 * -----------------------------------
 * This endpoint is public, so it has to be safe to press by anyone who finds
 * it. Two conditions, both evaluated server-side — the client is never trusted:
 *
 *   1. CALENDAR. A refresh is allowed only when a gauge is genuinely behind its
 *      published release date, computed from data/release_calendar.json (which
 *      carries precomputed UTC availability instants). When nothing has
 *      published since the last build, the button does nothing at all — so
 *      spamming it cannot burn Action minutes or provider API quota.
 *   2. COOLDOWN. Refuse while a run is queued or in progress, and for
 *      COOLDOWN_MINUTES after the last one finished. Derived from the GitHub
 *      runs API rather than a KV store, so there is no state to keep and the
 *      answer is correct even across cold starts and multiple regions.
 *
 * The worst a determined stranger can do is cause one rebuild per release per
 * cooldown window — which is exactly what the scheduled job would have done
 * anyway, only sooner.
 *
 * ENVIRONMENT (set these in Vercel → Project → Settings → Environment Variables)
 *   GITHUB_TOKEN   required. Fine-grained PAT scoped to THIS repo only, with
 *                  Actions: Read and write. Nothing else. Server-side only —
 *                  it must never be exposed to the browser, so do not prefix it
 *                  with NEXT_PUBLIC_ or VITE_.
 *   GITHUB_REPO    optional, default "bzhmacro/ISMI"
 *   GITHUB_REF     optional, default "main"
 *   COOLDOWN_MIN   optional, default 20
 *   REFRESH_TOKEN  optional. Enables FORCE (below). Leave unset to disable it.
 *
 * FORCE
 * -----
 * The calendar gate is what makes an unauthenticated endpoint safe, so force
 * cannot be unauthenticated too. POST { force:true, token, gauges? } with a
 * token matching REFRESH_TOKEN skips the "is anything due" test and the
 * cooldown — for an off-calendar revision, an annual update, or simply knowing
 * the print is out before the calendar says so.
 *
 * It does NOT skip the in-flight check: two concurrent runs would race to
 * commit the same 27 MB of JSON, and one would lose. That check is about
 * correctness, not abuse, so force has no business overriding it.
 */

const WORKFLOW = "refresh-data.yml";
const DEFAULT_REPO = "bzhmacro/ISMI";
const DEFAULT_REF = "main";
const DEFAULT_COOLDOWN_MIN = 20;

const gh = (token) => ({
  Accept: "application/vnd.github+json",
  Authorization: `Bearer ${token}`,
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "ismi-refresh-button",
});

/* Newest reference period whose data should be fetchable by `now`, and whether
   the gauge's committed vintage is behind it. Mirrors
   ism.release_calendar.Status.due exactly — keep the two in step. */
function evaluateGauge(g, now) {
  let expected = null;
  let expectedRelease = null;
  for (const r of g.releases) {
    if (new Date(r.availableUtc) <= now && (!expected || r.ref > expected)) {
      expected = r.ref;
      expectedRelease = r;
    }
  }
  const committed = g.committed || null;
  const due = Boolean(expected && g.ci && (!committed || committed < expected));
  return { name: g.name, label: g.label, ci: g.ci, committed, expected, due,
           release: expectedRelease };
}

async function readCalendar(req) {
  const proto = (req.headers["x-forwarded-proto"] || "https").split(",")[0];
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  const res = await fetch(`${proto}://${host}/data/release_calendar.json`, {
    headers: { "Cache-Control": "no-cache" },
  });
  if (!res.ok) throw new Error(`release_calendar.json ${res.status}`);
  return res.json();
}

/* Cooldown state straight from the GitHub runs API — no KV, no cron drift. */
async function runState(repo, token, cooldownMin) {
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW}/runs?per_page=5`;
  const res = await fetch(url, { headers: gh(token) });
  if (!res.ok) {
    return { known: false, reason: `runs API ${res.status}` };
  }
  const { workflow_runs: runs = [] } = await res.json();
  const active = runs.find((r) => r.status === "queued" || r.status === "in_progress");
  if (active) {
    return { known: true, active: true, run: { id: active.id, url: active.html_url,
             status: active.status, startedAt: active.run_started_at } };
  }
  const last = runs[0];
  if (last) {
    const finished = new Date(last.updated_at);
    const waitMs = cooldownMin * 60000 - (Date.now() - finished.getTime());
    if (waitMs > 0) {
      return { known: true, active: false, cooldownMsRemaining: waitMs,
               run: { id: last.id, url: last.html_url, status: last.conclusion,
                      finishedAt: last.updated_at } };
    }
    return { known: true, active: false, cooldownMsRemaining: 0,
             run: { id: last.id, url: last.html_url, status: last.conclusion,
                    finishedAt: last.updated_at } };
  }
  return { known: true, active: false, cooldownMsRemaining: 0, run: null };
}

/* CommonJS on purpose. Vercel's zero-config Node runtime treats api/*.js as
 * CommonJS unless the project carries a package.json with "type": "module",
 * and adding one to a zero-build static site risks tripping framework
 * detection. `fetch` is global on Node 18+, which Vercel uses, so this needs
 * no dependencies and no package.json at all. */
module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "GET" && req.method !== "POST") {
    res.setHeader("Allow", "GET, POST");
    return res.status(405).json({ error: "method not allowed" });
  }

  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || DEFAULT_REPO;
  const ref = process.env.GITHUB_REF || DEFAULT_REF;
  const cooldownMin = Number(process.env.COOLDOWN_MIN || DEFAULT_COOLDOWN_MIN);

  let calendar;
  try {
    calendar = await readCalendar(req);
  } catch (e) {
    return res.status(503).json({ error: "calendar unavailable", detail: String(e) });
  }

  const now = new Date();
  const gauges = calendar.gauges.map((g) => evaluateGauge(g, now));
  const due = gauges.filter((g) => g.due).map((g) => g.name);
  const localBehind = gauges.filter((g) => !g.ci && g.expected &&
                                   (!g.committed || g.committed < g.expected))
                            .map((g) => g.name);

  // Without a token the button still reports freshness accurately; it just
  // cannot dispatch. That is the right degraded mode for a fork or a preview
  // deployment, and it keeps the panel useful before the PAT is configured.
  const configured = Boolean(token);
  const state = configured
    ? await runState(repo, token, cooldownMin)
    : { known: false, reason: "GITHUB_TOKEN not set" };

  const status = {
    generatedUtc: calendar.generated_utc,
    calendarVerified: calendar.calendar_verified || null,
    now: now.toISOString(),
    gauges,
    due,
    localBehind,          // e.g. Canada: behind, but refreshed by hand
    notes: calendar.notes || [],
    configured,
    forceAvailable: Boolean(process.env.REFRESH_TOKEN),
    run: state.run || null,
    active: Boolean(state.active),
    cooldownMsRemaining: state.cooldownMsRemaining || 0,
  };

  if (req.method === "GET") return res.status(200).json(status);

  /* ---------------------------- POST: dispatch --------------------------- */
  if (!configured) {
    return res.status(501).json({ ...status, error: "refresh not configured",
      detail: "Set GITHUB_TOKEN in the Vercel project environment." });
  }

  // Vercel parses JSON bodies, but be tolerant of a raw string body.
  let body = req.body || {};
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = {}; } }
  const wantForce = Boolean(body.force);
  const secret = process.env.REFRESH_TOKEN;
  const supplied = body.token || req.headers["x-refresh-token"] || "";

  let forced = false;
  if (wantForce) {
    if (!secret) {
      return res.status(501).json({ ...status, error: "force not configured",
        detail: "Set REFRESH_TOKEN in the Vercel project environment to enable force." });
    }
    if (!timingSafeEqual(String(supplied), secret)) {
      return res.status(403).json({ ...status, error: "bad token",
        detail: "Force requires the shared token." });
    }
    forced = true;
  }

  // A forced run may name its own gauges; otherwise force everything the
  // calendar knows about that CI can fetch, since "force" usually means the
  // calendar is the thing that is wrong.
  const requested = forced && body.gauges
    ? String(body.gauges).split(/\s+/).filter(Boolean)
    : null;
  const known = new Set(calendar.gauges.filter((g) => g.ci).map((g) => g.name));
  const bad = requested ? requested.filter((g) => !known.has(g)) : [];
  if (bad.length) {
    return res.status(400).json({ ...status, error: "unknown gauge",
      detail: `Not in the calendar, or not CI-refreshable: ${bad.join(", ")}.` });
  }
  const target = requested || (forced ? [...known] : due);

  if (!forced && !due.length) {
    return res.status(409).json({ ...status, error: "nothing due",
      detail: "Every CI gauge already holds the newest published vintage." });
  }
  // In-flight is checked even when forced: concurrent runs would race on the
  // same commit.
  if (state.active) {
    return res.status(409).json({ ...status, error: "already running",
      detail: "A refresh is in progress." });
  }
  if (!forced && state.cooldownMsRemaining > 0) {
    return res.status(429).json({ ...status, error: "cooling down",
      detail: `Try again in ${Math.ceil(state.cooldownMsRemaining / 60000)} min.` });
  }
  // Fail CLOSED. If the runs API did not answer we cannot tell whether a
  // refresh is already in flight or how recently one finished, so the cooldown
  // is unenforceable — and an endpoint that dispatches freely whenever GitHub
  // is having a bad minute is exactly the hole the gate exists to close.
  if (!state.known) {
    return res.status(503).json({ ...status, error: "cannot verify run state",
      detail: `Refusing to dispatch without cooldown state (${state.reason}).` });
  }

  const dispatch = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: { ...gh(token), "Content-Type": "application/json" },
      // Normally the gauges the calendar says are behind; when forced, the
      // explicit list. The workflow revalidates the names against the calendar
      // before fetching, so a bad value here cannot rebuild anything
      // unexpected.
      body: JSON.stringify({ ref, inputs: { gauges: target.join(" ") } }),
    },
  );

  if (!dispatch.ok) {
    const detail = await dispatch.text();
    // Never echo the token or the raw Authorization header back to the client.
    return res.status(502).json({ ...status, error: "dispatch failed",
      detail: detail.slice(0, 400) });
  }

  return res.status(202).json({ ...status, dispatched: target, forced,
    detail: `${forced ? "Forcing" : "Refreshing"} ${target.join(", ")}. ` +
            `The site updates automatically when the run finishes.` });
};

/* Constant-time-ish compare so a wrong token cannot be recovered by timing the
   response. Node's crypto.timingSafeEqual needs equal lengths, hence the
   length check first and the fixed-length loop after. */
function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
