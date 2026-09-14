# Port decisions

Non-obvious modelling and data judgment calls made when porting the two FRBSF
models to other countries. Referenced from the source docstrings and the
`config/sources_*.yaml` registries.

## US — goods vs services scopes (supply/demand decomposition)

- **Goods/services split.** Alongside `headline` and `core`, the US PCE model
  exposes `goods` and `services` scopes (the analogue of the Canada
  total/goods/services scopes, Shapiro Figs. 3–4). Each pinned leaf carries a
  `gs` tag (G/S) in `config/pce_categories.csv`, consumed by
  `ism.decomp_pipeline.goods_services_keys`. Unlike Canada — where the tag is a
  hand-made judgment call at the durable/service boundary — the US tag is
  **BEA's own PCE aggregate split**: table 2.4.5U places the "Goods" header at
  line 2 and "Services" at line 150, so every leaf with `line < 150` is a good
  and `line >= 150` a service (66 goods, 64 services of the 130 pinned leaves).
  No boundary judgment is needed. `scripts/finalize_categories.py` re-emits the
  `gs` column on a category rebuild so the split survives regeneration.

- **All-PCE, monthly, no author overlay.** Both scopes use the full pinned set
  (no core food/energy cut) and the same monthly baseline as headline/core
  (`DecompConfig(var_lags=12, window=120)`). FRBSF publishes supply/demand only
  for headline and core, so `goods`/`services` carry **no author overlay**;
  validation is internal coherence (`sanity_quarterly_decomp`) and the dotted
  overlay is the panel's own aggregate implicit-deflator y/y change, as for the
  Canada goods/services scopes. Sanity: goods y/y peaks ~14% in the 1974 oil
  shock (supply-led) and services later (~11% around 1980–81).

- **Web.** Both appear in the decomposition site's Scope selector as `US goods`
  / `US services`, grouped after `headline`/`core` and before the Canada scopes
  (the selector is built from `meta.scopes`, so no JS change was needed).

## Canada (Bank of Canada SAP 2026-33) — supply/demand decomposition

The Canadian decomposition follows Kang, Sekkel, Taskin & Yang (2026), "Supply
and Demand-Driven inflation: Decomposition and policy implications" (Bank of
Canada Staff Analytical Paper 2026-33), which applies Shapiro (2022) to
**quarterly** national-accounts household consumption rather than monthly BEA
PCE. Decisions:

- **Frequency & estimation window.** The paper runs 10-year rolling reduced-form
  VARs with **p = 4 lags** on **quarterly** data. We therefore use
  `DecompConfig(var_lags=4, window=40, periods_per_year=4)`
  (`ism.decomp_ports.QUARTERLY_BASELINE`). The estimation/classification code is
  frequency-free; `periods_per_year` only sets the y/y horizon and the precision
  (ambiguous) SD min-periods floor. The browser twin (`web/decomp_engine.js`)
  takes the same `ppy` and is parity-tested at quarterly frequency
  (`tests/test_decomp_ca_quarterly.py`).

- **Price and quantity.** Price is the category **implicit deflator**
  `p = 100 · nominal / real` from StatCan table **36-10-0124** (current prices ÷
  2017 constant prices); quantity is the 2017 constant-price (chained-volume)
  series — the paper's "real index". Weights are current-price (nominal) shares,
  renormalised each quarter over available leaves (Laspeyres, prior-period
  weights, Eq. 15).

- **y/y aggregation: compounding vs summing.** The paper *sums* the last four
  quarterly contributions to form annual inflation. We keep the Shapiro
  Section 3.1 **running product** (`Π(1+π) − 1`) across all frequencies so the US
  and country ports stay directly comparable. For inflation of a few percent the
  difference is second-order (e.g. four +1pp quarters → 4.06 pp compounded vs
  4.00 pp summed).

- **Category set (99 leaves).** `config/ca_hce_categories.csv` pins 99 leaves =
  116 tree leaves minus 15 "adjusting entry" members and the
  net-expenditure-abroad block (members 125/126/127). The three cannabis leaves
  (2018Q4+) are included but absent until they have a full window, so the
  effective pre-2018 cross-section is ~96 — the paper's count.

