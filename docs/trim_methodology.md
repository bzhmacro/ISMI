# Trimmed-mean and median inflation — maths → code

The third model in this repo: the limited-influence estimators behind the
Cleveland Fed's **median CPI** and **16% trimmed-mean CPI** and the Dallas Fed's
**trimmed mean PCE**, rebuilt from the category cross-section, validated against
the published series, and exposed as a live page.

Read it beside `src/ism/trim_engine.py`; every equation number below is a
section heading in that file.

---

## 1. The object

Headline inflation is the expenditure-weighted **mean** of the cross-section of
category price changes. That cross-section is fat-tailed and skewed, so its mean
is a high-variance estimator of its own central tendency: a single category
moving 40% can add a tenth of a point to a monthly print without telling you
anything about inflation in general.

A **limited-influence estimator** answers the same question with a statistic
that the tails cannot move. Sort the categories by their price change, line them
up along their expenditure weight, discard the lowest α and the highest β of that
weight, and average what is left. α = β = 0 is the mean; α = β = 0.5 is the
weighted **median**; the published measures sit in between.

---

## 2. The chain (Eqs. T1–T4)

### (T1) Seasonal adjustment

    π^sa_{i,t} = π_{i,t} − s_{i,m(t)}

Month effects `s_{i,m}` are estimated per category and re-centred to sum to zero
over the twelve calendar months, so removing them cannot move the annual
average. Three estimators, chosen with `sa=`:

| `sa` | what it does | when to use it |
|---|---|---|
| `none` | pass through | the panel already arrives adjusted |
| `dummy` | month effects from the whole sample | a revised, final-vintage adjustment |
| `rolling` | month effects from the trailing `sa_window` periods | real-time; lets the seasonal drift |

This is a transparent stand-in for X-13, not a replacement: it has no moving
average of the seasonal, no outlier detection, no trading-day correction. **For
the US scopes it is not used at all** — see §4.

