# Wage model — maths to code

The fifth model on the site. Read this beside `src/ism/wage_engine.py`; every
equation below carries the tag the code carries, and the browser twin
`web/wage_engine.js` carries it too.

Companion documents: the paper is `paper/wage_inflation.md`; the non-obvious
data and modelling judgments are in `docs/DECISIONS.md`; every institutional
number is sourced row by row in `config/indexation_coverage.csv`.

---

## 0. What the model is for

The other four models on this site take an inflation print apart. This one asks
what happens on the other side of the transaction: when prices move, what
happens to what households are paid, and does that feed back into prices?

Three things pay a household and only one is a wage — the market bargain, the
statutory floor, and indexed benefits and pensions — and since 2021 there is a
fourth, discretionary payments and energy subsidies worth several percent of
GDP across Europe. The model therefore has two objects:

* the **Effective Wage Index (EWI)**, which adds all four weighted by an income
  group's actual composition, and
* the **Spiral Gain** `G = Λ × M`, the product of how much of a real-wage loss
  is recovered and how much of a wage impulse reaches prices.

Frequency is **quarterly**. Growth rates are **four-quarter log changes in
percent**, not annualised quarterly ones; §6 says why.

---

## 1. Trend inflation — Eq. (W1)

A fixed-gain local-level filter:

```
pi*_t = pi*_{t-1} + k(q) * (pi_t - pi*_{t-1})
k(q)  = (sqrt(q^2 + 4q) - q) / 2
```

`q` is the signal-to-noise ratio of a random-walk-plus-noise model and `k` its
steady-state Kalman gain. `q = 0` gives `k = 0`: a constant trend, perfectly
anchored expectations. Large `q` gives `k → 1`: `pi*` is last quarter's
inflation and there is no anchor at all. The baseline is `q = 0.05`, i.e.
`k = 0.20`.

This is the fixed-gain limit of the Stock–Watson (2007) unobserved-components
model with stochastic volatility. The full version is better econometrics; the
fixed gain is a single readable number that the site can put on a slider and
the browser can reproduce exactly, and the anchoring question is precisely a
question about the size of that number.

→ `kalman_gain`, `trend_inflation` / `kalmanGain`, `trendInflation`

## 2. The catch-up term — Eq. (W2)

```
rw_t      = 100 * log(W_t / P_t)
trend_t   = one-sided local linear projection of rw over the last 40 quarters
catchup_t = -(rw_t - trend_t)
```

Positive when the real wage has fallen below the path it was on — the state in
which workers have something to catch up. The trend is fitted on the window
*ending at t-1* and projected one period forward, so nothing after `t` enters
and the series is computable in real time and in a browser.

**Why not Bernanke & Blanchard's catch-up term.** Theirs is realised inflation
minus the survey expectation formed a year earlier. Without a survey — and
there is none for most of this sample or most of these countries — the natural
substitute is realised inflation minus a filtered trend. That substitute is an
*exact linear function of the trend's own lags*: with a fixed-gain filter,

```
pi_t = pi*_{t-1} + (pi*_t - pi*_{t-1}) / k
```

so the catch-up block and the trend block span the same space. In our panel
this produced catch-up coefficient sums of +54 with `k = 0.2` — which is
1/k times noise, not an estimate. The level formulation has no such defect and
is closer to what the theory describes: Bernanke & Blanchard's own Eq. (2) has
wages chase an *aspiration real wage*, and DeLuca & Van Zandweghe (2023) argue
for an error-correction term on the level of the real wage for the same reason.

The surprise version is retained as `catchup_bb` so the collinearity can be
demonstrated rather than asserted. Do not put it in the same regression as a
filtered trend.

→ `rolling_trend_gap`, `real_wage_gap`, `catchup` / `rollingTrendGap`,
`realWageGap`

## 3. Indexation intensity — Eq. (W3)

```
lambda_t = clip( sum_j c_{j,t} * e_j , 0, 1 )
```

`c_{j,t}` is the share of employees covered by channel `j` at date `t`, from
`config/indexation_coverage.csv`; `e_j` is that channel's assumed pass-through.
The four channels and their baseline elasticities:

