# Port decisions

Non-obvious modelling and data judgment calls made when porting the two FRBSF
models to other countries. Referenced from the source docstrings and the
`config/sources_*.yaml` registries.

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

- **France.** INSEE quarterly national accounts, household consumption by product
  (**A17**, ~17 products), values + chained volumes, SA-WDA, from 1949. This is a
  deliberately **coarse** cross-section (17 vs 96–105 elsewhere); read the shares
  with that in mind. It still cleanly recovers known episodes (e.g. the 1974 oil
  shock peaks aggregate y/y inflation at ~15%).

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