### (T2) Annualisation

    a_{i,t} = 100 · ((1 + π^sa_{i,t}/100)^P − 1)      ("compound", the agencies')
    a_{i,t} = P · π^sa_{i,t}                          ("log", exactly additive)

### (T3) The trim

Sort by `a`, form the cumulative normalised weight, and average the mass lying
in (α, 1−β):

    m_t = Σ_{i∈R} w̃_{i,t} a_{i,t} / Σ_{i∈R} w̃_{i,t}

The two categories straddling each trim point enter **partially** — only the
slice of their weight inside the retained interval counts. That is not a detail:
partial inclusion is what makes the estimator continuous in α and β (otherwise
the answer jumps every time a trim point crosses a category boundary), and it is
what both Reserve Banks do. `test_partial_inclusion_makes_the_trim_continuous`
guards it.

Partial inclusion has a consequence worth stating, because getting it wrong is
easy and invisible: a category straddling a trim point is **neither cut nor
included**. On the shipped panels at the published trim points, the straddling
category has contributed as much as 17% of the basket while most of its own
weight sat in a tail. The cross-section chart therefore colours four states, not
three — cut from the bottom, counted, cut from the top, and **at the trim point
(partly counted)** — which is the same distinction the Dallas Fed's published
component table draws when it marks a row "Trim point".
`retained_weight()` returns the share each category actually contributed, and
`test_retained_weight_reconstructs_the_trimmed_mean` asserts those shares
reproduce the headline number exactly, so the picture and the figure come from
one calculation.

α + β = 1 degenerates to the weighted median: the value of the category holding
the 50th percentile of the weight — *a real category's own price change*, never
an interpolation, which is why the Cleveland Fed can name the median component
each month.

### (T4) Chaining

De-annualise back to a period rate, compound into an index, and take the
12-month change of the index:

    I_t = I_{t−1} · (1 + m_t/100)^(1/P)

The 12-month trimmed mean is therefore **the 12-month change of the chained
index**, not a trim of the cross-section of 12-month changes. The two are
different objects and the second is noisier; the published series are the first.

---

## 3. Choosing the trim

The trim fractions are not an aesthetic choice. `optimal_trim()` grid-searches
them against a centred 36-month moving average of headline inflation — the
standard stand-in for the unobservable trend — which is how the Dallas Fed
arrived at cutting **24% from the bottom and 31% from the top**. The asymmetry
falls out of the data rather than being imposed.

`scripts/build_trim.py --optimal-trim` re-runs the exercise on any scope. Note
that the reference is *centred*, so it uses future data: this is an in-sample
calibration, not a real-time rule.

---

## 4. The scopes, and what makes each faithful

| scope | cross-section | prices | weights |
|---|---|---|---|
| `cpi45` | 45 components, OER split by census region | BLS `CUSR*` (SA), `CUUR*` where BLS publishes no SA series | December relative importances, price-updated monthly |
| `cpi70` | the repo's 70 CPI item strata | same | same |
| `pce` | 130 BEA fourth-level categories | BEA 2.4.4U (already SA) | monthly nominal shares, BEA 2.4.5U |
| `uk` | 85 ONS COICOP classes | ONS MM23, NSA | ONS annual weights (per mille) |
| `ca` | 119 StatCan leaf classes | table 18-10-0004, NSA | StatCan basket-vintage weights |
| `de` `fr` | 130 / 127 Eurostat ECOICOP items | `prc_hicp_minr`, NSA | annual HICP item weights |
| `jp` | 47 e-Stat medium groups | 2020-base CPI, NSA | static 2020-base weights |

Three things had to be measured rather than assumed, and each one mattered:

**BEA's underlying-detail price indexes are already seasonally adjusted.**
Applying our own adjustment on top *lowers* the fit to the Dallas Fed series
(12-month correlation 0.9970 → 0.9951). The `pce` scope therefore declares
`sa="none"`. The ISM momentum model differences these panels again and is
insensitive to this; a trimmed mean is not, because seasonality decides who
lands in the tails.

**BLS does not seasonally adjust every stratum.** It publishes a `CUSR` series
only where the seasonal is statistically significant; for the rest the NSA index
*is* the adjusted index by BLS's own test. Seven of the 70 strata and three of
the 45 Cleveland components are in that position, and the pipeline falls back
rather than treating them as missing.

**Splitting owners' equivalent rent by region is the single biggest fidelity
win for the median.** OER is roughly a quarter of the CPI, so with the stratum
whole it *is* the median in most months and the measure barely moves. The
Cleveland Fed splits it into four census regions of 5–9% each. Doing the same
takes the 12-month correlation with the published median from 0.965 to **0.997**.

### 4b. The five foreign gauges — and whether their cross-sections can carry a trim

The other two models on the site already ship category panels for the UK,
France, Germany, Japan and Canada, so the trimmed mean gets them for the cost of
a scope entry. Whether that is *worth* doing is a separate question, and it is
not answered by the component count. A trim is only as informative as the
cross-section it cuts: if one component outweighs the tail fraction, the tail is
that component's price and the estimator has relabelled one series rather than
averaged anything away.

`cross_section_conditioning()` measures it at a reference 8/8 cut, and the page
prints the answer under the header. Effective breadth is `1 / Σw²` on the latest
weights; the tail figures are ten-year means of how many components each tail
actually cuts through, counting a straddling component for the part of its
weight that falls inside — the same partial accounting the estimator uses.

| scope | components | effective breadth | heaviest | an 8% tail spans | largest share of a tail |
|---|---:|---:|---|---:|---:|
| `de` | 130 | **48.7** | rents 6.8% | 12.2 / 10.8 | 46% |
| `fr` | 127 | **41.0** | restaurants 7.7% | 11.9 / 10.7 | 43% |
| `ca` | 119 | **38.3** | rent 7.4% | 13.7 / 12.4 | 41% |
| `uk` | 85 | **29.8** | restaurants 11.0% | 10.4 / 9.9 | 38% |
| `pce` | 130 | 26.0 | imputed rent 12.0% | 20.3 / 17.8 | 33% |
| `cpi45` | 45 | 21.9 | OER (South) 9.1% | 7.3 / 6.6 | 48% |
| `jp` | 47 | **16.7** | rent 18.3% | 5.1 / 5.0 | **53%** |
| `cpi70` | 69 | **10.9** | OER 26.1% | 11.9 / 10.2 | 48% |

Read it two ways. Germany, France and Canada are the best-conditioned gauges on
the site — nothing in them outweighs an 8% tail at all. The UK sits comfortably
above every US cut. Japan is the weakest: 47 medium groups with rent at 18%, so
an 8% tail is barely five components and half of it is whichever single one
leads it.

`cpi70` is the instructive case for why breadth alone is not the test. Its
effective breadth is the worst here (10.9, because owners' equivalent rent is a
quarter of the basket), yet its tails span about eleven components — OER
habitually sits in the *middle* of the distribution and never reaches an edge.
It hurts the **median**, which is a claim about which category sits at the 50th
percentile, far more than the trimmed mean. Hence the two columns.

### 4c. Which of them have ground truth

| scope | published measure | same construction? |
|---|---|---|
| `ca` | Bank of Canada **CPI-trim** (20% each tail), **CPI-median** | yes — monthly cross-section, chained |
| `jp` | Bank of Japan **10% trimmed mean**, weighted median, mode | **no** — the Bank trims the *twelve-month* cross-section |
| `uk` `fr` `de` | none | — |

Canada is a real replication target. Two documented differences remain and both
show up in the bias: the Bank's inputs are adjusted for changes in indirect
taxes and seasonally adjusted with StatCan's own per-series specifications,
while ours are the published NSA index with this engine's rolling seasonal.

Japan is an overlay, not a test. The Bank of Japan trims the cross-section of
year-over-year changes (BoJ Review 2015-E-6, Chart 4); this engine trims the
monthly one and chains. The Bank also strips "institutional factors" — the
consumption-tax changes, the free-education policies, the 2021 mobile-phone
cuts, travel subsidies, energy-cost relief — that the official CPI we trim still
contains. The two lines agree to 0.94 anyway, which is a statement about how
little the choice of basis matters at the twelve-month horizon, not a
replication claim.

For the UK there is nothing to check against: the ONS publishes no
limited-influence measure. Nor is there one for France or Germany —
**the ECB's trimmed means are computed for the euro area as a whole** (ICP item
codes `TRIM05`–`TRIM50`, where the number is the *total* trim, under institution
code 3), not per member state, and as of September 2026 their last observation
is December 2025, the same month Eurostat froze the ECOICOP v1 datasets. A
euro-area scope would come with ten published trim fractions to check against
and is the obvious next addition; it needs an `EA20` backbone the ISM export
does not currently build.

