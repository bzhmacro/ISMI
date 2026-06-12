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

`.github/workflows/refresh-data.yml` rebuilds `web/data/ism.json` from the latest
BEA/FRED data on the 3rd of each month (and on demand via the **Run workflow**
button), commits it, and pushes — which triggers an automatic Vercel redeploy.

**One-time setup:** in your GitHub repo → **Settings → Secrets and variables →
Actions → New repository secret**, add:
- `FRED_API_KEY`
- `BEA_API_KEY`

The export is self-fetching (it pulls the BEA tables via the API), so the Action
needs no committed data. The site header shows "Data through YYYY-MM · generated
… · index recomputed live in your browser".

To refresh manually instead: run `python scripts/export_web_data.py` locally and
commit `web/data/ism.json`.

## Charts

- **Main** — ISM (recomputed live) vs the author series, optional S⁺/S⁻ components
  and a 12-month headline-inflation overlay; sample-start slider; live correlation.
- **Last 22 ISM prints** — a bar chart of the most recent 22 monthly values
  (orange = positive pressure, blue = negative); click a bar to inspect that month.
- **Top drivers** — for the selected (or latest) month, the categories contributing
  most to the index (ωᵢ·(M⁺ᵢ−M⁻ᵢ), which sum exactly to the ISM), so you can see
  *what* is pushing it up or down.
