# ISM interactive explorer (static site)

A zero-build static website to explore the Inflation Shock Momentum index under
different model parameters. No framework, no build step — just HTML + JS +
Plotly (from CDN) + one JSON file.

**The index is computed client-side.** `data/ism.json` ships the *raw* category
inflation and weight panels, and a Web Worker recomputes the full pipeline
(rolling AR(p) regressions → momentum runs → weighted shares) whenever a
control changes. That makes every parameter a live dial — window length,
run length, AR order, weighting scheme, ρ̂ cap, even the category set —
instead of a precomputed grid.

## Files

```
web/
├── index.html      # layout + controls
├── styles.css
├── app.js          # UI: loads data, drives the worker, plots, correlates
├── engine.js       # the ISM maths in JS — parity-tested port of src/ism/engine.py
├── worker.js       # Web Worker wrapper; caches residual panels per (gauge, AR, W)
├── data/ism.json   # raw panels + one precomputed baseline combo (instant first paint)
└── vercel.json
```

`engine.js` must stay in sync with the Python engine. The contract is enforced
by `tests/test_web_engine_parity.py`, which runs both implementations on the
same synthetic panel (including missing data and rank-deficient windows) and
asserts the residuals, momentum and index match. `tests/web_smoke.cjs` boots
the whole app headlessly (jsdom) and drives every control.

## Performance notes

- The worker assembles each window's normal equations from prefix sums of
  lagged cross-products, so a full AR(1) pass over 130 categories × ~800
  months is ~30 ms; the worst case (AR(12), W=240) is ~150 ms.
- Residual panels are cached per (gauge, AR order, W); changes to k, the
  scheme, the ρ̂ cap or the category set re-aggregate in ~5–10 ms.
- Rank-deficient windows (e.g. a price index flat for 10 straight years) are
  solved min-norm via a pseudo-inverse fallback, matching `numpy.lstsq`.

## Refresh the data

```bash
# from the repo root, with BEA/BLS data already cached (see ISM_replication.ipynb)
python scripts/export_web_data.py      # writes web/data/ism.json (schema v3)
```

This exports the raw panels for both gauges (PCE + CPI), the author overlay,
12-month headline inflation, and one precomputed baseline combo
(AR1 | k=3 | extensive) used for instant first paint. Commit the regenerated
`web/data/ism.json`.

Backward compatibility: if the app is served an old v2 `ism.json` (27
precomputed combos, no panels) or the worker cannot start, it degrades
gracefully to the precomputed combos and hides the live-only controls.

## Run locally

```bash
cd web
python -m http.server 8000      # then open http://localhost:8000
```
(Any static server works; opening index.html via file:// will fail the fetch
and Workers — serve it.)

## Deploy to Vercel

The site is fully static, so there is **no build command**.

**Option A — dashboard:** New Project → import the repo → set **Root Directory =
`web`**, **Framework Preset = Other**, leave the build command empty → Deploy.

**Option B — CLI:**
```bash
cd web
vercel            # accept defaults; it's detected as a static site
vercel --prod
```

## What the controls do

