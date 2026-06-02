"""
ism.forecasting
===============

In-sample forecast regressions (paper Table 1) and scaffolding for the
out-of-sample adaptive-LASSO exercise (Table 2). Kept readable: the regression
is a single, explicit OLS with robust standard errors.

Table 1 specification
---------------------
Dependent variable: the h-months-ahead value of 12-month PCE inflation,
    y_t = pi^{12m}_{t+h}.
Baseline regressors: a constant and current 12-month PCE inflation.
Then add EITHER the ISM index OR its two components S+ and S-, and OPTIONALLY
the control block (3-month PCE inflation, 1-yr inflation expectations, V/U, oil
price, S&P 500 level, real disposable income y/y growth, 10yr-FFR spread, NBER
recession dummy). Robust (HC1) standard errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd

try:
    import statsmodels.api as sm
except ImportError:
    sm = None


CONTROL_COLS = [
    "pce_3m", "infl_exp_1y", "vu_ratio", "oil_wti",
    "sp500", "rdpi_yoy", "spread_10y_ffr", "nber_recession",
]


@dataclass
class RegressionResult:
    spec: str
    horizon: int
    params: pd.Series
    bse: pd.Series
    rsquared: float
    rsquared_adj: float
    nobs: int

    def coef_with_se(self, name: str) -> str:
        if name not in self.params:
            return ""
        return f"{self.params[name]:.3f} ({self.bse[name]:.3f})"


def _build_target(pce_yoy: pd.Series, horizon: int) -> pd.Series:
    """y_t = 12-month PCE inflation observed h months ahead (pi^{12m}_{t+h})."""
    return pce_yoy.shift(-horizon).rename(f"target_h{horizon}")


def in_sample_regression(
    pce_yoy: pd.Series,
    ism: pd.Series,
    horizon: int,
    momentum: str = "ism",          # 'none' | 'ism' | 'components'
    s_pos: Optional[pd.Series] = None,
    s_neg: Optional[pd.Series] = None,
    controls: Optional[pd.DataFrame] = None,
    use_controls: bool = False,
) -> RegressionResult:
    """Estimate one column of Table 1 with HC1-robust standard errors."""
    if sm is None:
        raise RuntimeError("statsmodels is required: pip install statsmodels")

    y = _build_target(pce_yoy, horizon)
    X = pd.DataFrame({"pce_yoy": pce_yoy})

    if momentum == "ism":
        X["ISM"] = ism
    elif momentum == "components":
        X["S_pos"] = s_pos
        X["S_neg"] = s_neg
    elif momentum != "none":
        raise ValueError("momentum must be 'none', 'ism', or 'components'")

    if use_controls:
        if controls is None:
            raise ValueError("use_controls=True but no controls frame supplied")
        for c in CONTROL_COLS:
            if c in controls.columns:
                X[c] = controls[c]

    data = pd.concat([y, X], axis=1).dropna()
    yv = data[y.name]
    Xv = sm.add_constant(data[X.columns])
    model = sm.OLS(yv, Xv).fit(cov_type="HC1")

    spec = f"{momentum}{'+controls' if use_controls else ''}"
    return RegressionResult(
        spec=spec, horizon=horizon, params=model.params, bse=model.bse,
        rsquared=float(model.rsquared), rsquared_adj=float(model.rsquared_adj),
        nobs=int(model.nobs),
    )


def table1(
    pce_yoy: pd.Series,
    ism: pd.Series,
    s_pos: pd.Series,
    s_neg: pd.Series,
    controls: Optional[pd.DataFrame] = None,
    horizons: Sequence[int] = (12, 24),
) -> pd.DataFrame:
    """Reproduce the full Table 1 grid as a tidy DataFrame.

    Per horizon, runs: (1) baseline, (2) +components, (3) +ISM, and with controls
    (4) baseline, (5) +components, (6) +ISM. If `controls` is None, only 1-3 run.
    """
    specs = [
        ("none", False), ("components", False), ("ism", False),
        ("none", True),  ("components", True),  ("ism", True),
    ]
    if controls is None:
        specs = specs[:3]

    rows = []
    for h in horizons:
        for i, (mom, ctrl) in enumerate(specs, start=1):
            r = in_sample_regression(
                pce_yoy, ism, h, momentum=mom, s_pos=s_pos, s_neg=s_neg,
                controls=controls, use_controls=ctrl,
            )
            rows.append({
                "horizon": h, "col": i, "spec": r.spec,
                "pce_yoy": r.coef_with_se("pce_yoy"),
                "ISM": r.coef_with_se("ISM"),
                "S_pos": r.coef_with_se("S_pos"),
                "S_neg": r.coef_with_se("S_neg"),
                "R2": round(r.rsquared, 3),
                "adjR2": round(r.rsquared_adj, 3),
                "N": r.nobs,
            })
    return pd.DataFrame(rows)
