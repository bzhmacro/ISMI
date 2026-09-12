"""
ism.trim_validate
=================

Does our trimmed mean reproduce the published one?

Two kinds of check, because they fail for different reasons:

**Series comparison** (:func:`compare_to_official`) -- correlation, RMSE, bias
and max absolute gap of our series against the Reserve Bank's, at both the
1-month annualised and 12-month horizons.  This catches a wrong cross-section,
wrong weights or a wrong seasonal treatment, but it is slow to localise: a bad
month looks much like a bad decade.

**Cross-section comparison** (:func:`compare_latest_cross_section`) -- our
category rates and weights for the latest month against the Reserve Bank's own
published component table, joined by name.  This is the sharp test: if a weight
is wrong you see *which* one, and by how much, rather than inferring it from a
0.1pp drift in the index.

Reference results at the time of writing (1998-, revised-vintage overlap):

===================================  ======  ======  ======
scope / measure                        corr    RMSE    bias
===================================  ======  ======  ======
``cpi45`` median CPI, 12-month        0.997   0.083   0.000
``cpi45`` 16% trimmed CPI, 12-month   0.998   0.114  +0.084
``pce``   trimmed mean PCE, 12-month  0.997   0.128  +0.048
===================================  ======  ======  ======

``cpi70`` -- the repo's finer 70-stratum cut -- tracks the trimmed mean about as
well but the median less well (corr 0.965), which is not a bug: a median is a
statement about *which category* sits at the 50th percentile, so it moves when
you re-cut the cross-section, while a trimmed mean averages over that choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .official_trim import (cleveland_components, cleveland_history,
                            dallas_detail, dallas_history)
from .trim_engine import MEDIAN_CPI, TRIM16_CPI, TRIM_PCE, TrimConfig, compute_trim
from .trim_pipeline import TrimPanel

#: Which published series each (scope, measure) pair should be judged against.
OFFICIAL = {
    ("cpi45", "median"): ("cleveland", "median"),
    ("cpi45", "trim16"): ("cleveland", "trim16"),
    ("cpi70", "median"): ("cleveland", "median"),
    ("cpi70", "trim16"): ("cleveland", "trim16"),
    ("pce", "trim_pce"): ("dallas", "trim_pce"),
}

#: The revised-vintage Cleveland series and the current Dallas methodology both
#: cover this span cleanly; earlier months mix vintages.
DEFAULT_START = "1998-01-01"


@dataclass
class Comparison:
    """One (measure, horizon) comparison, in the shape the CLI prints."""

    scope: str
    measure: str
    horizon: str
    n: int
    corr: float
    rmse: float
    bias: float
    max_abs: float

    def as_row(self) -> dict:
        return {"scope": self.scope, "measure": self.measure,
                "horizon": self.horizon, "n": self.n, "corr": self.corr,
                "rmse": self.rmse, "bias": self.bias, "max_abs": self.max_abs}


def _score(ours: pd.Series, official: pd.Series, start: Optional[str],
           scope: str, measure: str, horizon: str) -> Optional[Comparison]:
    both = pd.concat([ours.rename("ours"), official.rename("official")],
                     axis=1, sort=True).dropna()
    if start:
        both = both[both.index >= pd.Timestamp(start)]
    if both.empty:
        return None
    err = both["ours"] - both["official"]
    return Comparison(
        scope=scope, measure=measure, horizon=horizon, n=int(len(both)),
        corr=float(both["ours"].corr(both["official"])),
        rmse=float(np.sqrt((err ** 2).mean())),
        bias=float(err.mean()),
        max_abs=float(err.abs().max()),
    )


def official_series(force: bool = False) -> dict[str, pd.DataFrame]:
    """Fetch both banks' published histories, keyed ``cleveland`` / ``dallas``."""
    return {"cleveland": cleveland_history(force=force),
            "dallas": dallas_history(force=force)}


