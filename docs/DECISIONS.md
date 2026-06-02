# Decisions log

Records the judgment calls made during the build, the options that were on the
table, and which path was taken (and why). Written so choices can be revisited.

## D1. Notebook vs installable module
- Options: (a) pip-installable package only; (b) single self-contained notebook;
  (c) hybrid.
- **Taken: hybrid.** The core engine + Figure 1 + Table 1 live in a
  self-contained `notebooks/ISM_replication.ipynb` (engine inlined for
  readability — it's the heart of the paper). The tested library in `src/ism`
  remains as the reference implementation and powers the heavier expand-phase
  analyses. Rationale: the user found "installing a module to replicate a PDF"
  heavy, but the complex/fragile pieces (data loaders, LASSO, local projections)
  are safer unit-tested in one place than duplicated inline.

## D2. PCE category data source (the 129 categories)
- Options: (a) FRED mirror of the underlying detail; (b) BEA API; (c) BEA bulk
  files; (d) hard-coded category list.
- **Taken: BEA API for values + BEA interactive CSV for hierarchy.** The JSON
  API gives values but strips indentation, so hierarchy depth (needed for the
  "fourth level") came from the interactive-table CSV. The resulting list is
  pinned to `config/pce_categories.csv` (deterministic thereafter).
- Note: matching price `…RG`/`IA…` to nominal `…RC`/`LA…` on a normalized key was
  essential (the original bug that returned an empty panel).

## D3. Defining the "fourth level / 129 categories"
- Options considered, with #categories and correlation vs the author ISM:
  summary-`(NN)`-reference set (58, 0.97); ultimate leaves (227, 0.962);
  level-4 cut (59, 0.938); level-5 cut incl. NPISH (142, 0.982);
  **level-5 cut excluding addenda + NPISH "…services to households" (130, 0.990).**
- **Taken: the 130-category level-5 cut excluding addenda and the NPISH
  net-output layer.** Lands one above the paper's 129 at correlation 0.990.
- Not taken: chasing the exact 129 by dropping one more category — without the
  authors' exact list this risks removing a legitimate category; the residual is
  inside the reported 0.03 RMSE. Flagged in `differences_report.md`.

## D4. Inflation transform & weights
- Options: log change vs % change; renormalized weights vs raw PCE shares.
- **Taken: `100*dln(price)` and monthly-renormalized nominal-share weights.**
  Empirically these choices did not move the correlation (all 0.982 before the
  NPISH fix), so the category set — not the transform — was the binding issue.

## D5. Long-history controls (V/U and S&P 500)  [Part A]
- Problem: FRED's JOLTS starts 2000 and FRED's S&P 500 is licence-limited (~10y),
  which would truncate Table 1's with-controls columns.
- Options: (a) accept the short sample; (b) splice external series.
- **Taken: splice.** V/U = Barnichon (2010) HWI scaled to JOLTS over their
  overlap, divided by the unemployment level (paper fn 15); S&P 500 = Shiller
  `ie_data.xls`. Both load via `src/ism/external_data.py` with graceful fallback
  to FRED-only if the files are absent. Barnichon must be user-supplied
  (`data/raw/external/barnichon_hwi.csv`) because its hosted format varies by
  vintage; Shiller auto-downloads.
- Caveat I could not resolve from this sandbox: the exact Barnichon URL/format
  and the Kanzig shock file format are unverified here (no network); loaders are
  written to a documented 2-column shape with clear errors if the file is missing.

## D6. Local projections (Fig 2, Fig 3)  [Part B]
- Options: estimate the "ISM surprise" in a separate first stage, vs estimate
  Eq. (9) directly and read the contemporaneous coefficient.
- **Taken: estimate Eq. (9)/(15) directly with the lags as controls.** By
  Frisch-Waugh the contemporaneous coefficient equals the response to the
  orthogonalized surprise, with fewer moving parts. Newey-West (HAC) SEs,
  maxlags = h+1. Romer-Romer response uses the raw 0/1 event (no sd scaling);
  ISM and Kanzig responses are scaled to a 1 sd shock.

## D7. Out-of-sample LASSO (Table 2)  [Part B]
- **Taken: adaptive LASSO** (weights 1/|b_OLS|) via scikit-learn, rolling
  120-month windows, lambda chosen by grid search to minimize rolling RMSFE,
  compared with the Giacomini-White test (unconditional/DM form on the squared-
  error differential, HAC). Predictors standardized so full-sample coefficients
  are comparable.
- Caveat: the paper's exact lambda cross-validation scheme and GW conditioning
  set are described at a high level; the implementation follows the stated
  procedure and is unit-tested on synthetic data (a genuinely predictive ISM
  lowers RMSFE with a significant GW statistic).

## D8. What is tested vs what must run on your machine
- Everything is **unit-tested on synthetic data** (12 tests: engine, external
  loaders incl. Shiller parser, local projections, LASSO/GW). The build sandbox
  cannot reach BEA/FRED/Shiller, so the live numbers (Fig 2/3, Table 2) are
  produced when you run the notebooks on your machine. The core index already
  validated at 0.99 against the authors' file.

## D9. Interactive website architecture
- Options: (a) Next.js/serverless with Python; (b) static precompute + JS recompute;
  (c) static precompute of all discrete combos + JS selection.
- **Taken: (c).** `scripts/export_web_data.py` precomputes ISM/S⁺/S⁻ for all 27
  combos (AR×k×weighting); a zero-build static site (`web/`, Plotly via CDN)
  selects + plots + correlates client-side. No Python runtime, no build step —
  most robust for Vercel. A synthetic demo `ism.json` ships so it renders before
  the real export is run. Continuous "forecast injection" is left to the
  notebooks (infinite scenarios don't precompute); the site covers the discrete
  model parameters.

## D10. Europe port — validated mapping choices
User-validated (this session):
- **Geography:** euro area (EA20; EA19/EA for longer history).
- **Inflation expectations:** EC Consumer Survey balance (`ei_bsco_m`) — monthly,
  long history, qualitative balance (scale absorbed in regression). Not the ECB
  CES (too short).
- **Equity index:** STOXX Europe 600 (external file; Eurostat has no equity index).
- **V/U:** Eurostat `jvs` quarterly vacancy rate / `une_rt_m`, interpolated to
  monthly (history ~2006-2009+).
Still open (flagged in sources_europe.yaml): real disposable income deflator;
EU monetary-policy shock analogue for the Section-5 validation.

## D11. Europe — category set and engine reuse
- **Taken:** HICP-by-COICOP is the analogue of PCE underlying detail; COICOP leaf
  codes (capped at 4-digit class by default, `max_digits` knob) are the analogue
  of the BEA level cut. The EU panel flows through the **identical** engine /
  forecasting / LP / LASSO modules — only `eu_pipeline` + `eurostat` are new.
- Caveat: detailed euro-area HICP starts ~1997-2001, so the 120-month-window
  index begins ~2007-2011; there is no author series to validate against, so the
  EU port is judged on economic plausibility + in-sample fit.
