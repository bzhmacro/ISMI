# ISM — Inflation Shock Momentum (replication)

A readable, portable Python replication of:

> Lansing, K. J. & Shapiro, A. H. (2026). **Measuring Inflation Shock Momentum.**
> FRBSF Working Paper 2026-10. https://doi.org/10.24148/wp2026-10

The paper builds a non-parametric **Inflation Shock Momentum (ISM)** index from
the cross-section of ~129 disaggregated PCE inflation categories, and shows it
helps forecast aggregate PCE inflation 1–3 years ahead. This repo reproduces the
index and its empirical tests, and is designed so you can (1) feed in your own
forecasts of future data, (2) share it as readable code, and (3) port the idea
to other countries/datasets.

## What the index is, in one paragraph

For each PCE category we estimate a 120-month rolling AR(1) benchmark for monthly
inflation and keep the most recent regression residual each month. A category has
**positive momentum** when its last *k = 3* residuals are all positive (a
sustained run of "hotter than the benchmark" surprises), and **negative momentum**
when the last 3 are all negative. We then take expenditure-weighted shares of
categories with positive (`S⁺`) and negative (`S⁻`) momentum, and define

```
ISM_t = S⁺_t − S⁻_t          (net positive momentum share)
```

A positive ISM means broad-based upward inflation pressure; negative means
disinflationary pressure. See `docs/methodology.md` for the full maths→code map.

## Repository layout

```
ISMI/
├── config/
│   ├── sources.yaml           # registry of EVERY US data source (URLs, series IDs, roles)
│   ├── sources_europe.yaml    # FRED -> Eurostat mapping for the EU port
│   ├── sources_uk.yaml        # FRED/BEA/BLS -> ONS mapping for the UK CPI port
│   ├── sources_japan.yaml     # FRED/BEA/BLS -> e-Stat mapping for the Japan CPI port
│   ├── pce_categories.csv     # the pinned 130 fourth-level PCE categories
│   └── cpi_categories.csv     # the pinned ~70 BLS CPI item strata (alt. backbone)
├── src/ism/                   # the library (the importable engine + plumbing)
│   ├── engine.py              # the ISM maths: Eqs (3)-(8). The centerpiece.
│   ├── transforms.py          # price index -> inflation transforms
│   ├── datasources.py         # FRED / BEA / BLS clients (retry, caching, provenance)
│   ├── external_data.py       # Shiller S&P, Barnichon V/U, Kanzig, Romer-Romer, STOXX
│   ├── pipeline.py            # BEA tables -> category inflation panel + weights (PCE)
│   ├── cpi_pipeline.py        # BLS CPI item strata -> panel + weights (alt. backbone)
│   ├── controls.py            # control / predictor frame
│   ├── forecasting.py         # Table 1 in-sample regressions
│   ├── oos_lasso.py           # Table 2 out-of-sample adaptive LASSO + GW test
│   ├── local_projection.py    # Figures 2-3 local projections
│   ├── appendix.py            # appendix exhibits (run probs, weighted momentum, ...)
│   ├── eurostat.py            # Eurostat JSON-stat client (EU port)
│   ├── eu_pipeline.py         # HICP -> ISM for the euro area
│   ├── ons.py                 # ONS client: MM23 bulk CSV + /generator (UK port)
│   ├── uk_pipeline.py         # ONS CPI COICOP classes -> ISM for the UK
│   ├── estat.py               # e-Stat API client (Japan port; free ESTAT_APP_ID)
│   ├── jp_pipeline.py         # Japan CPI by item -> ISM (e-Stat 2020-base table)
│   ├── figures.py / validate.py / run.py
├── scripts/                   # runnable helpers
│   ├── build_and_validate.py  # build the US index + convergence check
│   ├── finalize_categories.py # pin config/pce_categories.csv from BEA hierarchy
│   └── export_web_data.py     # export raw panels + baseline to web/data/ism.json
├── notebooks/                 # guided, runnable analyses
│   ├── ISM_replication.ipynb  # Figure 1 + Table 1 (core)
│   ├── ISM_expand.ipynb       # Figures 2-3 + Table 2
│   ├── ISM_appendix.ipynb     # Figures A1-A8 + Tables A1-A6
│   └── ISM_europe.ipynb       # euro-area port (Eurostat HICP)
├── web/                       # zero-build interactive site (deploy on Vercel)
│   ├── index.html / app.js / styles.css / vercel.json
│   ├── engine.js / worker.js  # the ISM maths IN THE BROWSER (parity-tested JS port)
│   └── data/ism.json          # raw panels + baselines, all gauges: pce cpi uk fr de [jp] (regen via scripts/export_web_data.py)
├── tests/                     # 25 synthetic unit tests incl. Python<->JS parity (no network)
├── docs/                      # methodology.md, differences_report.md, DECISIONS.md
├── data/                      # NOT committed (gitignored); see data/README.md
├── .env.example  pyproject.toml  requirements.txt  pytest.ini  LICENSE
```