| channel | what it is | e | source for e |
|---|---|---:|---|
| `automatic` | a contractual escalator: pay moves with a price index by formula | 0.90 | Card (1986): marginal escalator elasticities 0.75–0.95 |
| `public` | statutory indexation of public-sector pay | 1.00 | mechanical by construction |
| `minwage` | pay set by, or benchmarked to, a price-indexed statutory floor | 0.35 | Cengiz et al. (2019): spillovers ≈ 40% of the total wage gain, dying out about $3 above the floor |
| `benchmark` | inflation has a formal, named role in collective bargaining | 0.30 | ECB OP 299 (2022): private wage reaction 0.3–0.5pp per 1pp of indexed public wage growth |

The channels are **not mutually exclusive** — a French employee can sit in a
SMIC-benchmarked agreement *and* one with a formal inflation reference — so the
raw sum can exceed one and is clipped. `lambda` then reads as "the share of the
wage bill that moves one-for-one with past prices".

Coverage is documented at the dates in the CSV and linearly interpolated
between them, because institutions change on a date but the share of employees
affected drifts as contracts expire on a rolling basis. The one case where that
would be wrong — the UK's 1974 threshold agreements, which were in force for
about a year — is encoded as a step with adjacent zero rows so it is not
smoothed away.

→ `indexation_intensity` / `indexationIntensity`

## 4. The wage equation — Eq. (W4)

```
gw_t = a0 + sum_{k=1..p} a_k gw_{t-k}
          + sum_{k=1..p} b_k pistar_{t-k}
          + sum_{k=1..p} c_k slack_{t-k}
          + sum_{k=1..p} d_k catchup_{t-k}
          + sum_{k=1..p} dx_k [lambda_{t-k} * catchup_{t-k}]
          + e1 gpty_{t-1} + f1 dmw_t + u_t
```

subject to `sum(a) + sum(b) = 1` (a vertical long-run Phillips curve).

The catch-up block enters **twice**: at its own level, and multiplied by
`lambda`. The level coefficients `d_k` are then the pass-through of a real-wage
loss in a country with no indexation at all, and the interaction coefficients
`dx_k` the extra pass-through per unit of indexation intensity. The test that
matters is `sum(dx) > 0`.

`interact=False` drops `lambda` entirely and recovers the Bernanke & Blanchard
wage equation (their `gexp` is our `pistar`), which is what the validation
suite compares against their Table 1.

### Eq. (W4′) — the pooled panel

The same equation across seven countries with country fixed effects and common
slopes. This is the headline specification and the reason the reference
countries exist: within any one country `lambda` moves slowly over a narrow
range — 0.02 to 0.13 across sixty-five years of US data — so the interaction is
barely identified from the time series. Across the panel it runs from 0.02 (the
United States today) to 1.00 (Belgium throughout), and Belgium and Germany
share a currency, a central bank and the 2022 energy shock while differing in
exactly the institution under study.

→ `fit_wage_equation`, `fit_panel_wage_equation` / `fitWageEquation`,
`fitPanelWageEquation`

## 5. The price equation — Eq. (W5)

```
gp_t = b0 + sum_{k=1..p} B_k gp_{t-k}
          + sum_{k=0..p} M_k gw_{t-k}
          + sum_{k=0..p} E_k grpe_{t-k}
          + sum_{k=0..p} F_k grpf_{t-k}
          + sum_{k=0..p} P_k h_{t-k}
          + Bm gpty_{t-1} + v_t
```

subject to `sum(B) + sum(M) = 1`. Two departures from Bernanke & Blanchard,
both deliberate:

* `h_t` is the **income-based** fiscal support term: cash transfers to
  households, as the four-quarter change in their share of household
  disposable income, cyclically adjusted (§7). B&B have no fiscal block; this
  is the term through which a government's response to an energy shock feeds
  back into prices. Price-based support is deliberately *not* here — it does
  not add demand, it subtracts mechanically from the measured index — and is
  handled as a CPI wedge in Eq. (W11) instead.
* relative energy and food prices are measured against **wages**,
  `grpe = Δ4 log(P_energy / W)`, which is B&B's own convention and makes these
  real-product-wage terms rather than relative-to-CPI terms. This is the
  commonest replication error in the literature.

→ `fit_price_equation` / `fitPriceEquation`

## 6. The estimator

