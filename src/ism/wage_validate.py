"""
ism.wage_validate
=================

What the wage model is checked against, and -- just as important -- what it
cannot be checked against.

The three older models in this repository are validated the strong way: the
Cleveland Fed publishes a median CPI, the Dallas Fed a trimmed-mean PCE, the
FRBSF a supply/demand decomposition, so a replication either matches the
published series or it does not. The wage model has no published counterpart.
Its validation is therefore assembled from four weaker but independent checks:

1. **Statutory uprating rules.** The pipeline implements each country's benefit
   uprating statute and applies it to observed price and wage data. The
   resulting percentages must reproduce the uprating decisions actually
   announced (``config/wage_uprating.csv``). This is a genuine out-of-sample
   test of the data plumbing: the SSA's COLA is a deterministic function of
   CPI-W, so any error in the price series shows up immediately.

2. **The Bernanke & Blanchard (2025) coefficient sums.** We cannot replicate
   their equation exactly -- it needs the Employment Cost Index back to 1990
   (BLS API, keyed) and the Barnichon composite help-wanted index (a manual
   download) -- so this is a *similarity* check, not a replication, and it is
   reported as such. What should hold is the split between own-lag persistence
   and the expectations term (they report 0.460 / 0.540) and the sign and rough
   size of the tightness term.

3. **Internal coherence.** Coefficient sums inside their admissible ranges,
   homogeneity restrictions actually binding, gains finite, lambda in [0,1],
   no country's panel silently empty.

4. **Known institutional facts.** The UK's indexation intensity must spike in
   1974 and nowhere else; Belgium's must sit near one throughout; the US's must
   fall by roughly a factor of six between 1975 and today; France's
   minimum-wage channel must not fall after 1983 (the desindexation ended
   general wage indexation but left the SMIC formula intact -- the single most
   important institutional fact in the French part of the paper).

``validate_all`` returns a list of ``Check`` records rather than raising, so a
build reports every failure at once instead of stopping at the first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import wage_pipeline as wp
from .wage_engine import (OLSFit, WageConfig, fit_panel_wage_equation,
                          fit_price_equation, fit_wage_equation,
                          poolability_test, price_to_wage_gain,
                          wage_to_price_gain)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    value: Optional[float] = None
    target: Optional[float] = None

    def __str__(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        return f"[{mark}] {self.name}: {self.detail}"


# ---------------------------------------------------------------------------
# 1. Statutory uprating rules vs published decisions
# ---------------------------------------------------------------------------
def check_uprating(raw_by_country: Dict[str, Dict[str, pd.Series]],
                   tol: float = 0.35) -> List[Check]:
    """Reproduce announced uprating decisions from the implemented statute.

    ``tol`` is 0.35pp, not 0.1pp, because three of the four rules are applied
    to a slightly different index from the statutory one: the US rule wants
    CPI-W (we have it), but the French rule wants the national CPI excluding
    tobacco (we use the harmonised index), the German formula wants the
    national-accounts wage aggregate with two dampening factors we do not
    model, and the UK triple lock wants the May-July average of total pay
    including bonuses. Where the gap exceeds the tolerance the check fails and
    the size of the gap is reported, which is more useful than pretending the
    approximation is exact.
    """
    out: List[Check] = []
    table = pd.read_csv(REPO_ROOT / "config" / "wage_uprating.csv", comment="#")
    for country, raw in raw_by_country.items():
        sub = table[table["country"] == country]
        if sub.empty:
            continue
        try:
            if country == "US":
                implied = wp.uprating_us(raw.get("cpi_w", raw["cpi"]))
            elif country == "UK":
                implied = wp.uprating_uk(raw["cpi_m"], raw.get("earnings_m"))
            elif country == "FR":
                implied = wp.uprating_fr(raw.get("cpi_xtob_m", raw.get("cpi_m", raw["cpi"])))
            else:
                implied = wp.uprating_de(raw["wage"])
        except Exception as exc:  # noqa: BLE001
            out.append(Check(f"uprating/{country}", False, f"rule failed: {exc}"))
            continue
        hits, misses, gaps = 0, [], []
        for _, row in sub.iterrows():
            eff = pd.Timestamp(str(row["effective_month"]) + "-01")
            cand = implied[(implied.index.year == eff.year)]
            if cand.empty:
                continue
            got, want = float(cand.iloc[0]), float(row["pct"])
            gaps.append(abs(got - want))
            if abs(got - want) <= tol:
                hits += 1
            else:
                misses.append(f"{row['programme']} {eff.date()}: rule {got:.2f} vs published {want:.2f}")
        if not gaps:
            out.append(Check(f"uprating/{country}", False, "no overlapping dates to compare"))
            continue
        mad = float(np.mean(gaps))
        ok = hits >= max(1, int(0.6 * len(gaps)))
        detail = (f"{hits}/{len(gaps)} within {tol}pp, mean abs gap {mad:.2f}pp"
                  + ("; worst: " + misses[0] if misses else ""))
        out.append(Check(f"uprating/{country}", ok, detail, mad, tol))
    return out


# ---------------------------------------------------------------------------
# 2. Similarity to Bernanke & Blanchard (2025), Table 1
# ---------------------------------------------------------------------------
BB_TARGETS = {
    "sum_gw": 0.460,     # own lags of wage growth
    "sum_exp": 0.540,    # short-run inflation expectations
    "sum_vu": 0.693,     # labour-market tightness
    "sum_catchup": -0.024,
    "r2": 0.578,
}


def check_bernanke_blanchard(panels: Dict[str, pd.DataFrame],
                             cfg: Optional[WageConfig] = None,
                             tol: float = 0.20) -> List[Check]:
    """Compare the US wage equation's coefficient sums with B&B's Table 1.

    The comparison is made on the POOLED panel, which is this paper's headline
    specification, and the United States alone is reported alongside without a
    pass/fail. That is not cherry-picking, and the reason matters enough to
    state plainly: estimated on one country's year-on-year series, the trend
    term pi* is close to collinear with four lags of wage growth, so the
    homogeneity restriction is satisfied by loading almost everything on
    persistence -- the US-alone split is 0.97 / 0.03. Pooling seven countries
    breaks that collinearity, because pi* and wage growth do not move together
    across countries in the same way. On the full sample the pooled split
    (without the lambda interaction) is about 0.60 / 0.40 against Bernanke &
    Blanchard's 0.46 / 0.54; on THEIR window (1990Q1-2019Q4), which is what
    this check uses, it is about 0.64 / 0.36. Do not quote a number here
    without re-running: an earlier version of this docstring carried 0.44 /
    0.56 from a superseded vintage and the paper copied it. Neither number should be called a replication, and the second
    only passes a 0.20 tolerance by 0.02. What the check establishes is that
    the estimator puts a substantial weight on the expectations term rather
    than loading everything on persistence, not that it reproduces their
    coefficients.

    The check is deliberately loose (0.20 on a sum the homogeneity restriction
    confines to [0,1]) because a tight one would be testing our data
    substitutions rather than the estimator: we lack their ECI back-history and
    their vacancy series.
    """
    cfg = cfg or WageConfig()
    out: List[Check] = []
    # Deliberately the FULLY POOLED fit. Bernanke & Blanchard estimate one
    # equation with one coefficient vector, so the comparable object here is
    # the pooled panel, not the paper's headline specification, whose dynamics
    # are country-specific and therefore have no common own-lag sum to compare.
    try:
        fit = fit_panel_wage_equation(panels, cfg, interact=False, free=(),
                                      sample=("1990-01-01", "2019-12-31"))
    except Exception as exc:  # noqa: BLE001
        return [Check("bernanke_blanchard/wage", False, f"estimation failed: {exc}")]
    try:
        full = fit_panel_wage_equation(panels, cfg, interact=False, free=())
        out.append(Check("bernanke_blanchard/full_sample_split", True,
                         f"full-sample pooled split {full.sum_of('gw_l'):.3f} / "
                         f"{full.sum_of('pistar_l'):.3f} -- reported, not tested",
                         full.sum_of("gw_l"), None))
    except Exception:  # noqa: BLE001
        pass
    if "US" in panels:
        try:
            us = fit_wage_equation(panels["US"], cfg, interact=False,
                                   sample=("1990-01-01", "2019-12-31"))
            out.append(Check("bernanke_blanchard/us_alone", True,
                             f"United States alone splits {us.sum_of('gw_l'):.3f} / "
                             f"{us.sum_of('pistar_l'):.3f} -- reported, not tested; see docstring",
                             us.sum_of("gw_l"), None))
        except Exception:  # noqa: BLE001
            pass
    got = fit.sum_of("gw_l")
    out.append(Check("bernanke_blanchard/persistence", abs(got - BB_TARGETS["sum_gw"]) <= tol,
                     f"sum of own lags {got:.3f} vs published {BB_TARGETS['sum_gw']:.3f}",
                     got, BB_TARGETS["sum_gw"]))
    got = fit.sum_of("pistar_l")
    out.append(Check("bernanke_blanchard/expectations", abs(got - BB_TARGETS["sum_exp"]) <= tol,
                     f"sum of trend/expectations terms {got:.3f} vs published {BB_TARGETS['sum_exp']:.3f}",
                     got, BB_TARGETS["sum_exp"]))
    got = fit.sum_of("slack_l")
    out.append(Check("bernanke_blanchard/tightness_sign", got > 0,
                     f"tightness sum {got:+.3f}; published v/u sum {BB_TARGETS['sum_vu']:+.3f} "
                     "(different slack measure, so only the sign is comparable)", got, None))
    return out


# ---------------------------------------------------------------------------
# 3 & 4. Internal coherence and institutional facts
# ---------------------------------------------------------------------------
def check_coherence(panels: Dict[str, pd.DataFrame],
                    cfg: Optional[WageConfig] = None) -> List[Check]:
    cfg = cfg or WageConfig()
    out: List[Check] = []

    for c, d in panels.items():
        lam = d["lambda"].dropna()
        out.append(Check(f"lambda_range/{c}", bool(lam.between(0, 1).all()),
                         f"lambda in [{lam.min():.3f}, {lam.max():.3f}]"))
        n = int(d[["gw", "gp"]].dropna().shape[0])
        out.append(Check(f"panel_nonempty/{c}", n >= 80,
                         f"{n} quarters with both wage and price growth", float(n), 80.0))

    # The homogeneity restriction must bind ONCE PER COUNTRY now that the
    # dynamics are free.
    try:
        f = fit_panel_wage_equation(panels, cfg)
        worst, worst_c = 0.0, None
        for c in panels:
            tot = f.sum_of("gw_l", c) + f.sum_of("pistar_l", c)
            if abs(tot - 1.0) > worst:
                worst, worst_c = abs(tot - 1.0), c
        out.append(Check("homogeneity", worst < 1e-6,
                         f"binds in every country; worst deviation {worst:.2e} ({worst_c})",
                         worst, 1e-6))

        # The sign of the indexation effect must hold in EVERY country, not
        # just on average. This is the claim the paper rests on, and freeing
        # the dynamics is what puts it at risk.
        signs = {c: (price_to_wage_gain(f, 1.0, country=c)
                     - price_to_wage_gain(f, 0.0, country=c)) for c in panels}
        bad = {c: v for c, v in signs.items() if v <= 0}
        lo, hi = min(signs.values()), max(signs.values())
        out.append(Check("indexation_sign", not bad,
                         f"d(Lambda)/d(lambda) positive in all {len(signs)} countries, "
                         f"range {lo:+.3f} to {hi:+.3f}"
                         + (f"; NEGATIVE in {list(bad)}" if bad else ""),
                         lo, 0.0))

        pooled = fit_panel_wage_equation(panels, cfg, free=())
        out.append(Check("pooling_shrinks_interaction", True,
                         f"catch-up x lambda is {pooled.sum_of('cux_l'):+.3f} fully pooled "
                         f"vs {f.sum_of('cux_l'):+.3f} with free dynamics -- reported, not "
                         "tested: pooled dynamics inflate the interaction",
                         f.sum_of("cux_l"), None))
    except Exception as exc:  # noqa: BLE001
        out.append(Check("panel_estimation", False, f"failed: {exc}"))

    # Is one coefficient vector for seven countries defensible?
    try:
        t = poolability_test(panels, cfg)
        out.append(Check("poolability", True,
                         f"Chow F = {t['F']:.2f} on ({t['df1']:.0f}, {t['df2']:.0f}), "
                         f"p = {t['p']:.2e} -- pooling is REJECTED, which is why the "
                         "headline specification frees the dynamics",
                         t["F"], None))
    except Exception as exc:  # noqa: BLE001
        out.append(Check("poolability", False, f"failed: {exc}"))

    for c, d in panels.items():
        try:
            pf = fit_price_equation(d, cfg)
            M = wage_to_price_gain(pf)
            out.append(Check(f"wage_to_price/{c}", np.isfinite(M) and -0.5 < M < 2.5,
                             f"three-year wage-to-price pass-through {M:+.3f}", M, None))
        except Exception as exc:  # noqa: BLE001
            out.append(Check(f"wage_to_price/{c}", False, f"failed: {exc}"))

    # Institutional facts the coverage database must encode.
    facts = []
    if "UK" in panels:
        uk = panels["UK"]["lambda"]
        peak = uk.loc["1974-01-01":"1974-12-31"]
        rest = uk.drop(uk.loc["1973-06-01":"1975-06-30"].index)
        facts.append(Check("fact/uk_1974_threshold",
                           bool(len(peak) and peak.max() > rest.max()),
                           f"UK lambda peaks at {peak.max():.3f} in 1974 vs a maximum of "
                           f"{rest.max():.3f} in every other year"))
    if "BE" in panels:
        be = panels["BE"]["lambda"].dropna()
        facts.append(Check("fact/belgium_indexed", bool(be.min() > 0.9),
                           f"Belgian lambda never falls below {be.min():.3f}"))
    if "US" in panels:
        us = panels["US"]["lambda"]
        a = float(us.loc["1975-01-01":"1975-12-31"].mean())
        b = float(us.loc["2023-01-01":"2024-12-31"].mean())
        facts.append(Check("fact/us_cola_decline", a / max(b, 1e-9) > 4.0,
                           f"US lambda falls from {a:.3f} in 1975 to {b:.3f} today "
                           f"(factor {a / max(b, 1e-9):.1f})", a / max(b, 1e-9), 4.0))
    if "FR" in panels:
        cov = panels["FR"]
        a = float(cov["cov_minwage"].loc["1980-01-01":"1982-12-31"].mean())
        b = float(cov["cov_minwage"].loc["1990-01-01":"1995-12-31"].mean())
        facts.append(Check("fact/france_smic_survived_desindexation", b >= a,
                           f"French minimum-wage channel {a:.3f} before 1983 and {b:.3f} after: "
                           "the 1983 desindexation ended general wage indexation but left the "
                           "SMIC formula in force"))
    out.extend(facts)
    return out


def estimation_samples(panels: Dict[str, pd.DataFrame],
                       cfg: Optional[WageConfig] = None,
                       interact: bool = True) -> pd.DataFrame:
    """The sample each country ACTUALLY contributes to the pooled regression.

    Data availability and estimation sample are not the same thing: a panel
    whose price series starts in 1960 contributes nothing until every regressor
    and all of its lags exist, and with four lags of five blocks that can be
    twenty years later. Reporting the difference is not housekeeping -- the
    paper's identification argument is about which values of lambda are inside
    the regression, and Italy's scala mobile years are not.

    Counted off the design matrix the estimator actually builds, not off a
    dropna on the contemporaneous columns: an interior gap in one series
    removes the four rows that lag onto it, and a first version of this
    function that sliced the first `lags` rows instead came out one observation
    short per country and did not sum to the reported n.
    """
    cfg = cfg or WageConfig()
    p = cfg.lags
    rows = []
    for c, d in panels.items():
        blocks = {"gw": d.get("gw"), "pistar": d.get("pistar"),
                  "catchup": d.get("catchup")}
        if "slack" in d:
            blocks["slack"] = d["slack"]
        if interact and "lambda" in d:
            blocks["cux"] = d["lambda"] * d["catchup"]
        ok = d["gw"].notna()
        for series in blocks.values():
            if series is None:
                continue
            for L in range(1, p + 1):
                ok &= series.shift(L).notna()
        eff = d.index[ok]
        if not len(eff):
            rows.append({"country": c, "start": None, "end": None, "nobs": 0,
                         "lambda_min": None, "lambda_max": None})
            continue
        lam = d.loc[eff, "lambda"] if "lambda" in d else None
        rows.append({
            "country": c,
            "start": eff[0].date().isoformat(),
            "end": eff[-1].date().isoformat(),
            "nobs": int(len(eff)),
            "lambda_min": None if lam is None else round(float(lam.min()), 3),
            "lambda_max": None if lam is None else round(float(lam.max()), 3),
        })
    return pd.DataFrame(rows).set_index("country")


def validate_all(panels: Dict[str, pd.DataFrame],
                 raw_by_country: Optional[Dict[str, Dict[str, pd.Series]]] = None,
                 cfg: Optional[WageConfig] = None) -> List[Check]:
    checks: List[Check] = []
    checks += check_coherence(panels, cfg)
    checks += check_identification(panels, cfg)
    checks += check_bernanke_blanchard(panels, cfg)
    if raw_by_country:
        checks += check_uprating(raw_by_country)
    return checks


def check_identification(panels: Dict[str, pd.DataFrame],
                         cfg: Optional[WageConfig] = None) -> List[Check]:
    """Is the top of the lambda range actually inside the estimation sample?

    Lambda(1) is the paper's headline number. If no country contributes an
    observation with lambda near one, that number is an extrapolation and must
    be described as one.
    """
    samples = estimation_samples(panels, cfg)
    hi = samples[samples["lambda_max"] >= 0.9]
    detail = ("lambda >= 0.9 is contributed by: "
              + (", ".join(f"{c} ({int(r.nobs)} obs, {r.start}..{r.end})"
                           for c, r in hi.iterrows()) if len(hi) else "no country"))
    return [Check("identification/lambda_upper_end", len(hi) > 0, detail,
                  float(len(hi)), 1.0)]


def report(checks: List[Check]) -> str:
    lines = [str(c) for c in checks]
    n_ok = sum(1 for c in checks if c.ok)
    lines.append(f"\n{n_ok}/{len(checks)} checks passed")
    return "\n".join(lines)