def compare_to_official(
    panel: TrimPanel,
    measures: Optional[dict[str, TrimConfig]] = None,
    official: Optional[dict[str, pd.DataFrame]] = None,
    start: Optional[str] = DEFAULT_START,
    force: bool = False,
) -> pd.DataFrame:
    """Score one scope's measures against the published series.

    Returns a tidy frame ``[scope, measure, horizon, n, corr, rmse, bias,
    max_abs]``; measures with no published counterpart are skipped rather than
    scored against something they are not.
    """
    measures = measures or {"median": MEDIAN_CPI, "trim16": TRIM16_CPI,
                            "trim_pce": TRIM_PCE}
    official = official or official_series(force=force)

    rows = []
    for name, base in measures.items():
        target = OFFICIAL.get((panel.key, name))
        if target is None:
            continue
        bank, series = target
        pub = official.get(bank)
        if pub is None:
            continue

        cfg = TrimConfig(lower=base.lower, upper=base.upper, sa=panel.sa,
                         periods_per_year=panel.periods_per_year)
        res = compute_trim(panel.inflation, panel.weights, cfg)

        if bank == "cleveland":
            pairs = [("1m", res.rate, pub.get(f"{series}_saar")),
                     ("12m", res.yoy, pub.get(f"{series}_yoy"))]
        else:
            pairs = [("1m", res.rate, pub.get("m1")),
                     ("12m", res.yoy, pub.get("m12"))]

        for horizon, ours, theirs in pairs:
            if theirs is None:
                continue
            c = _score(ours, theirs, start, panel.key, name, horizon)
            if c is not None:
                rows.append(c.as_row())
    return pd.DataFrame(rows)


def compare_latest_cross_section(
    panel: TrimPanel,
    bank: str = "cleveland",
    force: bool = False,
    cfg: Optional[TrimConfig] = None,
) -> pd.DataFrame:
    """Join our latest-month cross-section onto the bank's component table.

    The published tables are keyed by component *name*, ours by item code, so
    the join is on a normalised label.  Unmatched rows are kept with NaNs on one
    side -- an unmatched component is exactly the kind of thing worth seeing.

    Returns ``[component, rate_ours, rate_official, d_rate, w_ours,
    w_official, d_weight]`` with weights in percent.
    """
    cfg = cfg or TrimConfig(sa=panel.sa, periods_per_year=panel.periods_per_year)
    res = compute_trim(panel.inflation, panel.weights, cfg)

    valid = res.n_categories[res.n_categories > 0]
    if valid.empty:
        return pd.DataFrame()
    last = valid.index[-1]

    ours = pd.DataFrame({
        "label": [panel.labels.get(c, c) for c in panel.inflation.columns],
        "rate_ours": res.sa_panel.loc[last].to_numpy(),
        "w_ours": 100.0 * res.weights.loc[last].to_numpy(),
    })
    ours["join"] = ours["label"].map(_norm)

    if bank == "cleveland":
        pub = cleveland_components(force=force).rename(
            columns={"rate_ann": "rate_official", "ri": "w_official"})
    else:
        pub = dallas_detail(force=force).rename(
            columns={"rate_ann": "rate_official", "weight": "w_official"})
    pub["join"] = pub["component"].map(_norm)

    merged = ours.merge(pub[["component", "join", "rate_official", "w_official"]],
                        on="join", how="outer")
    merged["component"] = merged["component"].fillna(merged["label"])
    merged["d_rate"] = merged["rate_ours"] - merged["rate_official"]
    merged["d_weight"] = merged["w_ours"] - merged["w_official"]
    merged.attrs["month"] = str(last.date())
    return merged[["component", "rate_ours", "rate_official", "d_rate",
                   "w_ours", "w_official", "d_weight"]].sort_values(
        "w_official", ascending=False, na_position="last").reset_index(drop=True)


def _norm(label: str) -> str:
    """Loose label key: lower case, no punctuation, no filler words.

    The two banks and BLS all name the same component slightly differently
    ("Watches and jewelry" / "Jewelry and watches", "Water, sewer, and trash
    collection services" / "Water and sewer and trash collection services"), so
    the join sorts the words rather than trusting the order.
    """
    import re
    s = re.sub(r"[^a-z0-9 ]", " ", str(label).lower())
    words = [w for w in s.split() if w not in {"and", "the", "of", "in", "or"}]
    return " ".join(sorted(words))


def summarise(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate several :func:`compare_to_official` results for printing."""
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
