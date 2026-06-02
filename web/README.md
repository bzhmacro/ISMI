# ISM interactive explorer (static site)

A zero-build static website to explore the Inflation Shock Momentum index under
different model parameters. No framework, no build step — just HTML + JS +
Plotly (from CDN) + a precomputed JSON.

## Files

```
web/
├── index.html      # layout + controls
├── styles.css
├── app.js          # loads data/ism.json, selects combo, plots, correlates
├── data/ism.json   # precomputed series (DEMO synthetic data ships by default)
└── vercel.json
```

## Refresh the data (use real BEA data)

The repo ships a **synthetic demo** `data/ism.json` so the site renders out of the
box. To replace it with the real, validated index:

```bash
# from the repo root, with BEA data already cached (see ISM_replication.ipynb)
python scripts/export_web_data.py      # writes web/data/ism.json (27 param combos)
```

This precomputes the ISM / S⁺ / S⁻ series for AR(1/3/12) × k(2/3/4) ×
weighting(extensive/size/stickiness), plus the author series and 12-month PCE
inflation. Commit the regenerated `web/data/ism.json`.

## Run locally

```bash
cd web
python -m http.server 8000      # then open http://localhost:8000
```
(Any static server works; opening index.html via file:// will fail the fetch.)

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

- **Benchmark model** — AR(p) used for the rolling residuals (Eq. 3).
- **Run length k** — consecutive same-signed residuals that flag momentum (Eqs. 4-5).
- **Weighting** — `extensive` (sign only, the paper's baseline), `size`
  (× |Σ of the last k residuals|), `stickiness` (× 1/(1−ρ̂)).
- Toggles overlay the author series, the S⁺/S⁻ components, and 12-month PCE
  inflation; the slider trims the sample start; the readout shows the live
  correlation with the authors' published index.
