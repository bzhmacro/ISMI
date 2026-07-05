# The website: ship raw panels, recompute live, parity-test the twin

The website is not a screenshot of results — it is the model itself, running in the
visitor's browser. This is what makes every parameter a live dial and lets the page
auto-refresh as new data prints, with no server.

## Contents
- The architecture decision (ship raw, recompute client-side)
- File layout
- The JS engine twin and the parity contract
- The Web Worker
- The JSON export
- Performance notes
- Deploy (static, no build)
- Scheduled auto-refresh
- Graceful degradation

## The architecture decision

Three options exist for an interactive replication site: (a) a Python
backend/serverless that recomputes on request; (b) **precompute the raw inputs and
recompute in JS**; (c) precompute a finite grid of all parameter combinations and
just select in JS. Prefer **(b)**: ship `data/<name>.json` containing the *raw*
`(panel, weights)` panels plus one precomputed baseline combo (for instant first
paint), and recompute the full pipeline client-side whenever a control changes.

Why: it makes window length, lag order, run length, weighting scheme, and even the
unit set *continuous* live dials instead of a fixed grid; it needs no Python runtime
and no build step (most robust to deploy); and it keeps the data payload small (raw
panels, not a combinatorial grid). Continuous "inject your own forecast" scenarios,
which can't precompute, stay in the notebooks; the site covers the model
parameters.

## File layout

```
web/
├── index.html        # layout + controls
├── styles.css
├── app.js            # UI: loads JSON, drives the worker, plots, correlates
├── engine.js         # THE MATHS IN JS — a parity-tested port of src/pkg/engine.py
├── worker.js         # Web Worker wrapper; caches residual panels per (gauge, AR, W)
├── data/<name>.json  # raw panels + one baseline combo (regen via export script)
└── vercel.json
```

No framework, no bundler — plain HTML + JS + a charting lib from a CDN (Plotly,
Chart.js). Opening `index.html` via `file://` breaks `fetch`/Workers; always serve
it (`python -m http.server`).

## The JS engine twin and the parity contract

`engine.js` is a line-for-line port of the Python engine — the same equations, the
same rolling normal-equations-from-prefix-sums, the same pseudo-inverse fallback
for rank-deficient windows. It **will** drift from the Python over time unless you
pin it down, so make the contract executable:

> `tests/test_web_engine_parity.py` runs both implementations on the *same*
> synthetic panel — including missing data and rank-deficient windows — and asserts
> the residuals, momentum signals, and index match to a tight tolerance.

Run the JS side under Node from the test (shell out to `node` with a tiny harness,
or use a JS runtime binding). Treat a parity failure as a release blocker: the whole
value of the site is that it computes the *same* thing the paper does. A headless
smoke test (`web_smoke.cjs` via jsdom) that boots the app and drives every control
catches UI/wiring regressions the parity test doesn't.

See `templates/web/engine.js`, `templates/web/worker.js`, and
`templates/tests/test_web_engine_parity.py` for skeletons.

## The Web Worker

Run the engine off the main thread so the UI never janks. A simple message
protocol:

```
-> { type:"init", panels:{ pce:{inflation,weights}, cpi:{…} } }
<- { type:"ready", backbones:[…] }
-> { type:"compute", id, backbone, params:{ ar,W,k,scheme,rhoCap,excluded } }
<- { type:"result", id, backbone, Index, S_pos, S_neg, drivers, ms }
```

Cache residual panels per `(backbone, AR order, window W)` inside the worker — those
are the expensive regression passes; changing run length, weighting scheme, a cap,
or the unit set is then a near-instant re-aggregation. Bound the cache (drop oldest)
so memory stays flat.

## The JSON export

`scripts/export_web_data.py` (run from the repo root against cached data) writes
`web/data/<name>.json`: the raw inflation + weight panels for every backbone, the
author overlay, any headline series for context, and one precomputed baseline combo
for instant first paint. Version the schema (`"schema": 3`) so the app can detect
and gracefully handle an old payload. Keep the export **self-fetching** (it can pull
the provider tables itself) so a scheduled job needs no committed data.

## Performance notes (what "good" looks like)

- Assemble each window's normal equations from prefix sums of lagged
  cross-products: a full AR(1) pass over ~130 units × ~800 months is ~30 ms; worst
  case (AR(12), W=240) ~150 ms.
- Per-`(gauge, AR, W)` residual caching makes scheme/k/cap/unit-set changes
  re-aggregate in ~5–10 ms.
- Solve rank-deficient windows min-norm via pseudo-inverse, matching
  `numpy.lstsq`.

## Deploy (static, no build)

The site is fully static, so there is **no build command**. On Vercel: import the
repo, set Root Directory = `web`, Framework Preset = Other, leave build empty,
deploy. Or `cd web && vercel --prod`. Any static host works.

## Scheduled auto-refresh

A scheduled CI job (e.g. `.github/workflows/refresh-data.yml`, monthly + manual)
re-runs the self-fetching export, commits the regenerated `web/data/<name>.json`,
and pushes — which triggers an automatic redeploy. Store provider API keys as CI
secrets. Surface "data through YYYY-MM · recomputed live in your browser" in the
header so freshness is visible.

## Graceful degradation

If the worker can't start, or an older JSON schema is served, fall back to the
precomputed baseline combo and hide the live-only controls rather than showing a
broken page. The site should always render *something* correct.
