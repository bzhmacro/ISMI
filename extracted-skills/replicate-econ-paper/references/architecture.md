# Architecture: the package, the data contract, the engine

This file covers the Python side: how the project is laid out, the single data
contract everything routes through, how the engine maps to the paper, and how the
same code supports multiple models and multiple countries.

## Contents
- Repository layout
- The `(panel, weights)` data contract
- Equation→code discipline in the engine
- Pinning the cross-section deterministically
- Pipeline: from raw provider rows to the contract
- Portability: a second model, and a new country
- The "feed in your own forecast" property

## Repository layout

A `src/` layout keeps the importable library separate from scripts, notebooks,
config, and the website. A representative tree (rename `pkg` to your project's
import name):

```
project/
├── config/
│   ├── sources.yaml            # registry of EVERY data source (see data-sources.md)
│   ├── sources_<cc>.yaml       # one mapping file per country port (eu, uk, jp, …)
│   ├── units.csv               # the PINNED cross-section (categories/sectors/…)
│   └── shocks.yaml             # hand-encoded event dates from the paper text
├── src/pkg/
│   ├── engine.py               # THE MATHS: each function == one numbered equation
│   ├── transforms.py           # level → inflation/growth transforms
│   ├── datasources.py          # provider clients (retry, caching, provenance)
│   ├── external_data.py        # author-hosted / non-API series + loaders
│   ├── pipeline.py             # provider rows → (panel, weights)  [per backbone]
│   ├── controls.py             # control / predictor frame
│   ├── forecasting.py          # the in-sample tables
│   ├── oos_*.py                # out-of-sample exercises (e.g. LASSO + GW test)
│   ├── local_projection.py     # impulse responses / local projections
│   ├── validate.py             # convergence vs the authors' file
│   ├── <cc>_pipeline.py        # one extra loader per country (same contract out)
│   └── run.py                  # CLI orchestrator: fetch / index / table / figures / all
├── scripts/
│   ├── build_and_validate.py   # build + reprint the convergence table
│   ├── finalize_units.py       # regenerate the pinned units.csv from provider data
│   └── export_web_data.py      # raw panels + baseline → web/data/<name>.json
├── notebooks/                  # guided, runnable reproductions of each exhibit
├── web/                        # zero-build site (see web-port.md)
├── tests/                      # synthetic, no-network unit tests incl. JS parity
├── docs/  DECISIONS.md  differences_report.md  methodology.md
└── data/                       # gitignored; rebuildable from sources.yaml
```

Principles: the library has no hidden state and no I/O at import; scripts and
notebooks are thin callers; `data/` and secrets are never committed (everything is
reproducible from the registry).

## The `(panel, weights)` data contract

This is the keystone. Define it once and force every model and every country
through it:

- **`panel`** — a `DataFrame` indexed by month (a `Datetimeindex`), one column per
  **unit** (category, sector, bond, region). Values are the already-transformed
  quantity the equations consume (e.g. monthly inflation `100·Δln price`), not raw
  index levels.
- **`weights`** — a `DataFrame` aligned to `panel` (same index/columns) giving each
  unit's importance per month (expenditure share, market value, population). The
  engine renormalises weights each month over the units that have a defined signal,
  so a unit that is missing early (short history) simply doesn't contribute yet.

The engine's signature is `compute(panel, weights, config) -> result`. It must not
mention providers, countries, or file formats. Two tests of whether the
abstraction is clean: (1) you can run it on a purely synthetic panel in a unit
test; (2) adding a country touches only a new pipeline file, never the engine.

## Equation→code discipline in the engine

Write the engine so a reader can hold the paper in one hand and the module in the
other. Put the mapping at the top of the file and name functions after the
equations:

```
Eq. (3)  pi_{i,t} = mu_i + rho_i*pi_{i,t-1} + eps_{i,t}
         -> rolling_ar_residuals()      # per unit, W-month rolling window
Eq. (4)  M+_{i,t} = prod_{k=0..K-1} 1(eps_{i,t-k} > 0)
         -> momentum_signals()
Eq. (6)  S+_t = sum_i w_{i,t}*M+_{i,t}
         -> weighted_shares()
Eq. (8)  ISM_t = S+_t - S-_t
         -> index()
```

Keep every modelling choice a **parameter with the paper's baseline as default**
(`window=120`, `ar_order=1`, `run_length=3`, `scheme="extensive"`), never a
hard-coded constant. Robustness checks, the appendix grid, and country ports all
reuse the identical code by varying arguments. Use a frozen `@dataclass` config
object to bundle them.

Numerical care that pays off: assemble rolling normal equations from prefix sums of
lagged cross-products (fast and exactly reproducible), and fall back to a
pseudo-inverse / min-norm solution for rank-deficient windows (e.g. a price flat
for years) so the result matches `numpy.lstsq`. The JS twin must match these
choices bit-for-bit (see web-port.md).

## Pinning the cross-section deterministically

Recovering the authors' exact unit set ("129 categories at the fourth level") is
usually the hardest, most underspecified part of a replication, and the biggest
driver of how close you converge. Treat it as a first-class, reproducible step:

1. Pull the provider's hierarchy (often the API gives values but **strips the
   indentation/level**, so you need the interactive-table CSV or a separate
   metadata call to recover depth).
2. Take a documented cut — e.g. "every node at level 5, plus branches that
   terminate earlier, excluding addenda/aggregates and any double-counting
   accounting layer."
3. **Pin the result to `config/units.csv`** (key, provider code, level, label) and
   regenerate it with a committed script. After this, the set never drifts.
4. Record the candidates you tried and their correlation with the authors' output
   in the differences report — this is what justifies the final cut.

Matching codes across tables is a common foot-gun: a price series and its nominal
counterpart often differ by a suffix/prefix (e.g. `…RG` vs `…RC`). Match on a
normalised key, and unit-test that the panel is non-empty.

## Pipeline: from provider rows to the contract

`pipeline.py` is where provider-specific shape dies. It reads the cached raw rows,
selects the pinned units, applies the transform from `transforms.py`, aligns price
and weight tables on the normalised key, and returns the `(panel, weights)` pair —
nothing provider-specific escapes it. Each alternative "backbone" (e.g. a CPI gauge
beside a PCE gauge) is its own pipeline file producing the same pair, so the engine
and the website treat them interchangeably behind a toggle.

## Portability: a second model, and a new country

- **Second model.** If a related model needs more inputs (e.g. a supply/demand
  decomposition needs *quantity* as well as price), add the extra source to the
  registry, write a second engine (`decomp_engine.py`) and pipeline behind the same
  `(panel, …)` contract, and expose a top-level **model toggle** in the site. The
  validation, export, and parity machinery are reused wholesale.
- **New country.** Add `config/sources_<cc>.yaml` mapping each US source role to the
  national-statistics equivalent (Eurostat HICP, ONS MM23, e-Stat, …), write one
  `<cc>_pipeline.py` that returns the same pair, and the index/forecasts/local
  projections fall out unchanged. Expect the analogue of the "fourth level" to be a
  different hierarchy cut (COICOP n-digit) with a `max_digits` knob, and expect a
  shorter sample (detailed national series often start late) — judge ports on
  economic plausibility and in-sample fit when there is no author series.

## The "feed in your own forecast" property

Because the engine consumes a plain panel, scenario analysis is free: append your
projected future rows to `panel` (and `weights`), recompute, and the rolling
benchmark and momentum/decomposition logic extend naturally into the future. Keep
the controls frame append-compatible the same way. This is worth preserving
deliberately — it is what makes the replication a tool, not just a reproduction.
