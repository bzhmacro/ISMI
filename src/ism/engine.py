"""
ism.engine
==========

Core computation of the Inflation Shock Momentum (ISM) index from
Lansing & Shapiro (2026), "Measuring Inflation Shock Momentum",
FRBSF Working Paper 2026-10.

This module is deliberately written so that each function maps cleanly onto a
numbered equation in the paper. Read it side-by-side with Section 2.1
("Methodology"). The mapping is:

    Eq. (3)   pi_{i,t} = mu_i + rho_i * pi_{i,t-1} + eps_{i,t}
              -> rolling_ar_residuals()           (per category, 120-month window)

    Eq. (4)   M+_{i,t} = prod_{k=0}^{K-1} 1(eps_{i,t-k} > 0)
    Eq. (5)   M-_{i,t} = prod_{k=0}^{K-1} 1(eps_{i,t-k} < 0)
              -> momentum_signals()

    Eq. (6)   S+_t = sum_i w_{i,t} * M+_{i,t}
    Eq. (7)   S-_t = sum_i w_{i,t} * M-_{i,t}
              -> expenditure_weighted_shares()

    Eq. (8)   ISM_t = S+_t - S-_t
              -> ism_index()

The top-level convenience function `compute_ism` ties these together and is the
function most users will call.

Design notes
------------
* Everything is vectorised with pandas / numpy for readability and speed, but no
  step is "magic": each is a direct, auditable translation of the equations.
* The benchmark data-generating process (DGP) is an AR(p). The paper's baseline
  is AR(1); robustness uses AR(3) and AR(12). `ar_order` exposes this.
* The momentum run length is K (paper baseline K=3); `run_length` exposes this.
* The rolling window length is W months (paper baseline W=120); `window` exposes
  this.

All of these are parameters, not hard-coded constants, so the same engine can be
re-pointed at other countries / datasets (one of the project's stated goals).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ISMConfig:
    """Parameters that define a particular ISM specification.

    Attributes
    ----------
    ar_order:
        Order p of the benchmark AR(p) DGP estimated on each category's monthly
        inflation (Eq. 3). Paper baseline = 1.
    window:
        Length W (in months) of the rolling estimation window. Paper baseline =
        120 (10 years).
    run_length:
        Number K of consecutive same-signed residuals required to flag momentum
        (Eqs. 4-5). Paper baseline = 3.
    min_obs:
        Minimum number of usable observations required inside a window to bother
        estimating the AR(p). Defaults to the full window.
    """

    ar_order: int = 1
    window: int = 120
    run_length: int = 3
    min_obs: Optional[int] = None

    def __post_init__(self):
        if self.min_obs is None:
            object.__setattr__(self, "min_obs", self.window)


# ----------------------------------------------------------------------------
# Eq. (3): rolling AR(p) residuals, one category at a time
# ----------------------------------------------------------------------------
def _ar_design_matrix(y: np.ndarray, p: int) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, Y) for an AR(p) regression with intercept.

    Given a 1-D series y of length n, returns
        Y : shape (n-p,)            the dependent values y_t for t = p..n-1
        X : shape (n-p, p+1)        columns [1, y_{t-1}, ..., y_{t-p}]

    This is the textbook AR(p) layout; for p=1 it is exactly Eq. (3):
        pi_t = mu + rho * pi_{t-1} + eps_t
    """
    n = len(y)
    Y = y[p:]
    cols = [np.ones(n - p)]  # intercept (mu)
    for lag in range(1, p + 1):
        cols.append(y[p - lag : n - lag])  # y_{t-lag}
    X = np.column_stack(cols)
    return X, Y