---

## 5. Versioned weights

The CPI has no monthly expenditure series. A single static relative-importance
vector is fine for a diffusion index that renormalises anyway, but not for a
trimmed mean, where the weights *decide where the trim points fall*. Using 2023
weights to locate the trim point in 1975 puts a 2023-sized shelter weight and a
2023-sized (tiny) food weight into a 1975 cross-section.

`src/ism/cpi_ri.py` rebuilds the weight path the way BLS computes it:

    RI_{i,t} = RI_{i,Dec Y} · (P_{i,t} / P_{i,Dec Y})   / (normalise)     (W1)

anchored on the published December table for each year from 1997 and restarted
at each new anchor. Within a weight regime this is **not an approximation — it
is BLS's method**, and the repo checks it: in the non-update years of the
biennial regime (2012, 2014, 2016, 2018, 2020) the price-updated December weight
and the published December weight agree to about 0.02pp summed across all 70
strata. In the update years the difference is 5–8pp, and that difference *is* the
weight-update effect, reported by `weight_update_effect()`.

Coverage and its limits:

* **1997 onwards** — anchored on published December tables. The CPI item
  structure was revised in January 1998, so December 1997 (the `USRINEW` table)
  is the first one whose names map onto the `SE*` strata.
* **before 1998** — back-updated from the 1997 anchor by running (W1) in
  reverse. This holds the 1997 basket fixed in real terms: it captures relative
  *price* drift but not the genuine basket changes of the 1970s and 1980s. The
  payload carries a `weights_source` label per month and the website says so.
