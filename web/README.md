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
├── index.html        # layout + controls for all four models
├── styles.css
├── models.js         # the Model bar: a registry, show/hide, lazy first init
├── app.js            # model 1 — Inflation Shock Momentum
├── engine.js         # the ISM maths in JS — parity-tested port of src/ism/engine.py
├── worker.js         # Web Worker wrapper; caches residual panels per (gauge, AR, W)
├── decomp_app.js     # model 2 — Supply vs Demand
├── decomp_engine.js / decomp_worker.js
├── trim_app.js       # model 3 — Trimmed mean & median
├── trim_engine.js    # parity-tested port of src/ism/trim_engine.py
├── trim_worker.js    # caches the seasonally adjusted panel per (scope, sa, window)
├── cpipce_app.js     # model 4 — CPI → PCE (no client-side recompute: see below)
├── data/ism.json     # ISM panels + one precomputed baseline combo
├── data/decomp.json  # supply/demand panels
├── data/trim.json    # SA panels, versioned weights, the Cleveland/Dallas
│                     # overlays, and the CPI→PCE payload
└── vercel.json
```

Each model registers itself with `models.js` and owns one `<div id="…-view">`;
nothing else knows the others exist. A model's `init` runs the first time it is
shown, so opening the site does not download every payload.

`engine.js` and `trim_engine.js` must stay in sync with their Python
originals. The contracts are enforced by `tests/test_web_engine_parity.py` and
`tests/test_trim_parity.py`, which run both implementations on the same
synthetic panels — missing data, rank-deficient windows, late-born categories,
publication gaps, quarterly frequency — and assert the outputs match.
`tests/web_smoke.cjs` boots the whole app headlessly (jsdom) and drives every
control.

**The CPI→PCE page deliberately does not recompute in the browser.** The gap
decomposition is an accounting identity and the bridge is a rolling regression
over the full panels: there is no parameter a reader would want to drag, so the
payload carries the finished series and the page is a renderer.

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

## House style (bzhmacro)

The page follows the `bzhmacro.com` identity: `.site-banner` first in `<body>`,
a sticky `.section-nav`, `.wrap.wide`, `header.page-head`, numbered sections,
a sources block and the standing disclaimer in `footer.site-footer`.

`bzh.css` is linked from `https://www.bzhmacro.com/brand/bzh.css` with a
vendored fallback at `assets/bzh.css` (an `onerror` on the `<link>` swaps to it).
**Do not edit either.** Tokens are generated from `brand/tokens.json` in the
brand kit; a local override would silently fork this site from every other
bzhmacro surface.

`styles.css` is the project layer and loads after. It defines only what the
house system does not own — the parameter grid, segmented buttons, the category
picker, chart frames and the export toolbar — and holds no `:root` block.

Two collisions worth knowing about:

- The parameter grid is `.paramgrid`, **not** `.controls`. bzh already defines
  `.controls` as a flex filter row, so the old name fought the house system
  head-on.
- The four view apps emit `.stat > b + span` where bzh expects `.num`/`.lbl`.
  Rather than change four files, `styles.css` styles those scoped to
  `.statrow`, leaving the shared `.stat` untouched.

Section numbers (`01`, `02`, …) come from a CSS counter on `.model-view`, so
each model numbers independently and the markup carries none of it. Add
`class="nonum"` to a section to opt out.

The four models are toggled views, so the section nav switches views rather
than scrolling. Each is deep-linkable — `#ism`, `#decomp`, `#trim`, `#cpipce` —
and `models.js` honours the hash on load and on `hashchange`.

## Exporting a chart

Hover any chart for a small toolbar:

| Button | Output |
| --- | --- |
| `PNG` | 1200×675 at 2×, dark palette, matches the screen |
| `PAPER` | same, on a light background — for notes and PDFs |
| `CSV` | the plotted series, with a provenance header |

All three carry the chart title, the parameter combo it was computed with, the
data-through month and a source line, so an image stays self-documenting once
it has left the site — which is exactly when provenance normally gets lost.

`chart_export.js` reads the figure straight off the Plotly div (`gd.data` /
`gd.layout`), so **the four view apps know nothing about it** and need no
changes when charts are added or reshaped. To register a new chart, add its div
id to the `CHARTS` table at the top of that file.

The paper export deep-clones the figure, rewrites colours through a
dark→light map that mirrors the `@generated:print` block in `bzh.css`, and
renders the clone on an offscreen stage. The stage is positioned far
off-canvas rather than `display:none` — Plotly cannot measure a zero-size node
and would emit a blank image.

The per-view "Download current series (CSV)" buttons were removed in favour of
per-chart CSV. `setupDownload()` in `app.js` is now null-safe, so reinstating a
button is just markup.

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

**Caching.** `vercel.json` gives `/data/(.*)` a one-hour TTL, which is right for
the 27 MB panels and wrong for `data/release_calendar.json`: the panel polls that
file to notice a refresh has gone live, and an hour of staleness would have the
button claiming "up to date" long after a new print landed. A second, more
specific rule therefore gives it `max-age=60, must-revalidate`. Both rules match
that path and Vercel applies them in order, so the specific one must stay
**after** the general one or it has no effect.

That explanation lives here rather than in `vercel.json` because the file has
nowhere to put it: JSON has no comments, and Vercel validates each header entry
with `additionalProperties: false`, so the `"//"` key idiom fails the build with
``headers[1] should NOT have additional property `//` ``.

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

### Forcing a refresh when you know the print is out

US CPI and PCE land at 08:30 ET and the BLS/BEA APIs carry them immediately, so
`fetch_delay_hours` is **0.5** for those two gauges (the 3-hour default held the
gate shut until 11:30 ET and made the Refresh button refuse a print that had
been public for three hours). Scheduled polls at **13:15 and 14:15 UTC** cover
08:30 EDT and 08:30 EST respectively, so a US print is picked up automatically
within ~45 minutes either side of the DST switch.

For anything the calendar does not know about — an off-schedule revision, the
BEA annual update, a print you have in hand before the gate opens — set
`REFRESH_TOKEN` in the Vercel environment and a **Force** button appears next to
Refresh. It skips the "is anything due" test and the cooldown, but not the
in-flight check: two concurrent runs would race to commit the same 27 MB of
JSON. The token is remembered in `localStorage` and cleared automatically if the
server rejects it.

Without the browser, the same thing from the CLI or the Actions tab:

```bash
gh workflow run refresh-data.yml -f gauges="cpi pce"     # specific gauges
gh workflow run refresh-data.yml -f ignore_calendar=true # everything
```

Both bypass the calendar gate — `ism.release_calendar due --only` still
revalidates the names, so a typo fails loudly rather than fetching nothing.

> **After editing `config/release_calendar.yaml`, re-run
> `python scripts/export_release_calendar.py` and commit.** The browser reads
> precomputed UTC instants from `web/data/release_calendar.json`; a delay change
> in the YAML has no effect on the page until that file is regenerated.

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
