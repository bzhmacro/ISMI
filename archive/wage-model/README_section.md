## Fifth model: wages, indexation and the spiral gain

The other four models take an inflation print apart. The fifth asks the question
from the other side: when prices move, what happens to what households are paid,
and does that feed back into prices?

Three things pay a household and only one of them is a wage. There is the market
bargain; there is the statutory floor, which in France has been indexed to prices
by formula since 1970 and in the United States has not moved since 2009; and
there are indexed benefits and pensions, which cover about 70 million Americans
and rose 8.7% in a single January in 2023. Since 2021 there is a fourth:
discretionary payments and energy subsidies worth several percent of GDP across
Europe, some of which enter the consumer price index and some of which do not.

The model produces two objects.

**The Effective Wage Index** adds all four sources, weighted by an income group's
actual composition, and deflates twice — by the recorded price index, and by the
index that would have been recorded without caps, tariff shields and fuel-duty
cuts. The gap between the two is the part of measured real income that is a
consequence of *how* support was delivered rather than of what households
received: about 2.6 percentage points of French inflation in 2022.

**The Spiral Gain** `G = Λ × M` is the product of two pass-throughs: how much of
a real-wage loss gets recovered within three years (Λ), and how much of a wage
impulse reaches prices over the same horizon (M). A spiral needs both, and the
central estimate is that Λ runs from −0.23 with no indexation to +0.77 under
universal indexation — without an escalator clause, a real-wage loss is simply
not recovered. Belgium has the highest indexation intensity in the panel and
among the lowest wage-to-price pass-through, which is why automatic indexation
there did not produce excess inflation; Italy under the *scala mobile* had both,
and a gain of 0.76. No country in the panel today is above 0.21.

The indexation intensity λ is not a residual: it is built from a hand-assembled,
row-by-row sourced database of who was indexed to what
(`config/indexation_coverage.csv`), covering contractual escalators, statutory
public pay, minimum-wage-benchmarked agreements and formal inflation references
for seven countries from 1960 — the US COLA decline, the UK's 1974 threshold
agreements, France's 1983 *désindexation* and the SMIC formula that survived it,
Belgium's health-index indexation, Italy's *scala mobile* and its dismantling.

```bash
python scripts/build_wage.py        # fetch, assemble, estimate, validate
python scripts/export_wage_data.py  # refresh the website payload
```

No API key is required: every series comes from FRED's keyless CSV endpoint, the
ONS time-series JSON, the Eurostat dissemination API or INSEE's SDMX endpoint.
Countries: the United States (1960–), the United Kingdom (1963–), France and
Germany, plus Belgium, Italy and Spain as reference cases — λ barely moves inside
any one country, so the indexation interaction is identified across the panel.

Key files: `src/ism/wage_engine.py` (the maths, Eqs. W1–W12),
`wage_pipeline.py` (the country panels and the statutory uprating rules),
`wage_sources.py` (keyless clients), `wage_validate.py`,
`web/wage_engine.js` (parity-tested browser twin). Full maths-to-code map:
`docs/wage_methodology.md`. The paper is `paper/wage_inflation.md`.

