# Methodology — replicating "Measuring Inflation Shock Momentum"

This document records every step taken to replicate Lansing & Shapiro (2026,
FRBSF WP 2026-10) and maps each piece of the paper's mathematics to the code.

## 0. Sources and reproducibility

All inputs are declared in `config/sources.yaml`. The download clients in
`src/ism/datasources.py` cache every raw pull under `data/raw/<provider>/` and
write a `*.fetch.json` provenance sidecar (URL, parameters, UTC timestamp), so
the full data state can be rebuilt and audited later. The author-provided index
(`data/raw/ISM_public_author.xlsx`) is the ground truth for convergence checks.

## 1. The benchmark DGP and the residuals (paper Eqs. 1–3)

The paper postulates that monthly inflation follows
```
π_t   = μ + ρ·π_{t-1} + ε_t            (1)   intrinsic inertia ρ
ε_t   = α·ε_{t-1} + u_t                (2)   shock momentum α
```
and argues that estimating α directly is ill-behaved and "sign-agnostic". Instead
of estimating α, they detect *runs of same-signed residuals* from the benchmark
AR(1). For each of the 129 categories they estimate, on a 120-month rolling
window,
```
π_{i,t} = μ_i + ρ_i·π_{i,t-1} + ε_{i,t}    (3)
```
keeping the residual at the **end** of each window. The first window is
1959m2–1969m1, so residuals (and the index) start 1969m1.

**Code.** `engine.rolling_ar_residuals` (per category) and `engine.residual_panel`
(all categories). `_ar_design_matrix` builds the AR(p) regression; OLS is solved
with `np.linalg.lstsq`. `ISMConfig(ar_order, window)` exposes p and W
(baseline AR(1), W=120; robustness AR(3)/AR(12)). Monthly inflation itself is
built from the BEA price index by `transforms.monthly_inflation`
(`100·Δln P` by default).

> Implementation choice: the residual we keep for month *t* is the last residual
> of the window that *ends* at *t*. This matches the paper's phrasing ("near the
> end date of the rolling window") and makes a *k*-month run a property of recent,
> same-vintage residuals. This is the most consequential modelling choice and is
> the first thing to revisit if convergence is imperfect (see differences report).

## 2. Momentum signals (paper Eqs. 4–5)

A category has positive momentum at *t* if its last *k=3* residuals are all >0:
```
M⁺_{i,t} = Π_{k=0}^{2} 1(ε_{i,t-k} > 0)     (4)
M⁻_{i,t} = Π_{k=0}^{2} 1(ε_{i,t-k} < 0)     (5)
```
**Code.** `engine.momentum_signals`: builds boolean panels `1(ε>0)` / `1(ε<0)`
and takes a rolling product over the last `cfg.run_length` rows (a NaN residual
breaks a run, since its indicator is 0). Returns 0/1 panels `M⁺`, `M⁻`.
`run_length` is configurable (paper robustness: k=2,3,4).

## 3. Expenditure-weighted shares and the index (paper Eqs. 6–8)

```
S⁺_t = Σ_i ω_{i,t}·M⁺_{i,t}     (6)
S⁻_t = Σ_i ω_{i,t}·M⁻_{i,t}     (7)
ISM_t = S⁺_t − S⁻_t             (8)
```
where ω_{i,t} is the category's PCE expenditure weight (nominal PCE share from
BEA table 2.4.5U). Note S⁺ and S⁻ need **not** sum to one — many categories have
no 3-month run in a given month.

**Code.** `engine.expenditure_weighted_shares` aligns the momentum panels with
the weights, renormalises weights each month over the categories actually
available (so shares stay in [0,1] even early in the sample), then computes the
weighted sums. `engine.ism_index` does Eq. (8). `engine.compute_ism` chains
Eqs. (3)→(8) and returns an `ISMResult` bundle (index, components, residuals,
signal panels).

We verified the identity `ISM = S⁺ − S⁻` directly against the author file
(`tests/test_engine.py::test_identity_against_author_file`): max |diff| ≈ 1e-3,
explained entirely by the file being published rounded to 3 decimals.

## 4. Building the category panel (paper fn 7)

BEA "Underlying Detail" monthly tables, **fourth level of disaggregation**, 129
categories back to 1959:
- **2.4.4U** (`U20404`) price indexes → category inflation π_{i,t}.
- **2.4.5U** (`U20405`) nominal PCE → expenditure weights ω_{i,t}.

**Code.** `pipeline.build_category_panel` fetches both tables via `BeaClient`,
pivots to wide panels (`_bea_long_to_wide`), and selects the 4th-level leaves
(`select_leaf_categories`, depth inferred from BEA's LineDescription
indentation, with an explicit-list escape hatch and a "expected 129" guardrail).
Weights are nominal/Σnominal, renormalised monthly.