## Data & secrets (read before pushing)

- **No secrets are committed.** `.env` (your API keys) is gitignored — use
  `.env.example` as the template.
- **No data is committed.** `data/raw/` and `data/processed/` are gitignored; all
  inputs are reproducible from the source registries (`config/sources*.yaml`).
  See `data/README.md` for how to populate them and which hand-added files
  (author series, Shiller, Barnichon, Kanzig, STOXX) go where.
- The working-paper PDF is gitignored (not redistributed); cite it via its DOI.

## Quick start

This is a `src/` layout, so install the package once (this also pulls the
dependencies and creates the `ism` command). Run all commands **from the repo
root** (the folder containing `pyproject.toml`).

```bash
# 1) install (editable) + dependencies, then add your keys
pip install -e .
cp .env.example .env            # then paste your FRED / BEA / BLS keys

# 2) download + cache all inputs (needs internet access to BEA & FRED)
ism fetch                       # equivalently: python -m ism.run fetch

# 3) build the category panel, compute the ISM index, validate vs author file
ism index

# 4) in-sample forecast table (Table 1) and figures
ism table1
ism figures

# ...or run the whole pipeline end to end
ism all

# Alternative price gauge: run the SAME index on BLS CPI instead of BEA PCE
ism fetch cpi                   # download + cache the BLS CPI item strata
ism index cpi                   # build the CPI panel -> compute ISM (no author overlay)
```

### Running without installing

If you'd rather not install, invoke the orchestrator script directly — it adds
`src/` to the path itself:

```bash
python src/ism/run.py all
# or:  PYTHONPATH=src python -m ism.run all
```

> Plain `python -m ism.run` from the repo root only works **after**
> `pip install -e .` (otherwise Python can't find the `ism` package under
> `src/`). Use `python src/ism/run.py` if you skip the install.

Get free API keys: FRED https://fredaccount.stlouisfed.org/apikey ·
BEA https://apps.bea.gov/API/signup/ · BLS https://data.bls.gov/registrationEngine/

> **Network note.** The sandbox used to develop this repo blocks BEA and FRED
> hosts, so `fetch` must be run in an environment where those hosts are
> reachable (a normal laptop with the keys in `.env`). All other steps run
> anywhere from the cached data. See `docs/differences_report.md`.

## The three design goals, and how the code meets them

1. **Feed in your own forecasts of future data.** The engine consumes a plain
   `inflation_panel` (months × categories) and `weights`. To test a forecast
   scenario, append your projected category inflation rows to the panel and call
   `compute_ism` again — the rolling AR(1) and momentum logic extend naturally
   into the future. Controls accept the same append-a-future-row pattern.

2. **Portable & readable.** Pure pandas/numpy/statsmodels/sklearn; every function
   maps to a numbered equation; no hidden state. One `pip install -r`.

3. **Port to other countries/datasets.** Nothing is US-specific in `engine.py`.
   To run on, say, euro-area HICP components: point `sources.yaml` at the new
   category price/expenditure source, implement a small loader returning the same
   `(inflation_panel, weights)` shape, and the index falls out unchanged. The
   **CPI backbone** (`src/ism/cpi_pipeline.py`, below) is a worked in-repo example
   of exactly this — a second price gauge behind the same engine.

## The CPI backbone (alternative price gauge)

The paper builds the ISM on **PCE**. Because `engine.py` only ever sees an
`(inflation_panel, weights)` pair, the identical momentum machinery runs on the
**BLS Consumer Price Index** too. `src/ism/cpi_pipeline.py` produces that pair
from CPI data, and the interactive site exposes a **Price gauge** toggle to flip
between PCE and CPI live. Run it with `ism index cpi` (or
`python scripts/export_web_data.py cpi` to refresh just the CPI half of the web
data — the PCE backbone on disk is preserved).

How the CPI backbone is built, and where it differs from PCE:

- **Prices.** One NSA price index per CPI item stratum, series
  `CUUR0000<item>` (CPI-U, US city average, *not* seasonally adjusted — the right
  input for month-over-month inflation, matching how the PCE pipeline treats the
  BEA price index). Source: BLS, `api.bls.gov` (a key raises the daily cap but is
  optional), with the full history also available from the BLS flat files under
  `download.bls.gov/pub/time.series/cu/`.

- **Categories.** `config/cpi_categories.csv` pins a **non-overlapping partition
  of ~70 item strata** whose relative importances sum to 100% — a complete tiling
  of the index, the CPI analogue of the paper's "fourth level" PCE cut. It was
  obtained by walking the BLS relative-importance tree top-down and taking, on
  each branch, the shallowest node that maps to a published item-stratum (`SE`)
  series. Because the engine renormalises the weights each month, the index is
  robust to the exact category cut.