* **label drift** — BLS renamed several lines in the Dec-2009 table
  ("Owners' equivalent rent of primary residence" → "…of residences", "Gas
  (piped) and electricity" → "Energy services", "Recreation services" → "Other
  recreation services"). These are printing changes, not series changes, and are
  handled by `HISTORICAL_LABEL_ALIASES`. One is a **real** break: the medical
  commodities branch switched from prescription/non-prescription to
  drugs/equipment in Dec-2009, and the old lines are re-cut onto the new
  boundary. About 0.1% of the index sits on the wrong side of that line before
  2009.

The four **regional OER** weights are the one number BLS does not publish: each
region's OER relative importance is given *within that region's own index*,
never as a share of the national index. We take the national OER relative
importance (published) and split it with one observed split — the Cleveland Fed's
own component table — carried to every December by the regional OER price
indexes. `OER_SPLIT_ANCHOR` records the month.

The website exposes all of this as a **weight vintage** control: `versioned`,
`latest` (freeze today's vector) and `first`. Switching to `latest` is the
fastest way to see what the shortcut costs.

---

## 6. Validation

`python scripts/build_trim.py` prints the comparison table. Against the
published series, 1998 onward (the span where the Cleveland revised vintage and
the current Dallas methodology both apply):

| scope | measure | horizon | corr | RMSE (pp) | bias (pp) |
|---|---|---|---:|---:|---:|
| `cpi45` | median CPI | 1-month | 0.971 | 0.316 | −0.002 |
| `cpi45` | median CPI | 12-month | **0.997** | 0.083 | 0.000 |
| `cpi45` | 16% trim | 1-month | 0.991 | 0.223 | +0.089 |
| `cpi45` | 16% trim | 12-month | **0.998** | 0.114 | +0.084 |
| `cpi70` | median CPI | 12-month | 0.965 | 0.419 | +0.224 |
| `cpi70` | 16% trim | 12-month | 0.992 | 0.225 | +0.145 |
| `pce` | trimmed mean PCE | 1-month | 0.965 | 0.273 | +0.066 |
| `pce` | trimmed mean PCE | 12-month | 0.990 | 0.127 | +0.063 |

On the full Dallas sample (1980–) the PCE 12-month correlation is 0.997.

The two foreign scopes with published counterparts, on the same basis:

| scope | measure | horizon | corr | RMSE (pp) | bias (pp) |
|---|---|---|---:|---:|---:|
| `ca` | CPI-trim (20/20) | 12-month | 0.963 | 0.315 | +0.181 |
| `ca` | CPI-median | 12-month | 0.929 | 0.369 | +0.087 |
| `jp` | 10% trimmed mean | 12-month | 0.942 | 0.408 | +0.178 |
| `jp` | weighted median | 12-month | 0.754 | 0.445 | +0.141 |

These are looser than the US scopes and should be, for the reasons in §4c: the
Canadian inputs are tax- and seasonally adjusted differently, and the Japanese
measures are built on a different cross-section altogether. The Japanese
*median* is the weakest of the four, which is the §4b point made twice — a
median asks which single category sits at the 50th percentile, and a 47-group
partition with rent at 18% is the worst cross-section here to ask it of.

`cpi70` tracking the published **median** less well is not a defect. A median is
a statement about *which category* sits at the 50th percentile, so it moves when
you re-cut the cross-section; a trimmed mean averages over that choice and is
correspondingly robust. That contrast is why both cuts are offered.

Two sharper checks are available:

* `build_trim.py --cross-section` joins our latest-month cross-section onto the
  bank's own published component table by name. If a weight is wrong you see
  *which one*, rather than inferring it from a drift in the index.
* `tests/test_trim_parity.py` runs the Python engine and its browser twin
  (`web/trim_engine.js`) over a grid of configurations and asserts they agree to
  1e-9, so the website's numbers are the repo's numbers.

---

## 7. Sources

| what | where | key? |
|---|---|---|
| CPI item indexes, SA and NSA | `download.bls.gov/pub/time.series/cu/` | no |
| Chained CPI (C-CPI-U) | `download.bls.gov/pub/time.series/su/` | no |
| December relative importances 1997– | `bls.gov/cpi/tables/relative-importance/` | no |
| Median CPI and 16% trimmed mean | `clevelandfed.org/.../usinflationdata.zip` | no |
| Cleveland component table | `clevelandfed.org/.../mediancpi_component_table.csv` | no |
| Trimmed mean PCE history and detail | `dallasfed.org/.../pcehist.xlsx`, `detail.xlsx` | no |
| CPI-trim and CPI-median (Canada) | `statcan.gc.ca/n1/tbl/csv/18100256-eng.zip` | no |
| BoJ core indicators (Japan) | `boj.or.jp/en/research/research_data/cpi/cpirev.xlsx` | no |
| PCE category prices and expenditure | BEA 2.4.4U / 2.4.5U | yes (or the committed `web/data/ism.json`) |

Nothing here needs a key. `download.bls.gov` returns **403** to the default
`python-requests` user-agent — the repo's `USER_AGENT` (a name plus a contact
URL, which is what BLS asks for) is accepted. That trap is documented on
`BlsFlatFileClient`.

---

## 8. Running it

```bash
python scripts/build_cpi_ri.py        # refresh the December weight anchors (once a year)
python scripts/build_trim.py          # build every scope + validate vs the banks
python scripts/build_trim.py --cross-section --optimal-trim
python scripts/export_trim_data.py    # refresh web/data/trim.json
python scripts/export_trim_data.py uk ca      # or a subset -- BUT this REWRITES
                                             # trim.json with only those scopes
python -m pytest tests/test_trim_engine.py tests/test_trim_parity.py \
                tests/test_trim_foreign.py
```
