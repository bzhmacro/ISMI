"""
pkg.engine  (TEMPLATE)
======================

THE MATHS. Each function maps to one numbered equation in the paper; read this
module side-by-side with the methodology section. Nothing here knows about
providers, countries, or file formats -- it only ever sees a (panel, weights)
pair, which is the whole point (portability + scenario injection + a JS twin).

Worked example below: a momentum-style index (rolling AR(p) benchmark ->
consecutive-run momentum signals -> weighted shares -> net index). Replace the
bodies with YOUR equations but KEEP the contract and the parameter-not-constant
discipline.

    Eq. (3)  pi_{i,t} = mu_i + rho_i*pi_{i,t-1} + eps_{i,t}
             -> rolling_ar_residuals()     (per unit, W-month rolling window)
    Eq. (4)  M+_{i,t} = prod_{k=0..K-1} 1(eps_{i,t-k} > 0)
    Eq. (5)  M-_{i,t} = prod_{k=0..K-1} 1(eps_{i,t-k} < 0)
             -> momentum_signals()
    Eq. (6)  S+_t = sum_i w_{i,t}*M+_{i,t}
    Eq. (7)  S-_t = sum_i w_{i,t}*M-_{i,t}
             -> weighted_shares()
    Eq. (8)  Index_t = S+_t - S-_t
             -> compute()
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Config:
    """A particular specification. Paper baselines are the defaults; everything is
    a parameter so robustness checks and country ports reuse the same code."""
    window: int = 120        # W: rolling benchmark window (months)
    ar_order: int = 1        # p: AR order of the benchmark (Eq. 3)
    run_length: int = 3      # K: consecutive same-signed residuals (Eqs. 4-5)
    scheme: str = "extensive"  # weighting: "extensive" | "size" | "stickiness"


def rolling_ar_residuals(panel: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Eq. (3): per-unit one-step residual from a rolling AR(p) benchmark.

    Returns a residual panel aligned to `panel`. A unit with fewer than `window`
    observations contributes NaN until its window fills -- matching how the paper
    handles late-born units. Rank-deficient windows are solved min-norm via
    lstsq (the JS twin must match this).
    """
    p, W = cfg.ar_order, cfg.window
    resid = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
    for col in panel.columns:
        y_full = panel[col]
        for t in range(W, len(y_full)):
            win = y_full.iloc[t - W:t + 1]
            if win.isna().any():
                continue
            y = win.values
            # Design matrix: intercept + p lags.
            X = np.column_stack([np.ones(W - p + 1)] +
                                 [y[p - j - 1:len(y) - j - 1] for j in range(p)])
            target = y[p:]
            # Fit on the window (min-norm via lstsq handles rank-deficient X),
            # keep the most recent regression residual.
            beta, *_ = np.linalg.lstsq(X, target, rcond=None)
            resid.iloc[t, panel.columns.get_loc(col)] = target[-1] - X[-1] @ beta
    return resid


def momentum_signals(resid: pd.DataFrame, cfg: Config):
    """Eqs. (4)-(5): a unit has +momentum when its last K residuals are all > 0,
    -momentum when all < 0. Returns (m_pos, m_neg) 0/1 panels."""
    K = cfg.run_length
    pos = (resid > 0).astype(float)
    neg = (resid < 0).astype(float)
    m_pos = pos.rolling(K).apply(lambda x: float(np.all(x == 1)), raw=True)
    m_neg = neg.rolling(K).apply(lambda x: float(np.all(x == 1)), raw=True)
    # Where a residual is undefined the signal is undefined too.
    m_pos = m_pos.where(resid.notna())
    m_neg = m_neg.where(resid.notna())
    return m_pos, m_neg


def weighted_shares(m_pos, m_neg, weights: pd.DataFrame):
    """Eqs. (6)-(7): expenditure-weighted shares. Weights are renormalised each
    month over the units with a defined signal, so missing units don't distort."""
    defined = m_pos.notna()
    w = weights.where(defined)
    w = w.div(w.sum(axis=1), axis=0)        # renormalise per month
    s_pos = (w * m_pos).sum(axis=1)
    s_neg = (w * m_neg).sum(axis=1)
    return s_pos, s_neg


def compute(panel: pd.DataFrame, weights: pd.DataFrame, cfg: Config = Config()):
    """Tie the equations together. Eq. (8): Index = S+ - S-.

    THE public entry point. `panel` and `weights` are aligned (months x units).
    Returns a dict of pandas Series so the export script and tests can consume it
    uniformly. This is the function the JS twin reimplements.
    """
    resid = rolling_ar_residuals(panel, cfg)
    m_pos, m_neg = momentum_signals(resid, cfg)
    s_pos, s_neg = weighted_shares(m_pos, m_neg, weights)
    index = s_pos - s_neg
    return {"Index": index, "S_pos": s_pos, "S_neg": s_neg, "resid": resid}