## 5. Controls and the forecasting tests (paper Table 1, Eq. 9)

Controls (FRED unless noted), assembled by `controls.build_controls`:
12-month & 3-month PCE inflation (PCEPI), 1-yr inflation expectations (MICH,
pre-1978 proxied by trailing 12m PCE inflation per fn 14), V/U (JOLTS `JTSJOL` /
`UNRATE`, spliced to Barnichon (2010) for pre-2000 history), WTI oil (`WTISPLC`),
S&P 500 level (Shiller monthly — FRED's `SP500` is licence-limited to ~10y), real
disposable income y/y (`DSPIC96`), 10yr–FFR spread (`GS10`−`FEDFUNDS`), NBER
recession (`USREC`).

**Table 1** (`forecasting.table1`): dependent variable = 12-month PCE inflation
*h* months ahead (h=12, 24); regressors = constant + current 12m PCE inflation,
then either ISM or {S⁺,S⁻}, optionally + the control block. OLS with **HC1 robust**
standard errors, matching the paper's "robust standard errors in parentheses".

## 6. Out-of-sample (paper Table 2) and validation (Section 5) — scaffolded

The out-of-sample exercise uses an **adaptive LASSO** (Eq. 14) with λ chosen by
rolling-window cross-validation to minimise RMSFE, compared via the
Giacomini–White test. The validation exercises (Eq. 15) are local projections of
the ISM index onto Romer–Romer attempted-disinflation dates and the Känzig oil
supply news shock. These are part of the "expand" phase; their data sources are
already registered in `sources.yaml` (Romer–Romer dates are stated in the paper;
Känzig and Barnichon series are externally hosted).

## 7. Testing

`tests/test_engine.py` (no network needed):
1. momentum run logic (Eqs. 4–5) on a hand-built residual panel;
2. shares & index identity (Eqs. 6–8) with known weights;
3. AR(1) residual sign recovery (Eq. 3) on data with an injected shock;
4. `ISM = S⁺ − S⁻` against the real author file.

A whole-pipeline smoke test (synthetic 130-category panel) confirms the engine
detects an injected positive-shock regime and that `forecasting.table1` runs.

## 8. Long-history controls (V/U, S&P 500)  [src/ism/external_data.py]

FRED is missing two series the paper uses at full length:
- **V/U ratio**: JOLTS job openings (`JTSJOL`) only start in 2000. We splice the
  Barnichon (2010) composite Help-Wanted Index to JOLTS by scaling the index to
  JOLTS units over their overlap (median ratio), preferring JOLTS where it
  exists, then dividing by the unemployment level (`UNEMPLOY`). Paper fn 15.
- **S&P 500 level**: FRED's `SP500` is licence-limited to ~10 years. We use
  Robert Shiller's `ie_data.xls` (monthly composite price, parsed from its
  fractional-year date format where .01=Jan … .12=Dec).

Both are wired into `controls.build_controls` and the core notebook, with
graceful fallback to FRED-only if the files are absent.

## 9. Local projections — Figures 2 & 3  [src/ism/local_projection.py]

Jorda (2005) LPs, estimated directly (the contemporaneous coefficient equals the
response to the orthogonalized "surprise" by Frisch-Waugh), with Newey-West HAC
standard errors (maxlags = h+1):
- **Eq. (9) / Figure 2**: dependent variable `100*(ln p_{t+h} - ln p_{t-1})`
  (PCE price level); impulse = ISM (or S+, S-); controls = 12 lags of ISM and
  current+12 lags of the macro controls. Responses scaled to a 1 sd shock,
  horizons 0–60.
- **Eq. (15) / Figure 3**: dependent variable `ISM_{t+h} - ISM_{t-1}`; impulse =
  Romer-Romer disinflation dummy (raw 0/1 event) or the Kanzig (2021) oil-supply
  news shock (1 sd); controls = 12 lags of ISM and 12 lags of the recession
  dummy, horizons 0–36. Romer-Romer dates are taken from the paper text.

## 10. Out-of-sample adaptive LASSO — Table 2  [src/ism/oos_lasso.py]

Adaptive LASSO (Eq. 14): `min ||y-Xb||^2 + lambda*sum_j (1/|b_j^OLS|)|b_j|`,
implemented by the standard reparametrisation + scikit-learn `Lasso` on
standardized predictors. Direct h-step forecasts of 12-month PCE inflation
(h=12,24,36) over rolling 120-month windows; `lambda` chosen by grid search to
minimize rolling-window RMSFE; baseline vs baseline+ISM compared by the RMSFE
ratio and the Giacomini-White (2006) test. Standardized full-sample coefficients
give relative predictor importance.

All four modules are unit-tested on synthetic data (`tests/`), since the build
sandbox cannot reach the live data providers; the live figures/tables are
produced by running `notebooks/ISM_expand.ipynb` on a networked machine.
