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