Least squares subject to one linear restriction `R'b = r`, imposed
analytically:

```
b_r = b + V R (R'VR)^{-1} (r - R'b),    V = (X'X)^{-1}
V_r = s^2 [ V - V R (R'VR)^{-1} R' V ]
```

`(X'X)^{-1}` is computed by **Gauss-Jordan elimination with partial pivoting**
and a trace-scaled ridge of 1e-10, not by `numpy.linalg.pinv`, because the
browser twin has to reproduce it to 1e-9 and there is no SVD in JavaScript. Any
design matrix that needs more than this is one whose coefficients should not be
believed anyway.

Standard errors are classical. **They understate uncertainty**, because the
panel is estimated on overlapping four-quarter growth rates and the residuals
are therefore serially correlated by construction. Read the t-statistics as
indicative; the paper leans on coefficient sums and sign tests.

### Why year-on-year and not annualised quarterly

Bernanke & Blanchard can use annualised quarterly growth because their wage
measure is the Employment Cost Index, a fixed-weight quarterly index built for
exactly that. Outside the United States there is no ECI: what exists is
compensation per employee from the national accounts, OECD hourly earnings and
average weekly earnings, all of which carry enough quarter-to-quarter
measurement noise that their annualised quarterly growth is close to white.
Estimated on those, the wage equation returns a *negative* sum of own-lag
coefficients — the signature of differencing noise, not of wage dynamics. The
annualised quarterly variants are kept as `gp_q` and `gw_q` so the choice can
be inspected rather than taken on trust.

→ `_inv`, `restricted_ols` / `inv`, `restrictedOls`

## 7. The gains — Eqs. (W6)–(W8)

For a scalar AR(p) driven by a permanent unit step in a regressor, the response
at horizon `h`:

```
y_t = sum_k own_k y_{t-k} + sum_k driver_k x_{t-k},    x_t = 1 for t >= 0
```

* **Λ(λ)** — Eq. (W6) — the three-year response of wage growth to a unit
  real-wage gap, with `driver_k = d_k + λ dx_k`. `Λ(0)` is the pass-through
  with no indexation; `Λ(1)` under universal indexation; the difference between
  them is the estimate of what an indexation clause is worth.
* **M** — Eq. (W7) — the three-year response of price inflation to a permanent
  1pp rise in wage growth.
* **Φ** — Eq. (W8b) — the extra route that runs through the government rather
  than the wage bargain: `phi_e × mpc` scaled through the price equation's
  transfer block.
* **G = Λ × M** — Eq. (W8). `G > 1` is the spiral condition: one turn of the
  loop more than reproduces itself inside the horizon, so the shock is
  self-sustaining without any further impulse.

**Why three years and not the long run.** The long-run multiplier
`sum(driver)/(1 - sum(own))` is the obvious object and it is useless here: the
homogeneity restriction sets the price equation's long-run pass-through to
exactly 1 whatever the data say, because that restriction *is* the assumption
that the Phillips curve is vertical. The restriction is right — one does not
want a model in which permanently higher wage growth leaves prices permanently
behind — but it means the long run cannot distinguish regimes. Three years can:
it is the horizon the euro-area sectoral pass-through literature reports, and
it is long enough for an indexation clause to have fired several times and
short enough that monetary policy has not undone the shock.

In `spiral_gain`, `M` is fixed and only `lambda` varies over time, so the time
variation in `G` is entirely institutional — which is the claim being tested.
`rolling_gain` re-estimates both on a moving window and is the honest
robustness check.

→ `price_to_wage_gain`, `wage_to_price_gain`, `fiscal_gain`, `spiral_gain`,
`rolling_gain`

## 8. The fiscal reaction function — Eq. (W9)

```
h_t = rho h_{t-1} + phi_e energyshock_t + phi_pi (pi_t - pi*_t)
                  + phi_x slack_t + phi_P populist_t + country FE + e_t
```

`h` is in percentage points of household disposable income, so `phi_e` reads
directly as "points of household income handed out per point of excess
inflation". `populist` is the Funke–Schularick–Trebesch coding from
`config/wage_politics.csv`; it is zero throughout for all seven countries over
the estimation sample, so `phi_P` is not identified here. That is stated as a
result rather than papered over with a looser coding.

