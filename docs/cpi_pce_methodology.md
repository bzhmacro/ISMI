# CPI → PCE — maths → code

Why the two US inflation gauges print different numbers, as an exact monthly
identity; and what a CPI print implies for the PCE print that follows it.

Read it beside `src/ism/cpi_pce.py`.

---

## 1. Why it matters

The Fed targets PCE. The market trades CPI, which arrives about two weeks
earlier. Since 2000 PCE inflation has run about **0.34pp below** CPI inflation
on average — but that average hides a spread from −0.5pp to +1.7pp, and the
months when the wedge blows out are exactly the months when reading one gauge as
a proxy for the other goes wrong.

The wedge is not noise. It is four measurable differences, and each one is a
different trade.

---

## 2. The concordance

`config/cpi_pce_concordance.csv` assigns all 70 CPI item strata and all 130 PCE
categories to **28 common groups** plus a handful of scope groups.

Grouping rather than matching one-to-one is deliberate. The two
classifications are not nested: CPI's "Public transportation" spans PCE's
ground, air and water transportation; PCE's "Household furnishings and
operations" swallows CPI's housekeeping supplies *and* household operations *and*
domestic services. A group cut coarse enough to be honest beats a line-by-line
map that is quietly wrong in a dozen places.

Four groups carry `role = scope` rather than `common`, because the two gauges
measure genuinely different things there:

| group | CPI measures | PCE measures |
|---|---|---|
| `health_insurance` | the household premium net of benefits | employer- and government-paid spending, valued at the insurers' margin |
| `household_insurance` | the premium | premiums less benefits paid |
| `vehicle_insurance` | the premium | premiums less benefits paid |
| `financial_services` | *(nothing)* | fees **plus** imputed services banks provide without charging (FISIM) |

Plus `out_of_scope`: employer-furnished meals, military clothing, farm output
eaten on the farm, nonprofit social services, spending abroad. Together these
are most of the reason PCE covers far more than household out-of-pocket
spending, and a large part of why PCE inflation sits below CPI inflation.

`test_concordance_covers_every_category_exactly_once` fails if a category ever
falls out of the map — which would silently reweight every group it belonged to.

---

## 3. The decomposition (Eqs. C1–C6)

Take the two published 12-month rates and build five aggregates of our own,
each differing from the next by **exactly one substitution**:

    A_all    CPI prices, CPI weights, every group
    A_CPI    CPI prices, CPI weights, common groups only
    A_PCEw   CPI prices, PCE weights, common groups only   ← weights changed
    B_PCE    PCE prices, PCE weights, common groups only   ← prices changed
    B_all    PCE prices, PCE weights, every group

Then

    π_CPI − π_PCE =  (π_CPI − A_all )   rebuild residual     (C1)
                   + (A_all  − A_CPI )   coverage effect     (C2)
                   + (A_CPI  − A_PCEw)   weight effect       (C3)
                   + (A_PCEw − B_PCE )   price-measure effect(C4)
                   + (B_PCE  − B_all )   scope effect        (C5)
                   + (B_all  − π_PCE)   formula effect      (C6)

Six terms, summing to the gap by construction. No fitting, nothing to tune.
`GapResult.check()` returns the largest violation; on the live data it is
4e-16.

### What each term is

**(C1) rebuild residual.** Our 28-group aggregate of CPI strata against the
published CPI-U: lower-level formula differences and whatever the group cut
costs. Reported, not hidden — it averages −0.13pp and has run near zero since
2024. A residual that starts drifting means the concordance needs attention.

**(C2) coverage.** The CPI lines with no comparable PCE counterpart (the
insurance premiums). +0.05pp on average, +0.09pp through the 2010s.

**(C3) weight.** Identical price changes, PCE's expenditure shares instead of
CPI's. Shelter is the story:

| group | CPI weight | PCE weight |
|---|---:|---:|
| Owners' equivalent rent | 26.2% | 12.0% |
| Rent of primary residence | 7.8% | 3.9% |
| Medical services | 6.1% | 17.6% |
| New and used vehicles | 7.1% | 2.9% |

Shelter is roughly a third of the CPI and a sixth of PCE, so a shelter move hits
CPI about twice as hard. The 2021–22 rent surge pushed this term to **+1.56pp in
March 2022** — on its own more than four times the average gap — and then took
it negative as rents cooled. Averaged over 2000–2026 it is +0.02pp, which is
exactly why the average is the wrong thing to look at.

**This term is also the reason the versioned CPI weights exist.** Run it with a
static weight vector and you are measuring 2023's shelter share in every year.