def rolling_ar_residuals(
    inflation: pd.Series,
    cfg: ISMConfig,
) -> pd.Series:
    """Estimate Eq. (3) on rolling W-month windows and collect residuals.

    For each window ending at month t, we OLS-estimate the AR(p) model on the W
    observations in that window and record the residual at the window's *end*
    date (the most recent residual). Advancing the window one month at a time
    yields one residual per month, which is the object the paper's filter acts
    on:

        "For each rolling-window regression, the reduced-form residuals eps_{i,t}
         are collected and then used to identify whether each category i exhibits
         positive or negative inflation shock momentum near the end date of the
         rolling window in month t."  (Section 2.1)

    Parameters
    ----------
    inflation:
        Monthly inflation for a *single* category, indexed by a monthly
        DatetimeIndex (or PeriodIndex), sorted ascending.
    cfg:
        ISMConfig with ar_order, window, min_obs.

    Returns
    -------
    pd.Series
        Residual eps_t at each month t for which a full window was available,
        aligned to `inflation`'s index. Months without enough data are NaN.

    Notes
    -----
    We need the *last K* residuals of each window to evaluate the momentum
    runs (Eqs. 4-5). Because consecutive windows overlap heavily, the residual
    we keep for month t is the one estimated in the window that *ends* at t.
    This matches the paper's "near the end date of the rolling window"
    description and makes the K-month run a property of recent, same-vintage
    residuals.
    """
    y = inflation.to_numpy(dtype=float)
    n = len(y)
    p, W = cfg.ar_order, cfg.window
    resid = np.full(n, np.nan)

    # A window of W raw inflation points yields (W - p) AR(p) regression rows.
    # `end` is the index (inclusive) of the last inflation point in the window.
    for end in range(W - 1, n):
        start = end - W + 1
        y_win = y[start : end + 1]

        # Skip windows with insufficient finite data (e.g. category not yet born).
        finite = np.isfinite(y_win)
        if finite.sum() < cfg.min_obs:
            continue
        if not np.all(finite):
            # If there are interior gaps we cannot form a clean AR(p) design;
            # treat the window as unusable rather than silently interpolating.
            continue

        X, Y = _ar_design_matrix(y_win, p)
        # OLS via least squares (readable; numerically stable enough for W~120).
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
        fitted = X @ beta
        residuals_win = Y - fitted

        # The residual at the window's end date is the LAST element.
        resid[end] = residuals_win[-1]

    return pd.Series(resid, index=inflation.index, name=inflation.name)


def residual_panel(
    inflation_panel: pd.DataFrame,
    cfg: ISMConfig,
) -> pd.DataFrame:
    """Apply `rolling_ar_residuals` to every category column.

    Parameters
    ----------
    inflation_panel:
        DataFrame of monthly inflation, rows = months (DatetimeIndex), columns =
        categories.
    cfg:
        ISMConfig.

    Returns
    -------
    pd.DataFrame
        Same shape, holding the rolling-window residual eps_{i,t} for each
        category i and month t.
    """
    return inflation_panel.apply(lambda col: rolling_ar_residuals(col, cfg))