→ `fit_fiscal_rule`

## 9. The Effective Wage Index — Eqs. (W10)–(W11)

```
EWI_t = sum_{c != handout} s_c X_{c,t}  +  (X_handout,t - 100)
```

with components `wage`, `minwage`, `benefit` (each an index, 100 in 2019Q4) and
`handout`, and `s_c` the income-composition shares from
`config/wage_income_shares.csv`.

**Handouts enter additively.** A recurring income source is properly weighted
by its share of income: the market wage is 42% of the US bottom quartile's
income, so a 10% raise is worth 4.2 index points. A one-off payment has no
share — it is a flow that exists in one year and not the next — and its
component index is already one plus the payment as a fraction of disposable
income. Weighting it again by a "handout share" would shrink a €300
Energiepreispauschale to a rounding error.

The `benefit` component is built from the **statutory uprating rule**, not from
a spending aggregate, which would move with caseloads. The rules implemented:

| country | rule | effective |
|---|---|---|
| US | increase in the Q3 average CPI-W over the highest previous Q3, floored at zero (SSA s.215(i)) | December, paid the following January |
| UK | September CPI (SSAA 1992 s.150); for the State Pension the triple lock takes the highest of September CPI, the May–July average of total-pay growth, and 2.5% | the following April |
| FR | average CPI excluding tobacco over the twelve most recent monthly indices (CSS art. L161-25), floored at zero | 1 January |
| DE | the Rentenanpassungsformel in the form that has applied since the 48% Niveauschutzklausel began to bind: gross wage growth with the dampening factors suspended | 1 July |

These are validated against the uprating decisions actually announced, in
`config/wage_uprating.csv`.

**Real and subsidy-neutral.** Eq. (W11) deflates twice:

* *measured real* by the recorded CPI, which price-based support has already
  lowered;
* *subsidy-neutral real* by the index that would have been recorded without
  those measures, reconstructed by cumulating the wedge in
  `config/wage_cpi_wedge.csv`.

The gap is the part of measured real income that is a consequence of *how*
support was delivered rather than of what households received. A government
choosing between a price cap and a cash transfer of equal cost is also choosing
how much measured inflation to record, and by implication how much every
price-indexed contract in the economy will pay out. That is a policy lever
hiding inside a statistical convention.

→ `effective_wage_index`, `real_effective_wage`, `benefit_index`,
`uprating_us/uk/fr/de` / `effectiveWageIndex`, `realEffectiveWage`

## 10. The simulator — Eq. (W12)

```
gp_t     = sum B_k gp_{t-k} + sum M_k gw_{t-k} + sum E_k grpe_{t-k} + sum P_k h_{t-k}
gw_t     = sum a_k gw_{t-k} + sum b_k pistar_{t-k} + sum c_k slack_{t-k}
                             + sum (d_k + lam dx_k) catchup_{t-k}
pistar_t = pistar_{t-1} + k(q) (gp_t - pistar_{t-1})
catchup_t= mean(gp_{t-3..t}) - pistar_{t-4}
h_t      = phi_e * max(gp_t - pistar_t, 0) * mpc
slack_t  = -taylor * (gp_t - pistar_t)
```

The monetary rule is written as a direct slack response rather than a rate
rule, because the estimated wage equation takes slack and not the policy rate;
a Taylor rule here would need an IS curve that has not been estimated, and
pretending otherwise would add a free parameter without adding information.
`taylor` is therefore percentage points of slack opened per point of inflation
above trend — a reduced-form sacrifice-rate dial.

→ `simulate_loop`, `SimParams` / `simulateLoop`

---

## Commands

```bash
python scripts/build_wage.py              # fetch, assemble, estimate, validate
python scripts/build_wage.py --force      # ignore the raw-data cache
python scripts/export_wage_data.py        # refresh web/data/wage.json
python -m pytest tests/test_wage_engine.py tests/test_wage_parity.py
```

No API key is needed: every series comes from FRED's keyless CSV endpoint, the
ONS time-series JSON, the Eurostat dissemination API or INSEE's SDMX endpoint.
The one slow step is the employment-weighted effective US minimum wage, which
makes about a hundred single-series FRED calls; `--no-effective-mw` skips it
and falls back to the federal rate.