- **Goods vs services split (Figs. 3–4).** Each leaf carries a `gs` tag
  (G/S) in `ca_hce_categories.csv`. Durable/semi-durable/non-durable goods →
  **G**; all service categories → **S**. Judgment calls at the boundary
  (e.g. utilities, restaurant meals treated as services; alcohol/tobacco, energy
  products treated as goods) follow national-accounts convention. This tagging is
  ours, not the paper's; the `total` scope does not depend on it.

- **Core scope not reproduced.** The paper's core measure is the Bank of Canada
  **trimmed-mean CPI** (excludes 20% of weighted price changes at each tail), a
  CPI construction that is *not* an HCE partition. We expose Canada **total /
  goods / services** (all HCE) and deliberately omit a Canada "core" scope rather
  than mislabel a different construction. US core (food & energy exclusion) is
  unaffected.

- **Headline overlay.** No published author series exists for Canada, so the
  decomposition's own computed **Total** line is the reference. The dotted
  "Published inflation" overlay is the aggregate implicit-deflator y/y change
  reconstructed from the panel (`_aggregate_yoy` in `export_decomp_data.py`),
  not an external series.

## Canada — ISM momentum backbone (StatCan CPI)

- **Backbone.** StatCan table **18-10-0004** (CPI by product, monthly, NSA,
  Canada = geography member 2), leaf classes capped at tree depth 4 — the
  analogue of the BLS item-strata / ONS class cut. 119 leaves pinned in
  `config/ca_cpi_categories.csv`. The momentum engine is unchanged and monthly.

- **Weights.** Basket weights by vintage (table **18-10-0007**, Canada =
  geography member **1**, whose product member ids differ from 18-10-0004 and are
  aligned by cleaned name). StatCan links basket year *Y* into the CPI in spring
  *Y+1*; we apply vintage-*Y* weights from **June of Y+1**, forward-fill and
  renormalise monthly — a documented simplification (historical link months
  varied). Weight timing only second-orders the index.

## UK / France / Germany — quarterly national-accounts decomposition ports

The same quarterly estimator (`DecompConfig(var_lags=4, window=40,
periods_per_year=4)`, `QUARTERLY_BASELINE`) runs on each country's national
accounts via `ism.decomp_ports` (`build_uk_panels` / `build_fr_panels` /
`build_de_panels`, registered in `PORTS`). Each loader returns
`(nominal, volume, labels)` and `panels_from_nominal_real` turns that into the
implicit-deflator price, chained-volume quantity and nominal-share weights — the
identical `DecompPanels` contract as the US and Canada. Decisions:

- **United Kingdom.** ONS **Consumer Trends** bulk CSV (`ct.csv`): quarterly HCE
  by COICOP with current prices (CP) and chained volumes (CVM), seasonally
  adjusted, from 1955. Class-level leaves capped at `max_depth=2` give ~105
  categories — the finest cross-section among the European ports.