# ----------------------------------------------------------------------------
# Eqs. (4)-(5): momentum signals from runs of same-signed residuals
# ----------------------------------------------------------------------------
def momentum_signals(
    residuals: pd.DataFrame,
    cfg: ISMConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute M+ and M- indicator panels (Eqs. 4-5).

    A category i has *positive* momentum at month t if its residual was strictly
    positive in each of the last K months (t, t-1, ..., t-K+1):

        M+_{i,t} = prod_{k=0}^{K-1} 1(eps_{i,t-k} > 0)        (Eq. 4)
        M-_{i,t} = prod_{k=0}^{K-1} 1(eps_{i,t-k} < 0)        (Eq. 5)

    Returns two 0/1 DataFrames (M_pos, M_neg) aligned to `residuals`.

    Implementation
    --------------
    `1(eps>0)` is a boolean panel. A run of K consecutive Trues is detected with
    a rolling window product (equivalently, rolling sum == K). We use
    min_periods=K so the first K-1 rows are NaN -> treated as no signal (0).
    """
    K = cfg.run_length

    pos = (residuals > 0).astype(float)
    neg = (residuals < 0).astype(float)

    # rolling product over the last K rows; NaN residuals -> 0 indicator -> the
    # product is 0, i.e. a NaN month correctly breaks a run.
    m_pos = pos.rolling(window=K, min_periods=K).apply(np.prod, raw=True)
    m_neg = neg.rolling(window=K, min_periods=K).apply(np.prod, raw=True)

    m_pos = m_pos.fillna(0.0)
    m_neg = m_neg.fillna(0.0)
    return m_pos, m_neg


# ----------------------------------------------------------------------------
# Eqs. (6)-(7): expenditure-weighted shares
# ----------------------------------------------------------------------------
def expenditure_weighted_shares(
    m_pos: pd.DataFrame,
    m_neg: pd.DataFrame,
    weights: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """Aggregate category momentum into PCE-basket shares (Eqs. 6-7).

        S+_t = sum_i w_{i,t} * M+_{i,t}                        (Eq. 6)
        S-_t = sum_i w_{i,t} * M-_{i,t}                        (Eq. 7)

    Parameters
    ----------
    m_pos, m_neg:
        0/1 momentum panels from `momentum_signals`.
    weights:
        Expenditure weights w_{i,t}, same shape/columns as the momentum panels.
        Each row should sum to ~1 across categories present that month (the
        engine re-normalises defensively over the categories actually available
        in month t, so that S+ and S- are interpretable as basket shares even
        when some categories are missing at the start of the sample).

    Returns
    -------
    (S_pos, S_neg) : two pd.Series indexed by month.
    """
    # Align everything on common columns/index.
    cols = m_pos.columns
    w = weights.reindex(columns=cols)

    # Defensive per-month renormalisation over categories with a finite weight
    # AND a defined momentum value this month. This keeps S in [0, 1].
    valid = m_pos.notna() & m_neg.notna() & w.notna()
    w_eff = w.where(valid, other=np.nan)
    row_sums = w_eff.sum(axis=1)
    w_norm = w_eff.div(row_sums.replace(0, np.nan), axis=0)

    s_pos = (w_norm * m_pos).sum(axis=1)
    s_neg = (w_norm * m_neg).sum(axis=1)
    s_pos.name = "S_pos"
    s_neg.name = "S_neg"
    return s_pos, s_neg


# ----------------------------------------------------------------------------
# Eq. (8): the index itself
# ----------------------------------------------------------------------------
def ism_index(s_pos: pd.Series, s_neg: pd.Series) -> pd.Series:
    """ISM_t = S+_t - S-_t   (Eq. 8)."""
    out = (s_pos - s_neg)
    out.name = "ISM"
    return out


# ----------------------------------------------------------------------------
# Top-level convenience wrapper
# ----------------------------------------------------------------------------
@dataclass
class ISMResult:
    """Bundle of everything produced by `compute_ism`, for inspection/plots."""

    ism: pd.Series
    s_pos: pd.Series
    s_neg: pd.Series
    residuals: pd.DataFrame
    m_pos: pd.DataFrame
    m_neg: pd.DataFrame
    config: ISMConfig = field(default_factory=ISMConfig)

    def to_frame(self) -> pd.DataFrame:
        """The headline three series as a tidy DataFrame (ISM, S+, S-)."""
        return pd.concat(
            [self.ism, self.s_pos, self.s_neg], axis=1
        ).rename(columns={"S_pos": "Positive Momentum", "S_neg": "Negative Momentum"})


def compute_ism(
    inflation_panel: pd.DataFrame,
    weights: pd.DataFrame,
    cfg: ISMConfig | None = None,
) -> ISMResult:
    """End-to-end ISM computation (Eqs. 3-8).

    Parameters
    ----------
    inflation_panel:
        Monthly category inflation. Rows = months (sorted DatetimeIndex),
        columns = categories. This is pi_{i,t} in Eq. (3).
    weights:
        Monthly expenditure weights w_{i,t}, same rows/columns. Nominal PCE
        shares from BEA table 2.4.5U; the engine renormalises each row.
    cfg:
        ISMConfig (defaults to the paper baseline: AR(1), W=120, K=3).

    Returns
    -------
    ISMResult
    """
    cfg = cfg or ISMConfig()

    # Eq. (3): residuals from the rolling AR(p) benchmark, per category.
    residuals = residual_panel(inflation_panel, cfg)

    # Eqs. (4)-(5): same-signed runs of length K -> momentum indicators.
    m_pos, m_neg = momentum_signals(residuals, cfg)

    # Eqs. (6)-(7): expenditure-weighted positive / negative shares.
    s_pos, s_neg = expenditure_weighted_shares(m_pos, m_neg, weights)

    # Eq. (8): net diffusion index.
    ism = ism_index(s_pos, s_neg)

    return ISMResult(
        ism=ism,
        s_pos=s_pos,
        s_neg=s_neg,
        residuals=residuals,
        m_pos=m_pos,
        m_neg=m_neg,
        config=cfg,
    )
