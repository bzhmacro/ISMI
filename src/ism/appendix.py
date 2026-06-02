"""
ism.appendix
============

Helpers for the paper's appendix exhibits (Figures A1-A8, Tables A1-A6). These
build on the core engine and keep each appendix idea as a small, auditable
function.

Contents
--------
* run_probability               -> Fig A3 (arcsine / Sheppard run probability)
* consecutive_run_shares        -> Fig A2 (empirical share with >=k same-sign runs)
* rolling_rho_alpha             -> Fig A1a / Table A6 (two-step rho-hat, alpha-hat)
* rho_panel                     -> Fig A1b (per-category rolling rho-hat)
* aggregate_ism                 -> Fig A5 / Table A5 (ternary aggregate-data ISM)
* compute_ism_weighted          -> Tables A3 / A4 (momentum weighted by size or
                                   inflation stickiness 1/(1-rho))
The AR-order and k robustness variants (Fig A4b/A7, Table A1) need no new code:
call the core `compute_ism` / `forecasting.table1` with a different `ISMConfig`.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .engine import ISMConfig, momentum_signals, residual_panel, rolling_ar_residuals


# ---------------------------------------------------------------------------
# Fig A3: theoretical probability of a run of same-signed residuals
# ---------------------------------------------------------------------------
def run_probability(alpha: np.ndarray | float, k: int, same_sign_either: bool = False):
    """Probability of at least k consecutive positive residuals for an AR(1) with
    persistence `alpha` (Appendix B).

        p   = 1/2 + (1/pi) * arcsin(alpha)            # one-step sign persistence
        P_k = P(eps>0) * p^(k-1) = 0.5 * p^(k-1)      # >=k consecutive positives

    If `same_sign_either` is True, returns the probability of >=k consecutive of
    *either* sign (twice the one-sign probability).
    """
    a = np.asarray(alpha, dtype=float)
    p = 0.5 + np.arcsin(np.clip(a, -1, 1)) / np.pi
    Pk = 0.5 * p ** (k - 1)
    return 2 * Pk if same_sign_either else Pk


# ---------------------------------------------------------------------------
# Fig A2: empirical share of observations in a >=k consecutive same-sign run
# ---------------------------------------------------------------------------
def consecutive_run_shares(residuals: pd.DataFrame, kmax: int = 5) -> pd.DataFrame:
    """Share of all (category, month) residual observations that sit at the end of
    a run of at least k consecutive positive (or negative) residuals, k=1..kmax.

    Mirrors Fig A2: at k=3 the positive share is ~20% and negative ~15%.
    """
    finite = residuals.notna().to_numpy().sum()
    rows = []
    for k in range(1, kmax + 1):
        cfg = ISMConfig(run_length=k)
        mp, mn = momentum_signals(residuals, cfg)
        rows.append({
            "k": k,
            "positive_share": float(mp.to_numpy().sum() / finite),
            "negative_share": float(mn.to_numpy().sum() / finite),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fig A1a / Table A6: two-step rho-hat and alpha-hat on aggregate inflation
# ---------------------------------------------------------------------------
def _ols_ar1(y: np.ndarray):
    """Return (intercept, slope, residuals) for an AR(1) OLS on a 1-D array."""
    Y = y[1:]
    X = np.column_stack([np.ones(len(Y)), y[:-1]])
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ beta
    return beta[0], beta[1], resid


def rolling_rho_alpha(agg_inflation: pd.Series, window: int = 120, rho_cap: Optional[float] = None) -> pd.DataFrame:
    """Two-step rolling estimates of inflation inertia rho and shock momentum alpha.

    For each 120-month window of aggregate monthly inflation:
      step 1: AR(1) on inflation              -> rho_hat, residuals eps
      step 2: AR(1) on those residuals eps    -> alpha_hat
    Recorded at the window's end date. (Used for Fig A1a and the Table A6 measure.)
    """
    y = agg_inflation.to_numpy(float)
    n = len(y)
    idx = agg_inflation.index
    rho = np.full(n, np.nan)
    alpha = np.full(n, np.nan)
    for end in range(window - 1, n):
        yw = y[end - window + 1: end + 1]
        if not np.all(np.isfinite(yw)):
            continue
        _, rho_hat, eps = _ols_ar1(yw)
        _, alpha_hat, _ = _ols_ar1(eps)
        rho[end] = min(rho_hat, rho_cap) if rho_cap is not None else rho_hat
        alpha[end] = alpha_hat
    return pd.DataFrame({"rho_hat": rho, "alpha_hat": alpha}, index=idx)


# ---------------------------------------------------------------------------
# Fig A1b: per-category rolling rho-hat
# ---------------------------------------------------------------------------
def rolling_rho(inflation: pd.Series, cfg: ISMConfig) -> pd.Series:
    """Rolling AR(1) slope (rho-hat) for a single category, at each window end."""
    y = inflation.to_numpy(float)
    n = len(y)
    out = np.full(n, np.nan)
    for end in range(cfg.window - 1, n):
        yw = y[end - cfg.window + 1: end + 1]
        if not np.all(np.isfinite(yw)):
            continue
        _, rho_hat, _ = _ols_ar1(yw)
        out[end] = rho_hat
    return pd.Series(out, index=inflation.index, name=inflation.name)


def rho_panel(inflation_panel: pd.DataFrame, cfg: ISMConfig | None = None) -> pd.DataFrame:
    """Per-category rolling rho-hat panel (for the Fig A1b percentile fan)."""
    cfg = cfg or ISMConfig()
    return inflation_panel.apply(lambda c: rolling_rho(c, cfg))


# ---------------------------------------------------------------------------
# Fig A5 / Table A5: aggregate-data ISM (ternary -1/0/1)
# ---------------------------------------------------------------------------
def aggregate_ism(agg_inflation: pd.Series, cfg: ISMConfig | None = None) -> pd.DataFrame:
    """Non-parametric ISM computed on the AGGREGATE inflation series alone.

    One AR(1) rolling residual series -> M+ / M- in {0,1}; the index is M+ - M-
    in {-1, 0, 1} (Fig A5). Returns columns [ISM_agg, M_pos, M_neg].
    """
    cfg = cfg or ISMConfig()
    resid = rolling_ar_residuals(agg_inflation, cfg)
    mp, mn = momentum_signals(resid.to_frame("agg"), cfg)
    out = pd.DataFrame({"M_pos": mp["agg"], "M_neg": mn["agg"]})
    out["ISM_agg"] = out["M_pos"] - out["M_neg"]
    return out


# ---------------------------------------------------------------------------
# Tables A3 / A4: momentum weighted by shock size or inflation stickiness
# ---------------------------------------------------------------------------
def compute_ism_weighted(
    inflation_panel: pd.DataFrame,
    weights: pd.DataFrame,
    cfg: ISMConfig | None = None,
    scheme: str = "size",          # "size" (Table A3) | "stickiness" (Table A4)
    rho_cap: float = 0.9,
) -> pd.DataFrame:
    """ISM where each momentum signal is multiplied by a strength factor.

    scheme="size"       : M+/- *= |sum of the last k residuals|            (Eq. 10-11)
    scheme="stickiness" : M+/- *= 1/(1-rho_hat_i), rho capped at rho_cap   (Eq. 12-13)

    Returns columns [ISM, S_pos, S_neg]. Compare to the baseline (extensive-margin)
    index to see that most predictive content is on the sign, not the size.
    """
    cfg = cfg or ISMConfig()
    K = cfg.run_length
    resid = residual_panel(inflation_panel, cfg)
    mp, mn = momentum_signals(resid, cfg)

    if scheme == "size":
        roll_sum = resid.rolling(K, min_periods=K).sum()
        factor_pos = roll_sum.abs()
        factor_neg = roll_sum.abs()
    elif scheme == "stickiness":
        rp = rho_panel(inflation_panel, cfg).clip(upper=rho_cap)
        stick = 1.0 / (1.0 - rp)
        factor_pos = stick
        factor_neg = stick
    else:
        raise ValueError("scheme must be 'size' or 'stickiness'")

    mp_w = (mp * factor_pos).reindex_like(mp).fillna(0.0)
    mn_w = (mn * factor_neg).reindex_like(mn).fillna(0.0)

    w = weights.reindex(columns=mp.columns)
    valid = mp.notna() & mn.notna() & w.notna()
    wn = w.where(valid).div(w.where(valid).sum(axis=1).replace(0, np.nan), axis=0)
    s_pos = (wn * mp_w).sum(axis=1).rename("S_pos")
    s_neg = (wn * mn_w).sum(axis=1).rename("S_neg")
    out = pd.concat([s_pos, s_neg], axis=1)
    out["ISM"] = out["S_pos"] - out["S_neg"]
    return out