- **France.** INSEE quarterly national accounts, household consumption by product,
  values + chained volumes, SA-WDA, from 1949. **Two cross-sections, one contract:**
  - *Detail (~40 products, default).* INSEE publishes a finer quarterly product
    breakdown than A17, but **only as Excel** ("Consommation des ménages — par
    produit": `t_conso_val.xls` = values, `t_conso_vol.xls` = chained volumes),
    NOT in SDMX/BDM (the quarterly SDMX consumption is A17-only; the finer *annual*
    dataset `CNA-2020-CONSO-MEN` has 582 codes but is annual). `ism.insee` scrapes
    and caches those two files (`fr_hce_panels_detail`, needs `xlrd`); the release
    id changes each quarter (pin in `CONSO_RELEASE`, refresh via
    `scripts/fetch_insee_conso.py`). This lifts France from 17 to ~40 products —
    closer to the UK/Canada cross-sections.
  - *A17 (~17 products, fallback).* The SDMX `CNT-2020-OPERATIONS` P3M panel, always
    available and keyless. `fr_hce_panels(level="detail")` uses the Excel panel and
    **degrades gracefully to A17** when the Excel backbone is unreachable (host
    blocked / no `xlrd` / no cache — e.g. the analysis sandbox), so builds never fail.
  - *Validation.* Nominal is additive, so `validate_conso_vs_a17` cross-checks
    Σ(detailed products) against the A17 total each quarter (small residual gap
    expected). Both cross-sections recover known episodes (e.g. the 1974 oil shock
    peaks aggregate y/y inflation at ~15%).

- **Germany.** Quarterly consumption by **durability** (durable / semi-durable /
  non-durable goods, services — four categories) from **Eurostat**
  `namq_10_fcs` (SCA, nominal `CP_MEUR` + chain-linked real `CLV20_MEUR`), via
  the existing `ism.eurostat` client (`eu_hce_panels`). No API key, reachable
  from CI, from 1991Q1. Confirmed on a live run (2026-07): aggregate y/y
  inflation peaks ~9.3% in 2023Q1 (matching Germany's post-pandemic peak).

  *Why not Destatis?* Germany's national accounts only publish the COICOP
  *purpose* breakdown of consumption **annually**; the **quarterly** split is by
  durability, and Eurostat exposes exactly that in a harmonised, keyless,
  CI-reachable dataset. The Destatis GENESIS client (`ism.destatis`) remains in
  the repo — and its 2025 REST fixes (POST + token in an HTTP header, ZIP
  extraction, `DESTATIS_API_TOKEN`/`DESTATIS_API_KEY`) are kept — but the
  German decomposition port no longer depends on it. `eu_hce_panels` is
  `geo`-parameterised, so the same durability port trivially extends to other
  EU countries (FR/IT/ES/NL/…).

- **No published author overlay.** None of these countries publishes an official
  supply/demand series, so validation is by *internal coherence*
  (`sanity_quarterly_decomp`): the supply+demand+ambiguous split must reconstruct
  the total, the post-pandemic peak must be elevated-but-plausible, and the split
  must be non-degenerate (some quarters supply-led, some demand-led). The dotted
  "Published inflation" overlay is the panel's own aggregate implicit-deflator
  y/y change, as for Canada.

- **Web.** Each is a single scope (`uk` / `fr` / `de`) in the decomposition site's
  Scope selector, quarterly (`ppy=4`), alongside US headline/core and the three
  Canada scopes.

## Japan — quarterly SNA consumption-by-type port

Japan's monthly CPI (the ISM backbone) carries no quantity, so the decomposition
uses the Cabinet Office **quarterly SNA** (四半期別GDP速報 / QE) household final
consumption **by type (form)**, via the existing `ism.estat.EstatClient`
(`jp_hce_panels` → `ism.decomp_ports.build_jp_panels`, `PORTS["jp"]`). Decisions:

- **Tables.** Two current 2020-base, seasonally-adjusted tables, 1994Q1 onward:
  nominal `0003109753` and real (chained) `0003109790`
  (形態別国内家計最終消費支出 名目/実質季節調整系列). Pinned in
  `ism.estat` and documented in `config/sources_japan.yaml`; if a future SNA base
  rebases them, refresh via `getStatsList(statsCode=00100409,
  searchWord="形態別国内家計最終消費支出 …季節調整系列")`.

- **Categories — only four (coarse).** The quarterly SNA offers just four "form"
  leaves: durable / semi-durable / non-durable goods and services (cat01 codes
  15/16/17/18). This is the coarsest cross-section of any port (cf. France's 17);
  the shares are correspondingly lumpy — read them as a broad goods-vs-services
  signal, not a fine decomposition. The total (code 14) and residents-abroad
  adjustments (11/12/13) are dropped. Price = 100·nominal/real (implicit
  deflator); quantity = real chained series; weights = nominal shares.

  *Why not finer (the quarterly ceiling).* Four is not a choice but the hard
  quarterly limit — the same kind of constraint as Germany. The Cabinet Office
  **quarterly** QE breaks household consumption down *only* by form; the richer
  **by-purpose** breakdown (家計の目的別最終消費支出, ~10–13 COICOP-like
  categories, with both nominal and real) exists but is published **annually**
  only (国民経済計算年次推計, 付表 11/12), so it cannot feed a quarterly VAR
  without interpolation. The Family Income and Expenditure Survey (家計調査 /
  FIES) has many categories quarterly but is a **nominal**-only expenditure
  survey — its "real" figures are CPI-deflated growth rates, not chained-volume
  levels, and its per-household survey concept differs from SNA final
  consumption — so it can't supply the nominal+real-chained pair the
  decomposition needs. (The "116 purpose classifications" in the QE methodology
  handbook are internal estimation inputs, not a published quarterly output
  series.) Four form categories is therefore the finest cross-section that is
  simultaneously quarterly, SA, and nominal+real-chained in one SNA framework.

- **Access.** Same free `ESTAT_API_ID` as the CPI backbone; the loader
  self-fetches and caches under `data/raw/estat/`. Without the key the `jp` scope
  is skipped gracefully, like every other port.

- **Validation.** No published author series, so internal coherence
  (`sanity_quarterly_decomp`). Confirmed on an authenticated run (2026-07): 4
  categories × 129 quarters, aggregate y/y inflation peaks ~4.2% in 2022Q4
  (matching Japan's post-pandemic peak) and eases toward ~2% by 2025; the
  supply/demand split reconstructs the total and is non-degenerate.

## Data access

`www150.statcan.gc.ca` is blocked from the hosted analysis sandbox, so the repo
is designed to build from **assembled caches** under `data/raw/statcan/`. Rebuild
them on a machine with open network access with `python scripts/fetch_statcan.py`
(walks `data/raw/statcan/manifest.json`, which is generated from the pinned
category sets). Every builder degrades gracefully — a missing cache skips only
the Canadian gauge/scope and keeps previously committed data.

## US — trimmed mean & median (Cleveland / Dallas replication)

Decisions taken when adding the third model. Full write-up:
`docs/trim_methodology.md`.

- **BEA's underlying-detail price indexes arrive seasonally adjusted.** Measured,
  not assumed: applying our own adjustment to the 2.4.4U panel *lowers* the
  12-month correlation with the Dallas Fed trimmed mean from 0.9970 to 0.9951.
  The `pce` scope therefore declares `sa="none"`. This matters for a trimmed mean
  and not for the ISM index, which differences the panel again — seasonality
  decides who lands in the tails. The `cpi_pipeline` docstring calls the BEA
  panel "NSA" by analogy with the BLS `CUUR` series; that wording is loose and
  is corrected here rather than in the momentum code, whose behaviour does not
  change.

- **`CUSR` where BLS publishes it, `CUUR` otherwise.** BLS seasonally adjusts an
  item stratum only where the seasonal is statistically significant; for the
  rest the published NSA index *is* the adjusted index by their own test. Seven
  of the seventy strata (household insurance, household operations, motor-vehicle
  fees, medical equipment, health insurance, telephone services, personal-care
  services) and three of the 45 Cleveland components fall back this way.
  `BlsFlatFileClient.seasonally_adjusted` reports which, and the website shows
  the count. Treating the missing ones as an error would have dropped 6% of the
  basket.

- **Two CPI cross-sections, not one.** `cpi45` reproduces the Cleveland Fed's
  45-component cut (owners' equivalent rent split into its four census regions);
  `cpi70` keeps this repo's finer 70-stratum partition. The **median** is
  sensitive to the cut and the **trimmed mean** is not — 12-month correlation
  with the published median is 0.997 on `cpi45` and 0.965 on `cpi70`, while the
  16% trim is 0.998 and 0.992. That is a property of the estimators, not a
  defect: a median names a category, a trimmed mean averages over the choice of
  categories. Offering both makes the point visible rather than hiding it behind
  one blessed cut.

- **The regional OER split needs one number BLS does not publish.** Each region's
  owners'-equivalent-rent relative importance is published *within that region's
  own index*, never as a share of the national index. We take the national OER
  relative importance (published) and split it with one observed split — the
  Cleveland Fed's own component table, month recorded in
  `trim_pipeline.OER_SPLIT_ANCHOR` — carried to every December by the four
  regional OER price indexes. Without the split the median replication is 0.965;
  with it, 0.997. The alternative (dropping the split) would have been cleaner
  to source and much less faithful.

- **Seasonal adjustment as a control, not a fixed choice.** `sa="rolling"` uses
  trailing-window month effects and therefore no future data; `sa="dummy"` uses
  the whole sample and is a revised-vintage adjustment. Both are re-centred to
  sum to zero over the twelve calendar months so the annual average cannot move.
  Neither is X-13 — no moving-average seasonal, no outlier detection, no
  trading-day correction — and neither is used for the US scopes, where the
  agencies' own adjustment is available. They exist for the country ports.

- **Presets are the published parameterisations**, not round numbers: 8/8
  (Cleveland 16% trim), 24/31 (Dallas, asymmetric because the PCE cross-section
  is skewed), 50/50 (the weighted median). `optimal_trim()` re-derives them
  against a centred 36-month moving average of headline, which is how the banks
  chose them; `scripts/build_trim.py --optimal-trim` runs it.

- **Partial inclusion at the trim points.** The two categories straddling each
  cut enter with only the slice of their weight inside the retained interval.
  Without it the estimate jumps every time a trim point crosses a category
  boundary, which would make the trim sliders on the website meaningless. Both
  Reserve Banks do this; `test_partial_inclusion_makes_the_trim_continuous`
  guards it.

## US — versioned CPI weights

- **Price-updated December anchors, not a static vector.** `config/cpi_ri_by_year.csv`
  pins the published December relative importance for 1997-2025 and
  `cpi_ri.price_updated_weights` carries each anchor across the following year by
  the categories' own price changes. Within a weight regime this is BLS's actual
  method, and the repo verifies it: in the non-update years of the biennial
  regime the price-updated and published December weights agree to ~0.02pp summed
  across seventy strata. The old static Dec-2023 vector stays the default for the
  **ISM** backbone (which renormalises and is insensitive) and the versioned
  panel is used by the trimmed mean, where the weights decide the trim points.

- **1997 is the earliest usable anchor.** The CPI item structure was revised in
  January 1998; the December 1987-1996 tables use the old structure and cannot be
  mapped onto the `SE*` strata at all. Earlier months are back-updated from the
  1997 anchor, which holds the 1997 basket fixed in real terms — relative price
  drift is captured, genuine basket change is not. `weights_source` labels every
  month and the site says so rather than presenting 1960s weights as anchored.

- **Label drift is aliased, one real break is re-cut.** BLS renamed several lines
  in the Dec-2009 table (OER "of primary residence" → "of residences", "Gas
  (piped) and electricity" → "Energy services", "Recreation services" → "Other
  recreation services"); these are printing changes and are handled by
  `HISTORICAL_LABEL_ALIASES`. The medical-commodities branch is a genuine break —
  it switched from prescription/non-prescription to drugs/equipment — and the old
  lines are re-cut onto the new boundary, leaving ~0.1% of the index on the wrong
  side before 2009. Matching is case- and whitespace-insensitive so pure
  typography (the 1998 table's double space, a capital "I" in "Health Insurance")
  never breaks a join.

- **Late-born strata are back-updated, not dropped.** "Information technology,
  hardware and services" first appears in the Dec-2003 table. Reindexing on the
  whole-table anchor would have silently removed it from every earlier
  cross-section; instead the per-key anchor search back-updates it from 2003.

## US — CPI to PCE

- **Groups, not a line-by-line map.** The two classifications are not nested, so
  `config/cpi_pce_concordance.csv` maps both sides into 28 common groups. A
  coarser map that is right beats a finer one that is quietly wrong in a dozen
  places.

- **Four groups are flagged `scope`, not `common`.** Health, household and
  motor-vehicle insurance (PCE measures net insurance and employer-paid spending;
  the CPI measures the household premium) and financial services (PCE imputes
  FISIM; the CPI has no counterpart). Averaging them into a common group would
  hide the largest single structural difference between the gauges.

- **The identity telescopes; the C-CPI-U proxy is kept out of it.** The six terms
  are each one substitution in a chain from the published CPI to the published
  PCE, so they sum to the gap by construction (checked to 4e-16). The textbook
  formula-effect proxy — CPI-U minus C-CPI-U — is reported as a diagnostic only:
  chaining a published index between two aggregates of our own makes the formula
  and residual lines cancel, which looks tidy and means nothing. The formula
  effect in the identity is measured directly, as a fixed-weight aggregate of the
  PCE categories against the published Fisher chain.

- **The bridge never sees the month it predicts.** Each group's rolling
  regression is fitted on the trailing window *excluding* month t, because on CPI
  day month t's PCE has not been published.
  `test_bridge_uses_no_contemporaneous_pce` enforces it by tampering with the
  last month's PCE and asserting the implied value does not move. Scope groups
  are carried at their own trailing 12-month mean — deliberately dumb, and
  labelled as such, rather than pretending FISIM can be forecast from CPI data.

## Wage model (model 5) — indexation, statutory floors and handouts

Non-obvious judgment calls in `src/ism/wage_*.py`. The equations are mapped to
code in `docs/wage_methodology.md`; the paper is `paper/wage_inflation.md`.

### Specification

- **Year-on-year, not annualised quarterly.** Bernanke & Blanchard estimate on
  annualised quarterly growth because their wage measure is the Employment Cost
  Index, a fixed-weight quarterly index built for that. Outside the United
  States there is no ECI. Compensation per employee, OECD hourly earnings and
  average weekly earnings all carry enough quarter-to-quarter measurement noise
  that their annualised quarterly growth is close to white, and estimated on
  them the wage equation returns a *negative* sum of own-lag coefficients — the
  signature of differencing noise. The panel is therefore four-quarter log
  changes throughout. The cost is overlapping observations and serially
  correlated residuals, so the reported standard errors understate uncertainty;
  this is why the paper leans on coefficient sums and sign tests rather than on
  individual t-statistics. `gp_q` and `gw_q` keep the quarterly variants so the
  choice can be inspected.

- **A real-wage gap, not an inflation surprise, as the catch-up term.**
  Reproducing B&B's catch-up without a survey expectation — realised inflation
  minus a filtered trend — makes it an exact linear function of the trend's own
  lags, because a fixed-gain filter implies
  `pi_t = pi*_{t-1} + (pi*_t - pi*_{t-1})/k`. In this panel that produced
  catch-up coefficient sums of +54 at `k = 0.2`, i.e. 1/k times noise. The term
  is instead the deviation of the log real wage from its own one-sided local
  linear trend, which is the object B&B's own Eq. (2) describes (an aspiration
  real wage) and which DeLuca & Van Zandweghe (2023) argue for directly. The
  surprise version is retained as `catchup_bb` so the collinearity can be
  demonstrated rather than asserted.

- **The interaction, not a time-varying parameter.** Theory and euro-area
  evidence both say the catch-up coefficient should be state-dependent. Rather
  than filter a latent time-varying parameter, the state is made observable:
  `lambda_t` is built from a documented institutional coverage database and
  interacted with the catch-up term. Cost: `lambda`'s four channel elasticities
  are calibrated from the literature, not estimated, so they are exposed as
  controls on the site and the result should be read as conditional on them.

- **Pooled, with country fixed effects.** Within a country `lambda` moves
  slowly over a narrow range — 0.02 to 0.13 across sixty-five years of US data
  — so the interaction is barely identified from any one time series. Belgium,
  Italy and Spain are carried as reference countries purely to widen that
  range to 0.02–1.00. Belgium and Germany share a currency, a central bank and
  the 2022 energy shock and differ in exactly the institution under study.

- **Three-year gains, not long-run multipliers.** The homogeneity restriction
  sets the price equation's long-run pass-through to exactly 1 whatever the
  data say — that restriction *is* the vertical-Phillips-curve assumption — so
  the long run cannot distinguish regimes. Three years is the horizon the
  euro-area sectoral pass-through literature reports.

- **Gauss-Jordan, not `pinv`.** `_inv` is elimination with partial pivoting and
  a trace-scaled ridge, mirrored line for line in `web/wage_engine.js`, because
  the browser twin is parity-tested to 1e-9 and there is no SVD in JavaScript.

- **The monetary rule in the simulator is a slack response, not a Taylor
  rule.** The estimated wage equation takes slack, not the policy rate; a rate
  rule would need an IS curve that has not been estimated.

### Data

- **The effective US minimum wage.** The federal floor has been $7.25 since
  2009, so a series using it alone says the American wage floor has been frozen
  for seventeen years. It has not been, for most American workers: the binding
  minimum is the higher of the federal and the state rate, and by 2026 roughly
  three fifths of US employment is in a state with a higher one.
  `effective_us_minimum_wage` builds an employment-weighted index from FRED's
  `STTMINWG<ST>` and `<ST>NA` series. States whose series are unavailable fall
  back to the federal rate, which biases the index down, never up. This is the
  most consequential construction in the US data and the reason the US
  minimum-wage channel is not identically zero after 2009.

- **Transfers as a share, cyclically adjusted.** `h` is the four-quarter change
  in cash transfers as a *share* of household disposable income, not a deflated
  flow: seven national accounts in six currencies and three base years make a
  share the only unit in which a coefficient is comparable, and a units error
  in one source cannot silently rescale it. It is then projected on the
  contemporaneous and four lagged changes in the unemployment rate and the
  residual kept, because total transfers are dominated by automatic
  stabilisers — unemployment insurance rises in recessions, when inflation is
  falling — and enter a price equation with a spurious negative sign otherwise.

- **Price measures are a CPI wedge, not income.** A cap, tariff freeze or
  excise cut lowers the recorded index while in force and raises it on expiry;
  it does not add to nominal household income. It therefore appears in
  `config/wage_cpi_wedge.csv` and in the subsidy-neutral deflator, never in
  `h`. Income measures are the reverse. Germany's Inflationsausgleichsprämie is
  a third case — paid through the payslip, so it raises measured wage growth
  without raising the wage base — and is tagged `wage`.

- **French series.** An earlier version pulled the French CPI and base-wage
  index from INSEE BDM idbanks chosen by name. Two of the three were wrong: one
  resolved to a business-climate survey and two to series INSEE has since
  stopped (the base-2015 CPI, retired on the rebasing to 2025). The French real
  wage consequently appeared to fall 11% between 2019 and 2022 instead of about
  2.5%. Guessing an identifier from a series name is not a data source.
  Everything except the SMIC now comes through the harmonised Eurostat/OECD
  path, and the SMIC idbank is verified against the series title INSEE's own
  SDMX endpoint returns and against the published rate of €12.31 from 1 June
  2026.

- **German negotiated wages are not used.** Destatis's Tarifverdienstindex is
  the right series — it is published both including and excluding one-off
  payments, which is exactly what is needed to separate the
  Inflationsausgleichsprämie from base pay — but Genesis-Online serves it only
  behind a session API, so it cannot go in a keyless pipeline. German measured
  wage growth in 2023–24 therefore includes the tax-free bonus, which is
  precisely the measurement problem the model is about. Stated in the paper
  rather than hidden.

- **Uprating rules are implemented, not looked up.**
  `config/wage_uprating.csv` is a validation target, not an input: the pipeline
  applies each statute to observed data and `ism.wage_validate` checks the
  result against the decisions actually announced. Three of the four rules are
  applied to a slightly different index from the statutory one (the French rule
  wants the national CPI excluding tobacco, the German formula wants two
  dampening factors no keyless source publishes quarterly, the UK triple lock
  wants total pay including bonuses), so the tolerance is 0.35pp and the gap is
  reported rather than hidden.

- **Belgian and Italian benefit indexation is approximated.** Belgium indexes
  to the *health index* (CPI excluding alcohol, tobacco and motor fuels) and
  Italy to a forecast index excluding imported energy. Neither is in this
  pipeline, so both are treated as wage-linked in `benefit_index`. They are
  reference countries, and the approximation touches only their effective wage
  index, not their `lambda` or their entry in the pooled regression.

- **Slack is the unemployment gap by default, not v/u.** The
  vacancy-to-unemployment ratio is the better measure post-2020 and is Bernanke
  & Blanchard's choice, but it exists only from 2001 for the UK and the US.
  Making it the default would cut the UK sample from 1963 to 2001 and discard
  the 1973–74 threshold-agreement episode, which is the UK's whole contribution
  here. It is carried as `slack_vu` and the site can switch to it.

### What is not validated

There is no published counterpart to this model — no central bank publishes a
spiral gain or an effective wage index — so validation is four weaker checks
rather than one strong one: the statutory uprating rules against announced
decisions, similarity to Bernanke & Blanchard's coefficient sums, internal
coherence, and known institutional facts (the UK's 1974 spike, Belgium's flat
unity, the US COLA decline by a factor of six, and the survival of the SMIC
formula through the 1983 désindexation). The B&B comparison is a *similarity
check, not a replication*: an exact one needs the ECI back to 1990 (BLS API,
keyed) and the Barnichon composite help-wanted index (a manual download),
neither of which is available keylessly.

`tests/` is gitignored in this repository, so `tests/test_wage_engine.py` and
`tests/test_wage_parity.py` live locally only. The parity test is what makes
`web/wage_engine.js` trustworthy; if the tests are ever committed, that is the
one to commit first.