**(C4) price-measure.** Same weights, different price data for the same
spending. +0.44pp on average and the most persistent term. It is mostly medical
care: PCE prices hospital and physician services largely from the producer price
index and counts what insurers actually pay, while the CPI prices what a
household is billed.

**(C5) scope.** What the PCE-only groups do to the PCE total: −0.13pp on
average, −0.25pp through the 2010s.

**(C6) formula.** A fixed-weight aggregate of the PCE categories against the
published Fisher-chained PCE index — the cost of the aggregation formula,
measured rather than assumed. +0.10pp on average.

### On the C-CPI-U proxy

The textbook proxy for the formula effect is published CPI-U minus the chained
C-CPI-U (+0.26pp on average since 2000). It is reported as `ccpi_proxy` and
deliberately kept **out** of the identity: chaining a published index between two
aggregates of our own makes the formula and residual lines cancel each other,
which looks tidy and means nothing. It is a diagnostic, not a term.

---

## 4. The bridge

For each common group and each month t, fit on the trailing `window` months
**excluding t itself**

    π^PCE_{g,s} = a_{g,t} + b_{g,t} · π^CPI_{g,s}

and apply it to month t's CPI. Excluding t is what makes this a nowcast rather
than a fit: on CPI day, month t's PCE has not been published.
`test_bridge_uses_no_contemporaneous_pce` enforces it by tampering with the last
month's PCE and asserting the implied value does not move.

Scope groups have no CPI input by construction, so they are carried at their own
trailing 12-month average. That is deliberately dumb: pretending to forecast the
imputed-financial-services deflator from CPI data would be worse than admitting
it is a standing assumption. Their combined weight is about a fifth of PCE, and
the error bands include everything that goes wrong there.

Performance: monthly RMSE **0.121pp**; 12-month correlation 0.977 and RMSE
0.336pp since 2000.

### The pass-through column

The fitted slope answers "how much of a 1pp move in this group's CPI subindex
turns up in the PCE deflator for the same spending?".

| group | slope | why |
|---|---:|---|
| Shelter (rent, OER) | 1.00 | PCE takes the number straight from the CPI |
| Food at home, apparel, energy, vehicles | 0.95–1.03 | same source, same method |
| Personal care, vehicle services, education | 0.76–0.83 | partly other sources |
| Communication | 0.49 | different quality adjustment and scope |
| Public transport | 0.35 | air fares priced differently |
| Recreation services | 0.32 | large non-market and imputed component |
| **Medical services** | **0.31** | PPI-sourced, insurer-paid rather than billed |

A slope far below 1 marks a row where the two gauges have stopped being the same
measurement. Those rows are where a CPI surprise does *not* mean a PCE surprise —
which, given medical services is 17.6% of PCE against 6.1% of the CPI, is most
of the reason CPI-day moves in PCE expectations are often wrong.

---

## 5. What this does not do

* **No real-time vintages.** Everything uses the latest published data. A
  genuine reconstruction of what a given CPI day implied at the time would need
  an ALFRED-style vintage store on both sides.
* **The PCE source tagging is by group, not by line.** BEA's NIPA methodology
  documents the source series category by category; the bridge infers the same
  information statistically, from the fitted slope. That is more robust to
  BEA changing a source and less precise about which line changed.
* **The concordance is a judgement.** It is a committed CSV precisely so it can
  be argued with; changing a row changes the weight, price and scope terms and
  nothing else.

---

## 6. Running it

```bash
python scripts/export_trim_data.py        # builds the decomposition + bridge into web/data/trim.json
python -m pytest tests/test_cpi_pce.py
```

```python
from ism.cpi_pce import gap_decomposition, bridge_nowcast
res = gap_decomposition(cpi_infl, cpi_w, pce_infl, pce_w, pce_published=pce_yoy)
res.check()                      # ~1e-16
res.table[["gap", "weight", "price", "scope"]].tail()
```

---

## 7. Sources

| what | where |
|---|---|
| CPI item strata, published CPI-U | BLS flat files, `.../time.series/cu/` |
| Chained CPI (C-CPI-U) | BLS flat files, `.../time.series/su/` |
| PCE category prices and expenditure | BEA 2.4.4U / 2.4.5U (or the committed `web/data/ism.json`) |
| Published PCE price index | the site's own headline series, from FRED via `export_web_data.py` |

Background reading: McCully, Moyer & Stewart (2007), "Comparing the Consumer
Price Index and the Personal Consumption Expenditures Price Index", *Survey of
Current Business*; and the BLS "Differences between the CPI and the PCE price
index" fact sheet.
