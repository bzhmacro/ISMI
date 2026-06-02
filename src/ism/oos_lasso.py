"""
ism.oos_lasso
=============

Out-of-sample forecasting with an adaptive LASSO (paper Table 2 / Eq. 14).

Adaptive LASSO:  min_b ||y - Xb||^2 + lambda * sum_j w_j |b_j|,  w_j = 1/|b_j^OLS|.
Reparametrise g_j = w_j b_j so x~_j = x_j*|b_j^OLS|, run a plain LASSO on X~ to get
g, then b_j = g_j*|b_j^OLS|. Predictors are standardized first.

Procedure (matching the paper):
  * Direct h-step forecasts of 12-month PCE inflation, h in {12, 24, 36}.
  * Rolling 120-month estimation windows; for each window we fit the adaptive
    LASSO and forecast h months past the window end, collecting the forecast
    error.
  * The penalty lambda* is the grid value minimizing RMSFE across the collection
    of rolling-window forecasts.
  * We compare a baseline model to baseline + ISM via the RMSFE ratio and the
    Giacomini-White (2006) test of equal (conditional) predictive ability.
  * Standardized full-sample coefficients at lambda* indicate relative predictor
    importance.

This module needs scikit-learn and statsmodels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import Lasso, LinearRegression
    from sklearn.preprocessing import StandardScaler
except ImportError:
    Lasso = LinearRegression = StandardScaler = None

try:
    import statsmodels.api as sm
except ImportError:
    sm = None


# ---------------------------------------------------------------------------
# Adaptive LASSO fit / predict
# ---------------------------------------------------------------------------
@dataclass
class FittedAdaptiveLasso:
    scaler: "StandardScaler"
    beta_std: np.ndarray      # coefficients on STANDARDIZED predictors
    intercept: float
    columns: List[str]

    def predict(self, Xnew: pd.DataFrame) -> np.ndarray:
        Xs = self.scaler.transform(Xnew[self.columns].to_numpy())
        return self.intercept + Xs @ self.beta_std


def fit_adaptive_lasso(X: pd.DataFrame, y: pd.Series, lam: float) -> FittedAdaptiveLasso:
    """Fit the adaptive LASSO; returns an object with a .predict method.

    `beta_std` are coefficients on standardized predictors, so their magnitudes
    are directly comparable (the "standardized coefficients" in Table 2).
    """
    if Lasso is None:
        raise RuntimeError("scikit-learn is required: pip install scikit-learn")
    cols = list(X.columns)
    scaler = StandardScaler().fit(X.to_numpy())
    Xs = scaler.transform(X.to_numpy())
    ols = LinearRegression().fit(Xs, y.to_numpy()).coef_
    absb = np.maximum(np.abs(ols), 1e-4)          # adaptive weights = |b_ols|
    Xtilde = Xs * absb
    lasso = Lasso(alpha=lam, max_iter=50000).fit(Xtilde, y.to_numpy())
    beta_std = lasso.coef_ * absb                  # recover coef on standardized X
    return FittedAdaptiveLasso(scaler, beta_std, float(lasso.intercept_), cols)


# ---------------------------------------------------------------------------
# Rolling out-of-sample forecasts
# ---------------------------------------------------------------------------
def rolling_oos(
    X: pd.DataFrame,
    target_h: pd.Series,        # target_h[t] = 12-month PCE inflation at t+h
    lam: float,
    window: int = 120,
    min_train: int = 60,
) -> pd.DataFrame:
    """Collect rolling-window h-step forecasts and errors.

    For each window ending at row e, fit on the window's complete (X_t, target_h)
    pairs and forecast the window-end observation target_h[e]; record actual,
    forecast and error. Returns a DataFrame indexed by the forecast origin date.
    """
    idx = X.index
    recs = []
    for e in range(window - 1, len(idx)):
        Xtr = X.iloc[e - window + 1: e + 1]
        ytr = target_h.iloc[e - window + 1: e + 1]
        d = pd.concat([Xtr, ytr.rename("_y")], axis=1).dropna()
        if len(d) < min_train:
            continue
        actual = target_h.iloc[e]
        xrow = X.iloc[[e]]
        if pd.isna(actual) or xrow.isna().any(axis=None):
            continue
        fit = fit_adaptive_lasso(d[X.columns], d["_y"], lam)
        pred = float(fit.predict(xrow)[0])
        recs.append((idx[e], actual, pred, actual - pred))
    out = pd.DataFrame(recs, columns=["origin", "actual", "pred", "error"]).set_index("origin")
    return out


def rmsfe(errors: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(errors))))


def choose_lambda(
    X: pd.DataFrame, target_h: pd.Series, grid: Sequence[float], window: int = 120
) -> tuple[float, float, pd.DataFrame]:
    """Grid-search lambda minimizing rolling-window RMSFE. Returns (lam*, rmsfe*, fc)."""
    best = (None, np.inf, None)
    for lam in grid:
        fc = rolling_oos(X, target_h, lam, window)
        if len(fc) == 0:
            continue
        r = rmsfe(fc["error"].to_numpy())
        if r < best[1]:
            best = (lam, r, fc)
    return best


# ---------------------------------------------------------------------------
# Giacomini-White test of equal predictive ability
# ---------------------------------------------------------------------------
def giacomini_white(err_base: pd.Series, err_alt: pd.Series, hac_lags: Optional[int] = None):
    """Unconditional GW / Diebold-Mariano test on the loss differential.

    d_t = e_base_t^2 - e_alt_t^2. Tests E[d]=0 via HAC-robust regression of d on a
    constant. Returns dict with F-stat (= t^2), p-value, and mean loss diff.
    A positive mean diff and significant F means the alternative (e_alt) forecasts
    better (lower squared error).
    """
    if sm is None:
        raise RuntimeError("statsmodels is required: pip install statsmodels")
    j = pd.concat([err_base.rename("b"), err_alt.rename("a")], axis=1).dropna()
    d = (j["b"] ** 2 - j["a"] ** 2).rename("d")
    L = hac_lags if hac_lags is not None else int(np.ceil(len(d) ** 0.25))
    m = sm.OLS(d.to_numpy(), np.ones((len(d), 1))).fit(cov_type="HAC", cov_kwds={"maxlags": L})
    t = float(m.params[0] / m.bse[0])
    from scipy import stats
    p = 2 * (1 - stats.norm.cdf(abs(t)))
    return {"F": t ** 2, "t": t, "p": p, "mean_loss_diff": float(d.mean()), "n": int(len(d))}


# ---------------------------------------------------------------------------
# Table 2 orchestration
# ---------------------------------------------------------------------------
def _target_h(pce_yoy: pd.Series, h: int) -> pd.Series:
    return pce_yoy.shift(-h).rename(f"y_h{h}")


def table2(
    pce_yoy: pd.Series,
    ism: pd.Series,
    controls: Optional[pd.DataFrame] = None,
    horizons: Sequence[int] = (12, 24, 36),
    lam_grid: Optional[Sequence[float]] = None,
    window: int = 120,
) -> pd.DataFrame:
    """Reproduce Table 2: baseline vs baseline+ISM, RMSFE ratio + GW test.

    Baseline predictors = 12m PCE inflation (+ controls if supplied). The "+ISM"
    model adds the ISM index. Returns one row per horizon with RMSFE(baseline),
    RMSFE(+ISM), the ratio, and the GW F-stat / p-value.
    """
    lam_grid = lam_grid if lam_grid is not None else np.logspace(-4, 0, 15)
    base_cols = pd.DataFrame({"pce_yoy": pce_yoy})
    if controls is not None:
        base_cols = pd.concat([base_cols, controls.drop(columns=["pce_yoy"], errors="ignore")], axis=1)

    rows = []
    for h in horizons:
        y = _target_h(pce_yoy, h)
        Xb = base_cols
        Xa = pd.concat([base_cols, ism.rename("ISM")], axis=1)
        lam_b, r_b, fc_b = choose_lambda(Xb, y, lam_grid, window)
        lam_a, r_a, fc_a = choose_lambda(Xa, y, lam_grid, window)
        gw = giacomini_white(fc_b["error"], fc_a["error"])
        rows.append({
            "h": h, "rmsfe_base": round(r_b, 4), "rmsfe_ism": round(r_a, 4),
            "rmsfe_ratio": round(r_a / r_b, 4), "GW_F": round(gw["F"], 2),
            "GW_p": round(gw["p"], 4), "lam_base": lam_b, "lam_ism": lam_a,
        })
    return pd.DataFrame(rows)
