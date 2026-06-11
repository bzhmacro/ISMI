"""
ism.cpi_pipeline
================

A CPI backbone for the ISM index, parallel to :mod:`ism.pipeline` (which builds
the PCE backbone from BEA).  The engine (:mod:`ism.engine`) is dataset-agnostic:
it consumes an ``inflation_panel`` [months x categories] and ``weights`` of the
same shape.  This module produces those two objects from the **BLS Consumer
Price Index** instead of BEA PCE, so the *same* momentum machinery can be run on
either price gauge and compared.

What differs from the PCE backbone
----------------------------------
* **Prices.** BLS publishes a monthly price index per CPI item stratum
  (series ``CUUR0000<item>``, US city average, *not* seasonally adjusted -- the
  NSA series is the right input for month-over-month inflation, matching how the
  PCE pipeline treats the BEA price index).  ``config/cpi_categories.csv`` pins
  a non-overlapping partition of 70 item strata that tiles the whole index
  (their relative importances sum to 100%).

* **Weights.** Unlike PCE -- where BEA publishes a *monthly* nominal-dollar
  series per category (table 2.4.5U) -- the CPI has no monthly expenditure
  series.  BLS instead publishes annual **relative importances** (the share of
  the CPI basket each item represents).  We use the December-2023 relative
  importance (CPI-U, US city average) pinned in the config as a *static* weight
  vector, broadcast across all months.  The engine renormalises the weights each
  month over the categories that actually have a defined momentum signal, so the
  static vector behaves as expenditure shares for the diffusion index.  This is
  a documented simplification (the PCE weights drift month to month; the CPI RI
  is refreshed only annually).  To use year-varying RI, replace the single
  ``ri_weight`` column with one column per year and broadcast accordingly.

Selecting the category set
--------------------------
The 70 strata in ``config/cpi_categories.csv`` were obtained by walking the BLS
published relative-importance tree top-down and taking, on each branch, the
shallowest node that maps to a CPI item-stratum series (an ``SE`` code) -- a
greedy cut that yields a complete, non-overlapping expenditure-class partition.
This is the CPI analogue of the paper's "fourth level of disaggregation" of PCE.
Because the engine renormalises, the index is robust to adding/removing strata.

History note
------------
Most strata go back to the 1950s-60s; a few (owners' equivalent rent from 1983,
telephone/IT services from 1997-98) begin later.  The engine treats a category
as absent until it has a full rolling window, exactly as the PCE pipeline does
for late-born categories, so the CPI ISM simply has fewer categories early on.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import BlsClient, REPO_ROOT
from .transforms import monthly_inflation


CONFIG_CSV = REPO_ROOT / "config" / "cpi_categories.csv"

# All-items CPI-U (US city average, NSA): the headline gauge, analogue of PCEPI.
HEADLINE_SERIES = "CUUR0000SA0"


def load_cpi_categories(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the pinned CPI item-stratum partition (key, SeriesCode, group,
    ri_weight, label)."""
    path = path or CONFIG_CSV
    cats = pd.read_csv(path)
    cats["key"] = cats["key"].astype(str)
    cats["SeriesCode"] = cats["SeriesCode"].astype(str)
    return cats


def _series_dict_to_wide(series_by_id: dict[str, pd.Series], cats: pd.DataFrame) -> pd.DataFrame:
    """Stack the per-series monthly indexes into a [month x key] price panel."""
    cols = {}
    for _, row in cats.iterrows():
        s = series_by_id.get(row["SeriesCode"])
        if s is not None and len(s):
            s = s.copy()
            s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
            cols[row["key"]] = s
    wide = pd.DataFrame(cols).sort_index()
    return wide


def build_cpi_category_panel(
    bls: Optional[BlsClient] = None,
    start_year: int = 1957,
    end_year: Optional[int] = None,
    inflation_method: str = "log",
    cats: Optional[pd.DataFrame] = None,
    force: bool = False,
    fill_interior_gaps: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch BLS CPI item-stratum indexes and build ``(inflation_panel, weights)``.

    Mirrors :func:`ism.pipeline.build_category_panel` but for the CPI:

        * ``inflation_panel`` = month-over-month inflation of each CPI item
          stratum's price index (pi_{i,t}, Eq. 3 input).
        * ``weights`` = the static relative-importance vector from the config,
          broadcast across months (w_{i,t}, Eqs. 6-7 input).  The engine
          renormalises each row over available categories.

    ``fill_interior_gaps`` linearly bridges *interior* missing months in the
    price index before differencing.  BLS occasionally fails to publish a month
    (e.g. the Oct-2025 CPI release was not produced); a single hole otherwise
    breaks the month-over-month inflation chain and forces the momentum signal
    to zero for every subsequent month.  ``limit_area="inside"`` guarantees no
    leading/trailing values are ever fabricated -- only genuine interior holes
    between two published prints are bridged.

    Returns aligned DataFrames [months x categories].
    """
    bls = bls or BlsClient()
    cats = load_cpi_categories() if cats is None else cats
    end_year = end_year or dt.date.today().year

    series_by_id = bls.fetch_many(
        cats["SeriesCode"].tolist(), start_year, end_year, force=force
    )
    price = _series_dict_to_wide(series_by_id, cats)
    price = price.asfreq("MS")
    if fill_interior_gaps:
        price = price.interpolate(method="time", limit_area="inside")
    keys = list(price.columns)

    inflation_panel = monthly_inflation(price, method=inflation_method)

    # Static relative-importance weights, broadcast across every month, then
    # masked to where the price (hence inflation) is defined.
    ri = cats.set_index("key").loc[keys, "ri_weight"].astype(float)
    weights = pd.DataFrame(
        np.tile(ri.to_numpy(), (len(price.index), 1)),
        index=price.index,
        columns=keys,
    )
    weights = weights.where(price.notna())
    row_tot = weights.sum(axis=1)
    weights = weights.div(row_tot.replace(0, np.nan), axis=0)

    common = inflation_panel.index.intersection(weights.index)
    return inflation_panel.loc[common], weights.loc[common]


def headline_cpi_yoy(bls: Optional[BlsClient] = None, start_year: int = 1947,
                     end_year: Optional[int] = None, force: bool = False) -> pd.Series:
    """12-month CPI-U inflation (%) from the all-items NSA index -- the CPI
    overlay analogue of 12-month PCE inflation."""
    bls = bls or BlsClient()
    end_year = end_year or dt.date.today().year
    s = bls.series(HEADLINE_SERIES, start_year, end_year, force=force)
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
    s = s.asfreq("MS").interpolate(method="time", limit_area="inside")
    return 100.0 * (np.log(s) - np.log(s.shift(12)))