- **Weights.** The CPI has no monthly expenditure series (PCE does — BEA table
  2.4.5U). We therefore use the **static BLS December-2023 relative importance**,
  broadcast across all months; the engine renormalises it each month over the
  categories with a defined signal. This is a documented simplification: PCE
  weights drift month to month, the CPI RI is refreshed only annually. To use
  year-varying RI, swap the single `ri_weight` column for one column per year.

- **History.** Most strata reach back to the 1950s–60s; a few begin later
  (owners' equivalent rent from 1983, telephone/IT services from 1997–98). The
  engine treats a category as absent until it has a full 120-month window, so the
  CPI ISM simply has fewer categories early on — exactly how the PCE pipeline
  handles late-born lines.

- **Publication gaps.** BLS occasionally does not publish a month (e.g. the
  **October 2025** CPI release was never produced). A single missing interior
  month would break the month-over-month inflation chain and force the momentum
  signal to zero for every later month, so `cpi_pipeline` linearly interpolates
  *interior* gaps in the price index (`limit_area="inside"`, which never
  fabricates a leading or trailing tail — only bridges holes between two real
  prints). The interpolated month is documented here and in `sources.yaml`.

- **No author overlay.** The authors publish only the PCE series, so the CPI
  gauge has no ground-truth overlay; the web app hides the *Author series*
  control and the correlation read-out for CPI.

## Validating against ground truth

`python -m ism.run index` prints a convergence table (correlation, RMSE, MAE,
max abs diff) comparing our computed `ISM / S⁺ / S⁻` to the author-provided
`data/raw/ISM_public_author.xlsx`, and `validate.overlay_chart` saves a visual
overlay to `outputs/`.

## Tests

```bash
python -m pytest        # 4 tests: momentum-run logic, shares/index identity,
                        # AR(1) residual recovery, and ISM=S⁺−S⁻ vs author file
```

## Expand phase: Figures 2 & 3 and Table 2

`notebooks/ISM_expand.ipynb` reproduces the impulse responses and out-of-sample
forecasts, using the tested modules in `src/ism`:

- **Figure 2** (`local_projection.py`) — cumulative log-PCE-price response to a
  1 sd ISM / S⁺ / S⁻ surprise (Eq. 9).
- **Figure 3** (`local_projection.py`) — ISM response to Romer-Romer disinflation
  dates and the Känzig (2021) oil-supply news shock (Eq. 15).
- **Table 2** (`oos_lasso.py`) — out-of-sample adaptive-LASSO forecasts, baseline
  vs baseline+ISM, RMSFE ratio + Giacomini-White test (Eq. 14).

### Optional external files (drop in `data/raw/external/`)

For the full-sample control columns and Figure 3b:

- `ie_data.xls` — Shiller S&P 500 (auto-downloads if missing).
- `barnichon_hwi.csv` — Barnichon (2010) Help-Wanted Index (2 cols: date, index),
  for the V/U splice back to the 1950s. From Régis Barnichon's data page.
- `kanzig_oilshock.csv` — Känzig (2021) oil-supply news shock (2 cols: date,
  shock), for Figure 3b. From Diego Känzig's replication files.

Everything degrades gracefully if these are absent (V/U starts 2000, S&P uses the
short FRED series, Figure 3b is skipped). See `docs/DECISIONS.md` for the choices
made and `docs/methodology.md` for the full method.

## Tests

`python -m pytest` runs 12 synthetic unit tests covering the engine, external
loaders (incl. the Shiller parser), local projections, and the LASSO/GW machinery.

## Appendix exhibits

`notebooks/ISM_appendix.ipynb` reproduces the online-appendix figures and tables
(built on `src/ism/appendix.py`, which is unit-tested):

- **Fig A1** rolling ρ̂/α̂ (headline) + distribution of category ρ̂; **Fig A2**
  empirical consecutive-run shares; **Fig A3** theoretical run probabilities
  (arcsine law); **Fig A4** ISM by goods vs non-housing services and by
  AR(1/3/12); **Fig A5** aggregate (ternary) vs category-level ISM;
  **Fig A6/A7/A8** IRF robustness by k, AR model, and subsample.
- **Table A1** in-sample fit across AR×k; **Table A2** out-of-sample LASSO with
  AR(3) momentum; **Tables A3/A4** momentum weighted by shock size and by
  1/(1−ρ̂); **Table A5** aggregate-ISM in-sample; **Table A6** parametric α̂
  (which shows the paper's "perverse sign" result).

Heavy cells (multiple full-history ISM variants, the LASSO, the IRF grid) are
flagged in the notebook and take a few minutes.