- **Price gauge** — PCE (BEA underlying detail, the paper's gauge) or CPI (BLS item strata).
- **Benchmark model** — AR(p) for the rolling residuals (Eq. 3), plus the
  **rolling window W** slider (60–240 months; paper baseline 120).
- **Run length k** — consecutive same-signed residuals that flag momentum
  (Eqs. 4-5); slider 2–8 (paper baseline 3).
- **Weighting** — `extensive` (sign only, the paper's baseline), `size`
  (× |Σ of the last k residuals|), `stickiness` (× 1/(1−ρ̂), with a live ρ̂-cap slider).
- **Categories** — untick categories (searchable list) to drop them; weights
  renormalise over the rest. Try filtering "gasoline" or "food".
- Toggles overlay the author series, the S⁺/S⁻ components, and 12-month headline
  inflation; the slider trims the sample start; the readout shows the live
  correlation with the authors' published index.

## Auto-refresh to the latest data (GitHub Action)

`.github/workflows/refresh-data.yml` rebuilds `web/data/*.json` from the latest
public data, commits, and pushes — which triggers an automatic Vercel redeploy.

It is **calendar-gated**, not monthly. It polls at 04:00, 10:00, 13:00 and 17:00
UTC and refreshes a gauge only when `config/release_calendar.yaml` says a newer
vintage should be public than the one committed. See the README at the repo root
for why (short version: the old cron on the 3rd of the month fetched data that
was already five weeks stale, because every gauge except US CPI publishes between
the 10th and the 25th).

**One-time setup:** in your GitHub repo → **Settings → Secrets and variables →
Actions → New repository secret**, add `FRED_API_KEY`, `BEA_API_KEY`,
`BLS_API_KEY`, `ESTAT_API_ID`, `DESTATIS_API_TOKEN`. The exporters are
self-fetching, so the Action needs no committed raw data.

## The freshness panel and the Refresh button

Under the "Data through …" line the page renders a panel (`refresh.js`) listing,
per gauge, the vintage currently loaded, the newest vintage that should be
public, and the next release date. When something has published that the site has
not picked up, the button enables and names it — so on a US CPI morning you can
have the new print without waiting for the 17:00 UTC poll.

How it fits together:

```
browser  ──POST /api/refresh──>  Vercel function  ──workflow_dispatch──>  Action
   ^                                                                        │
   └──────── polls data/release_calendar.json until the build stamp moves ───┘
```

`data/release_calendar.json` is generated by `scripts/export_release_calendar.py`
from the YAML. It ships **precomputed UTC availability instants** rather than
timezones, so neither the browser nor the serverless function ever has to convert
a local wall time in an arbitrary IANA zone — the bug class that made a 16:00 UTC
cron miss every US winter release. It also embeds the vintages present in the
committed data files, so the panel needs one small fetch instead of re-reading
27 MB of panels.

**One-time setup for the button** (optional — without it the panel still shows
freshness accurately, just with no button):

1. Create a GitHub **fine-grained** personal access token scoped to this
   repository only, with **Actions: Read and write**. Nothing else.
2. In Vercel → Project → Settings → Environment Variables add `GITHUB_TOKEN`.
   Do **not** prefix it with `NEXT_PUBLIC_` or any other client-exposed prefix —
   it is read server-side only. Optionally set `GITHUB_REPO` (default
   `bzhmacro/ISMI`), `GITHUB_REF` (default `main`) and `COOLDOWN_MIN`
   (default 20).
3. Confirm the Vercel project's **Root Directory** is `web`, so `web/api/` is
   deployed as a serverless function at `/api/refresh`.

**Why the endpoint is safe to leave public.** It takes no input from the client
and enforces two conditions server-side: a refresh is allowed only when a gauge
is genuinely behind its published release date, and only when no run is in
flight and none finished within the cooldown. If the GitHub runs API cannot be
reached it refuses rather than dispatching, so the cooldown is never
unenforceable. The worst outcome is one rebuild per release per cooldown
window — which the scheduled job would have done anyway, only later.

The gauge list sent to the workflow is the calendar's own due-set, and
`ism.release_calendar due --only` revalidates it against the calendar before
anything is fetched, so a malformed value cannot rebuild something unexpected.

Canada is shown in the panel but has no button: StatCan is unreachable from CI,
so it is rebuilt locally. Hovering its row shows the command.

To refresh by hand instead: `python scripts/export_web_data.py [gauges]`, then
`python scripts/export_release_calendar.py`, then commit `web/data/`.

## Charts

- **Main** — ISM (recomputed live) vs the author series, optional S⁺/S⁻ components
  and a 12-month headline-inflation overlay; sample-start slider; live correlation.
- **Last 22 ISM prints** — a bar chart of the most recent 22 monthly values
  (orange = positive pressure, blue = negative); click a bar to inspect that month.
- **Top drivers** — for the selected (or latest) month, the categories contributing
  most to the index (ωᵢ·(M⁺ᵢ−M⁻ᵢ), which sum exactly to the ISM), so you can see
  *what* is pushing it up or down.
