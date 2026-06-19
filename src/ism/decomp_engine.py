r"""
ism.decomp_engine
==================

Core computation of the **supply- and demand-driven inflation decomposition** of

    Shapiro, A. H. (2024). "Decomposing Supply and Demand Driven Inflation."
    FRBSF Working Paper 2022-18. https://doi.org/10.24148/wp2022-18

This is the second model in the repo, a sibling of `ism.engine` (which
implements Lansing & Shapiro 2026, the *momentum* index). Both consume tidy
category panels and nothing here is US-specific; the difference is that this
model needs BOTH price AND quantity at the category level (the momentum index
needs only price).

Each function maps cleanly onto a numbered equation in the paper. Read it
side-by-side with Sections 2-3. The mapping is:

    Eqs. (12)-(13)  reduced-form VAR per category, on a rolling W-month window:
        q_{i,t} = c + Σ_{j=1..J} γ^{qp}_j p_{i,t-j} + Σ_{j=1..J} γ^{qq}_j q_{i,t-j} + ν^q_{i,t}
        p_{i,t} = c + Σ_{j=1..J} γ^{pp}_j p_{i,t-j} + Σ_{j=1..J} γ^{pq}_j q_{i,t-j} + ν^p_{i,t}
              -> rolling_var_residuals()          (p, q in LOG levels)

    Eqs. (8)-(11)   sign restrictions on the reduced-form residuals:
        sup(+): ν^p<0, ν^q>0     sup(-): ν^p>0, ν^q<0     (opposite signs -> supply)
        dem(+): ν^p>0, ν^q>0     dem(-): ν^p<0, ν^q<0     (same signs   -> demand)
              -> classify_labels()

    Eq. (14)        expenditure-weighted SHARES of PCE under each shock type:
        γ_{s,t} = Σ_i 1_{i∈s,t} ω_{i,t}        s ∈ {dem+, dem-, sup+, sup-}
              -> shock_shares()

    Eq. (15)        supply- / demand-driven CONTRIBUTIONS to monthly inflation:
        π_{t,t-1} = Σ_i 1_{sup,i,t} ω_{i,t-1} π_{i,t}  +  Σ_i 1_{dem,i,t} ω_{i,t-1} π_{i,t}
                    \_________ supply-driven _________/    \________ demand-driven ________/
              -> contributions()                  (Laspeyres ω_{i,t-1}; π = MoM % change)

    Section 3.1     year-over-year contribution = running product of the current
                    and past 11 monthly contributions:
        π^sup_{t,t-12} = Π_{k=0..11} (1 + π^sup_{t-k}) - 1
              -> yoy_contribution()

Robustness knobs (Section 3.2, Table 1) live on `DecompConfig`:
    * var_lags J        : baseline 12; AR-3 / AR-24 robustness use 3 / 24.
    * window W          : baseline 120 months (10 years).
    * irf_h             : 0 = one-step residual (baseline); h>0 uses the
                          h-months-ahead projection residual (Eqs. 17-18).
    * spec              : "levels" (baseline) | "diff" (Eqs. 19-20, first
                          differences) | "filter" (Hamilton-2018 filtered
                          p, q before estimation).
    * precision_cut c   : 0 = binary baseline (paper Fig. 3). c>0 re-labels a
                          category-month as "ambiguous" when |ν^p| < c·σ^p_i or
                          |ν^q| < c·σ^q_i (Fig. 5; the FRBSF *published* series
                          uses c = 0.1).

Design notes
------------
* Everything is vectorised with pandas / numpy; each step is a direct,
  auditable translation of the equations (no hidden state).
* The per-window residual is the IN-SAMPLE residual at the window's END date
  (the paper: "residuals collected for the final period of each window are used
  to label each category"). Identical convention to `ism.engine`.
* The fitted value x_t'β at the end row is a projection and is therefore unique
  even when a window is rank-deficient (e.g. a constant series), so the residual
  is well defined; this is what lets the JavaScript twin (web/decomp_engine.js),
  which solves the normal equations, match this module (which uses lstsq) to
  floating tolerance. The contract is enforced by tests/test_decomp_parity.py.
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
class DecompConfig:
    """Parameters defining a decomposition specification.

    Attributes
    ----------
    var_lags:
        Number J of own/cross lags in the reduced-form VAR (Eqs. 12-13). Paper
        baseline = 12. Table-1 robustness uses 3 ("AR-3") and 24 ("AR-24").
    window:
        Length W (months) of the rolling estimation window. Baseline = 120.
    irf_h:
        0 (baseline) -> one-step in-sample residual at the window end.
        h>0          -> residual from the h-months-ahead local projection of the
                        dependent variable (Eqs. 17-18; Table-1 "IRF (h mon.)").
    spec:
        "levels" (baseline) -> regress log p, log q on their lags.
        "diff"              -> regress Δlog p, Δlog q on lagged differences
                               (Eqs. 19-20; Table-1 "First diff").
        "filter"            -> the inputs are already Hamilton-(2018) filtered
                               (handled in the pipeline); estimation is unchanged.
    precision_cut:
        c ≥ 0. 0 = binary labels (paper baseline). c>0 marks a category-month as
        ambiguous when |ν^p_{i,t}| < c·σ^p_i or |ν^q_{i,t}| < c·σ^q_i, where σ_i
        is that category's own rolling residual standard deviation. The FRBSF
        published data use c = 0.1.
    min_obs:
        Minimum finite observations required in a window to estimate it.
        Defaults to the full window.
    """

    var_lags: int = 12
    window: int = 120
    irf_h: int = 0
    spec: str = "levels"
    precision_cut: float = 0.0
    min_obs: Optional[int] = None

    def __post_init__(self):
        if self.min_obs is None:
            object.__setattr__(self, "min_obs", self.window)
        if self.spec not in ("levels", "diff", "filter"):
            raise ValueError("spec must be 'levels', 'diff', or 'filter'")


# ----------------------------------------------------------------------------
# Eqs. (12)-(13): rolling reduced-form VAR residuals, one category at a time
# ----------------------------------------------------------------------------
def _var_design(
    p: np.ndarray, q: np.ndarray, J: int, h: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Build the shared regressor matrix X and the two dependent vectors.

    For the baseline (h = 0) and a window's log-price/log-quantity arrays p, q
    (length W), the regression rows are t = J .. W-1 with

        X_t = [1, p_{t-1}, ..., p_{t-J}, q_{t-1}, ..., q_{t-J}]   (1 + 2J cols)
        Yp_t = p_t      Yq_t = q_t

    For the IRF spec (h > 0, Eqs. 17-18) the dependent becomes the h-step change
    x_t - x_{t-h-1} and the regressors are lagged by h:
        X_t = [1, p_{t-1-h}, ..., p_{t-J-h}, q_{t-1-h}, ..., q_{t-J-h}]
    so the last usable row still ends at t = W-1 and its residual is the
    h-months-ahead projection error attributed to month W-1.

    Returns (X, Yp, Yq, end_row) where end_row is the index (into the returned
    rows) of the window's last date.
    """
    W = len(p)
    base = J + h                      # first regressable t
    idx = np.arange(base, W)
    cols = [np.ones(len(idx))]
    for lag in range(1 + h, J + 1 + h):
        cols.append(p[idx - lag])
    for lag in range(1 + h, J + 1 + h):
        cols.append(q[idx - lag])
    X = np.column_stack(cols)
    if h == 0:
        Yp = p[idx]
        Yq = q[idx]
    else:
        Yp = p[idx] - p[idx - h - 1]
        Yq = q[idx] - q[idx - h - 1]
    return X, Yp, Yq, len(idx) - 1


