"""
ism.transforms
==============

Inflation transforms that convert a *price index* into the inflation series the
paper's model consumes. Kept separate from the engine so the exact definition of
"monthly inflation" is explicit and swappable.

The paper estimates the benchmark AR(1) on *monthly inflation* (Eq. 3). The
natural monthly inflation rate from a price-index level P_t is the log change:

    pi_t = 100 * ( ln(P_t) - ln(P_{t-1}) )          # monthly %, not annualised

We default to this. Two alternatives are provided because they are common and
may matter for exact matching:
    * `annualize=True`  -> multiply by 12 (monthly rate at annual rate)
    * simple pct change instead of log change (`method="pct"`)

For the forecast *target* and several controls the paper uses 12-month
(year-over-year) and 3-month inflation; helpers for those are here too.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def monthly_inflation(
    price_index: pd.Series | pd.DataFrame,
    method: str = "log",
    annualize: bool = False,
) -> pd.Series | pd.DataFrame:
    """Month-over-month inflation from a price index.

    Parameters
    ----------
    price_index : level of a price index (Series or wide DataFrame of categories).
    method : "log" (default) -> 100*dln(P); "pct" -> 100*pct_change(P).
    annualize : if True, multiply the monthly rate by 12.

    Returns the same type as the input (Series or DataFrame), first row NaN.
    """
    if method == "log":
        infl = 100.0 * (np.log(price_index) - np.log(price_index.shift(1)))
    elif method == "pct":
        infl = 100.0 * price_index.pct_change()
    else:
        raise ValueError("method must be 'log' or 'pct'")
    if annualize:
        infl = infl * 12.0
    return infl


def yoy_inflation(price_index: pd.Series, method: str = "log") -> pd.Series:
    """12-month inflation: 100*(ln P_t - ln P_{t-12}) (or pct over 12 months)."""
    if method == "log":
        return 100.0 * (np.log(price_index) - np.log(price_index.shift(12)))
    return 100.0 * (price_index / price_index.shift(12) - 1.0)


def threemonth_inflation(price_index: pd.Series, annualize: bool = True) -> pd.Series:
    """3-month inflation, annualised by default (paper's '3-month PCE inflation')."""
    g = np.log(price_index) - np.log(price_index.shift(3))
    rate = 100.0 * g
    return rate * (12.0 / 3.0) if annualize else rate


def yoy_growth(level: pd.Series) -> pd.Series:
    """12-month growth rate of a level series (e.g. real disposable income)."""
    return 100.0 * (level / level.shift(12) - 1.0)
