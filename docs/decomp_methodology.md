# Supply/Demand decomposition — methodology → code map

Replication of **Shapiro, A. H. (2024), "Decomposing Supply and Demand Driven
Inflation," FRBSF Working Paper 2022-18** (https://doi.org/10.24148/wp2022-18).
This is the second model in the repo, a sibling of the Inflation Shock Momentum
(ISM) index. It shares the data-fetch plumbing (`ism.datasources`, the BEA
client) and the web-app shell, but is a distinct model: it needs both **price**
and **quantity** at the category level, where ISM needs only price.

## The idea in one paragraph

For each of the ~130 fourth-level PCE categories we estimate, on a rolling
10-year window, a reduced-form VAR of the category's **log price** and **log
quantity** on 12 lags of both (Eqs. 12–13), and keep the one-step residuals
ν^p, ν^q. A category-month is **demand-driven** when the price and quantity
surprises share the same sign (both up or both down — a shift along the supply
curve) and **supply-driven** when they have opposite signs (a shift along the
demand curve) (Eqs. 8–11). The **supply- and demand-driven contributions** to
inflation are the expenditure-weighted (Laspeyres) sums of the inflation of the
categories in each group (Eq. 15); the **shares** γ_s are the expenditure-weighted
counts of categories in each group (Eq. 14). Year-over-year contributions are the
running 12-month product of the monthly ones.

## Maths → code

| Paper | Object | Code |
|---|---|---|
| Eqs. 12–13 | rolling reduced-form VAR of (log p, log q), 12 lags, 10-yr window; residuals ν^p, ν^q at the window end | `decomp_engine.rolling_var_residuals` |
| Eqs. 8–11 | sign restrictions → sup(+), sup(−), dem(+), dem(−); supply = opposite signs, demand = same signs | `decomp_engine.classify_labels` |
| Fig. 5 | precision/ambiguous: relabel near-zero residuals (`|ν| < c·σ_i`) as ambiguous; FRBSF publishes c = 0.1 | `classify_labels(..., precision_cut=c)` |
| Eq. 14 | γ_{s,t} = Σ_i 1_{i∈s,t} ω_{i,t} (expenditure shares of the basket) | `decomp_engine.shock_shares` |
| Eq. 15 | π^sup_t, π^dem_t = Σ_i 1_{s,i,t} ω_{i,t-1} π_{i,t} (Laspeyres weight × MoM inflation) | `decomp_engine.contributions` |
| §3.1 | year-over-year = running 12-month product of monthly contributions | `decomp_engine.yoy_contribution` |
| Eqs. 17–18 | IRF (h-months-ahead) residual robustness | `DecompConfig(irf_h=h)` |
| Eqs. 19–20 | first-difference specification | `DecompConfig(spec="diff")` (pipeline supplies Δlog) |
| §3.2 | Hamilton-(2018)-filtered inputs | `DecompConfig(spec="filter")` |
| §3.2 | AR-3 / AR-24 lag robustness | `DecompConfig(var_lags=3 | 24)` |
| Eq. 21 | LP of contributions on HFI monetary & oil-supply shocks | `decomp_projection.irf_contribution_to_shock` |
| Fig. 4 | recession-peak dynamics of the contributions | `decomp_projection.recession_response` |

## Data

* **Prices** — BEA Underlying Detail table **2.4.4U** (`U20404`), monthly price
  indexes by type of product → log price and MoM inflation.
* **Quantities** — BEA table **2.4.3U** (`U20403`), monthly real PCE quantity
  indexes → log quantity. *This is the new input the momentum model did not
  need.* If `U20403` is unreachable, a dev stand-in `quantity = nominal / price`
  is available (`--proxy`); it reproduces the paper's narrative but is not the
  exact chain-type quantity index — rerun with `U20403` for the published series.
* **Weights** — BEA table **2.4.5U** (`U20405`), monthly nominal PCE → the
  Laspeyres expenditure shares ω_{i,t} (lagged one month for Eq. 15).
* **Headline vs core** — `config/pce_categories.csv` is the full set; core drops
  the food-off-premises and energy leaves in `config/pce_core_exclusions.csv`
  (BEA "PCE excluding food and energy"). Weights renormalise over the set in use,
  so the contributions sum to the corresponding aggregate.

## Validation

The FRBSF *published* "Supply- and Demand-Driven PCE Inflation" series (the four
chart CSVs) are the ground truth. They use the **precision (ambiguous)** labeling
(c = 0.1), so compare against `DecompConfig(precision_cut=0.1)`; the working-paper
baseline (Fig. 3) is binary (`precision_cut=0.0`). See `ism.decomp_validate`.

## Parity

`web/decomp_engine.js` is a parity-tested JavaScript port of `decomp_engine.py`
(the website recomputes the decomposition in the browser). The contract is
enforced by `tests/test_decomp_parity.py` (max |py − js| ≈ 2e-16 across residuals,
contributions and shares, over lag orders, windows, IRF horizons, precision
cut-offs and category exclusions).