def rolling_var_residuals(
    log_price: pd.DataFrame,
    log_quantity: pd.DataFrame,
    cfg: DecompConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate Eqs. (12)-(13) on rolling W-month windows; collect (ν^p, ν^q).

    Parameters
    ----------
    log_price, log_quantity:
        Aligned wide panels [months x categories] of the LOG price index and
        LOG quantity index. For spec="diff" pass the log *first differences*
        (the pipeline supplies these); for spec="filter" pass the Hamilton-2018
        filtered logs. The estimation code is identical in all three cases.
    cfg:
        DecompConfig.

    Returns
    -------
    (resid_p, resid_q):
        Two panels aligned to the inputs. resid_*[i, t] is the reduced-form
        residual ν^*_{i,t} at month t (the window ending at t); NaN where no
        clean window was available.
    """
    if not log_price.columns.equals(log_quantity.columns):
        common = log_price.columns.intersection(log_quantity.columns)
        log_price, log_quantity = log_price[common], log_quantity[common]
    if not log_price.index.equals(log_quantity.index):
        idx = log_price.index.intersection(log_quantity.index)
        log_price, log_quantity = log_price.loc[idx], log_quantity.loc[idx]

    index, cols = log_price.index, log_price.columns
    P = log_price.to_numpy(dtype=float)
    Q = log_quantity.to_numpy(dtype=float)
    rp = np.full(P.shape, np.nan)
    rq = np.full(P.shape, np.nan)

    J, W, h = cfg.var_lags, cfg.window, cfg.irf_h
    n = len(index)
    if not (W > n or (W - J - h) < (2 * J + 2)):
        for c in range(P.shape[1]):
            p_all, q_all = P[:, c], Q[:, c]
            for end in range(W - 1, n):
                s = end - W + 1
                p_win, q_win = p_all[s : end + 1], q_all[s : end + 1]
                finite = np.isfinite(p_win) & np.isfinite(q_win)
                if finite.sum() < cfg.min_obs or not np.all(finite):
                    continue
                X, Yp, Yq, last = _var_design(p_win, q_win, J, h)
                # Shared design -> one pseudo-inverse, two right-hand sides.
                beta_p, *_ = np.linalg.lstsq(X, Yp, rcond=None)
                beta_q, *_ = np.linalg.lstsq(X, Yq, rcond=None)
                rp[end, c] = Yp[last] - X[last] @ beta_p
                rq[end, c] = Yq[last] - X[last] @ beta_q

    return (pd.DataFrame(rp, index=index, columns=cols),
            pd.DataFrame(rq, index=index, columns=cols))


# ----------------------------------------------------------------------------
# Eqs. (8)-(11): sign restrictions -> category labels
# ----------------------------------------------------------------------------
@dataclass
class Labels:
    """0/1 indicator panels for the four shock types + ambiguous + roll-ups."""

    sup_pos: pd.DataFrame   # ν^p<0, ν^q>0   (Eq. 10)
    sup_neg: pd.DataFrame   # ν^p>0, ν^q<0   (Eq. 11)
    dem_pos: pd.DataFrame   # ν^p>0, ν^q>0   (Eq. 8)
    dem_neg: pd.DataFrame   # ν^p<0, ν^q<0   (Eq. 9)
    supply: pd.DataFrame    # sup_pos | sup_neg   (opposite-signed residuals)
    demand: pd.DataFrame    # dem_pos | dem_neg   (same-signed residuals)
    ambiguous: pd.DataFrame # residual(s) too close to zero (precision_cut > 0)


def _rolling_resid_sd(resid: pd.DataFrame, window: int) -> pd.DataFrame:
    """Per-category rolling standard deviation of a residual panel.

    Used for the precision (ambiguous) labeling: σ^*_i in |ν^*| < c·σ^*_i. We
    use the trailing `window`-month sample SD of the collected residuals, the
    natural "category-specific standard deviation" referenced in the paper.
    """
    mp = min(window, max(12, window // 4))
    return resid.rolling(window=window, min_periods=mp).std()


def classify_labels(
    resid_p: pd.DataFrame,
    resid_q: pd.DataFrame,
    cfg: DecompConfig,
) -> Labels:
    """Label each category-month from the residual signs (Eqs. 8-11).

    With `cfg.precision_cut = c > 0`, a category-month whose price OR quantity
    residual is within c category-specific standard deviations of zero is marked
    *ambiguous* and excluded from both the supply and demand groups (Fig. 5; the
    FRBSF published series use c = 0.1).
    """
    # Work entirely in numpy so no lazy pandas boolean/where blocks survive.
    index, columns = resid_p.index, resid_p.columns
    p = resid_p.to_numpy(dtype=float)
    q = resid_q.to_numpy(dtype=float)
    defined = np.isfinite(p) & np.isfinite(q)

    amb = np.zeros_like(defined)
    if cfg.precision_cut and cfg.precision_cut > 0:
        sp = _rolling_resid_sd(resid_p, cfg.window).to_numpy(dtype=float)
        sq = _rolling_resid_sd(resid_q, cfg.window).to_numpy(dtype=float)
        c = cfg.precision_cut
        near = (np.abs(p) < c * sp) | (np.abs(q) < c * sq)
        amb = near & defined

    keep = defined & ~amb

    def ind(cond):
        # 1.0 where the (kept) condition holds, 0.0 where a residual pair is
        # defined but the condition fails, NaN where no residual pair exists.
        arr = np.where(defined, cond.astype(float), np.nan)
        return pd.DataFrame(arr, index=index, columns=columns)

    sup_pos = ind((p < 0) & (q > 0) & keep)
    sup_neg = ind((p > 0) & (q < 0) & keep)
    dem_pos = ind((p > 0) & (q > 0) & keep)
    dem_neg = ind((p < 0) & (q < 0) & keep)
    supply = ind((((p < 0) & (q > 0)) | ((p > 0) & (q < 0))) & keep)
    demand = ind((((p > 0) & (q > 0)) | ((p < 0) & (q < 0))) & keep)
    ambiguous = ind(amb)
    return Labels(sup_pos, sup_neg, dem_pos, dem_neg, supply, demand, ambiguous)


# ----------------------------------------------------------------------------
# Eq. (14): expenditure-weighted shock SHARES
# ----------------------------------------------------------------------------
def shock_shares(labels: Labels, weights: pd.DataFrame) -> pd.DataFrame:
    """γ_{s,t} = Σ_i 1_{i∈s,t} ω_{i,t}  for s ∈ {sup+, sup-, dem+, dem-} (Eq. 14).

    `weights` are contemporaneous expenditure shares ω_{i,t}. The function
    renormalises defensively over the categories that actually carry a label
    that month, so each share is a monthly fraction of PCE in [0, 1].

    Returns a DataFrame with columns
        ["sup_pos", "sup_neg", "dem_pos", "dem_neg", "supply", "demand",
         "ambiguous"].
    """
    index = labels.sup_pos.index
    defined = labels.sup_pos.notna().to_numpy()     # any label panel shares the mask
    w = np.where(defined, weights.reindex_like(labels.sup_pos).to_numpy(), np.nan)
    row = np.nansum(w, axis=1)
    row[row == 0] = np.nan
    wn = w / row[:, None]

    def share(panel):
        return pd.Series(np.nansum(wn * np.nan_to_num(panel.to_numpy()), axis=1), index=index)

    out = pd.DataFrame({
        "sup_pos": share(labels.sup_pos),
        "sup_neg": share(labels.sup_neg),
        "dem_pos": share(labels.dem_pos),
        "dem_neg": share(labels.dem_neg),
        "supply": share(labels.supply),
        "demand": share(labels.demand),
        "ambiguous": share(labels.ambiguous),
    })
    # months with no labelled category -> undefined
    out[~defined.any(axis=1)] = np.nan
    return out


# ----------------------------------------------------------------------------
# Eq. (15): supply- / demand-driven CONTRIBUTIONS to monthly inflation
# ----------------------------------------------------------------------------
def contributions(
    inflation: pd.DataFrame,
    weights: pd.DataFrame,
    labels: Labels,
) -> pd.DataFrame:
    """Supply- and demand-driven contributions to monthly PCE inflation (Eq. 15).

        π^sup_t = Σ_i 1_{sup,i,t} ω_{i,t-1} π_{i,t}
        π^dem_t = Σ_i 1_{dem,i,t} ω_{i,t-1} π_{i,t}

    Parameters
    ----------
    inflation:
        Monthly category inflation π_{i,t} (MoM % change of the price index),
        [months x categories].
    weights:
        Contemporaneous nominal expenditure shares ω_{i,t}. The Laspeyres weight
        applied to month-t inflation is the PREVIOUS month's share, so this
        function uses `weights.shift(1)` internally (the paper's ω_{i,t-1}).
    labels:
        From `classify_labels`.

    Returns
    -------
    DataFrame with columns ["supply", "demand", "ambiguous", "total"], each a
    monthly contribution in the same units as `inflation` (percentage points).
    `total` = Σ_i ω_{i,t-1} π_{i,t} is the implied (Laspeyres) aggregate, equal
    to supply + demand + ambiguous.
    """
    infl = inflation.reindex_like(labels.supply)
    w_lag = weights.reindex_like(labels.supply).shift(1)

    contrib = (w_lag * infl).to_numpy()             # ω_{i,t-1} · π_{i,t}
    defined = labels.supply.notna().to_numpy() & np.isfinite(contrib)
    c = np.where(defined, contrib, 0.0)

    def lab_arr(panel):
        return np.where(defined, np.nan_to_num(panel.to_numpy()), 0.0)

    sup = (c * lab_arr(labels.supply)).sum(axis=1)
    dem = (c * lab_arr(labels.demand)).sum(axis=1)
    amb = (c * lab_arr(labels.ambiguous)).sum(axis=1)
    total = c.sum(axis=1)

    # Months with no defined category -> undefined (NaN), not a spurious 0.
    alive = defined.any(axis=1)
    out = pd.DataFrame({"supply": sup, "demand": dem, "ambiguous": amb,
                        "total": total}, index=labels.supply.index)
    out[~alive] = np.nan
    return out


# ----------------------------------------------------------------------------
# Section 3.1: year-over-year contributions (running 12-month product)
# ----------------------------------------------------------------------------
def yoy_contribution(monthly_contrib: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """12-month contribution = running product of the last 12 monthly ones.

        π^j_{t,t-12} = Π_{k=0..11} (1 + π^j_{t-k}) - 1          (×100, in pp)

    `monthly_contrib` is in percentage points (e.g. a column from
    `contributions`). Returns the same shape, in percentage points, NaN until 12
    months are available.
    """
    g = 1.0 + monthly_contrib / 100.0
    prod = g.rolling(12, min_periods=12).apply(np.prod, raw=True)
    return 100.0 * (prod - 1.0)


# ----------------------------------------------------------------------------
# Top-level convenience wrapper
# ----------------------------------------------------------------------------
@dataclass
class DecompResult:
    """Everything produced by `compute_decomp`, for inspection / plots."""

    contrib: pd.DataFrame          # monthly: supply / demand / ambiguous / total
    contrib_yoy: pd.DataFrame      # 12-month running-product version (pp, y/y)
    shares: pd.DataFrame           # γ_{s,t} (Eq. 14)
    resid_p: pd.DataFrame
    resid_q: pd.DataFrame
    labels: Labels
    config: DecompConfig = field(default_factory=DecompConfig)


def compute_decomp(
    log_price: pd.DataFrame,
    log_quantity: pd.DataFrame,
    inflation: pd.DataFrame,
    weights: pd.DataFrame,
    cfg: DecompConfig | None = None,
) -> DecompResult:
    """End-to-end supply/demand decomposition (Eqs. 8-15).

    Parameters
    ----------
    log_price, log_quantity:
        LOG price-index and LOG quantity-index panels for the regressions
        (Eqs. 12-13). For spec="diff" pass log first differences.
    inflation:
        Monthly category inflation π_{i,t} (MoM % change) for the contributions
        (Eq. 15). Kept separate from `log_price` so the contribution units stay
        interpretable regardless of the regression spec.
    weights:
        Contemporaneous nominal expenditure shares ω_{i,t} (BEA 2.4.5U). Used
        contemporaneously for shares (Eq. 14) and lagged one month for the
        Laspeyres contributions (Eq. 15).
    cfg:
        DecompConfig (defaults to the paper baseline: J=12, W=120, binary).

    Returns
    -------
    DecompResult
    """
    cfg = cfg or DecompConfig()
    resid_p, resid_q = rolling_var_residuals(log_price, log_quantity, cfg)
    labels = classify_labels(resid_p, resid_q, cfg)
    contrib = contributions(inflation, weights, labels)
    contrib_yoy = yoy_contribution(contrib[["supply", "demand", "ambiguous", "total"]])
    shares = shock_shares(labels, weights)
    return DecompResult(
        contrib=contrib,
        contrib_yoy=contrib_yoy,
        shares=shares,
        resid_p=resid_p,
        resid_q=resid_q,
        labels=labels,
        config=cfg,
    )
