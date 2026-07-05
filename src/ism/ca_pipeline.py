"""
ism.ca_pipeline
===============

Canada port of the ISM index, built on StatCan CPI by product (table
18-10-0004, monthly, NSA) with basket-vintage weights (18-10-0007). The
momentum engine is unchanged (`ism.engine.compute_ism`); this module only
builds the (inflation_panel, weights) pair, using the pinned leaf set in
config/ca_cpi_categories.csv and the conventions in config/sources_canada.yaml:

  geography            : Canada (geo member 2 in 18-10-0004, 1 in 18-10-0007)
  category prices      : 119 leaf product classes, tree capped at depth 4
                         (the analogue of the BLS item-strata / ONS class cut)
  category weights     : basket weights at link-month prices, distribution to
                         Canada, one vintage per basket year -> monthly ffill
  headline             : All-items CPI (member 2, v41690973)

History: major components from 1949, classic classes from 1978, detailed
leaves mostly from 1995 (we pull from 1976). With the paper's W=120 baseline
the Canadian ISM begins ~1986 on the early cross-section and thickens as
leaves are born (late-born categories are absent until they have a full
window, as on every other backbone).

Weight-vintage convention: StatCan links basket year Y into the CPI in the
spring of Y+1 (annual baskets since 2021; multi-year gaps before). We apply
vintage-Y weights from JUNE of Y+1 and carry them forward until the next
vintage — a documented simplification (link months varied historically);
weights are renormalised monthly over available leaves, so timing slack only
second-orders the index.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .statcan import (StatCanClient, ca_cpi_price_panel, ca_cpi_weights,
                      _pivot_quarterly)
from .transforms import monthly_inflation, yoy_inflation


def monthly_weights_from_vintages(vintages: pd.DataFrame,
                                  month_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Vintage weights [basket year x key] -> monthly panel (ffill from Jun Y+1)."""
    w = vintages.copy()
    w.index = pd.to_datetime([f"{int(y) + 1}-06-01" for y in w.index])
    w = w.sort_index()
    return w.reindex(month_index.union(w.index)).sort_index().ffill().reindex(month_index)


def build_ca_cpi_panel(client: Optional[StatCanClient] = None,
                       fill_interior_gaps: bool = True, force: bool = False):
    """Build (inflation_panel, weights, labels) for Canada from StatCan CPI.

    inflation = 100*dln(CPI leaf index); weights = basket-vintage percent
    weights, monthly-ffilled, masked to where the price is defined and
    renormalised. Same shapes as the US/UK/EU/JP panels -> `compute_ism`.
    """
    client = client or StatCanClient()
    price, labels = ca_cpi_price_panel(client, force=force)
    price = price.dropna(how="all").asfreq("MS")
    if fill_interior_gaps:  # same guard as the US CPI / UK backbones
        price = price.interpolate(method="time", limit_area="inside")

    vint = ca_cpi_weights(client, list(price.columns), force=force)
    wm = monthly_weights_from_vintages(vint, price.index)

    cols = [c for c in price.columns if c in wm.columns]
    price, wm = price[cols], wm[cols]

    infl = monthly_inflation(price)
    weights = wm.where(price.notna())
    weights = weights.div(weights.sum(axis=1).replace(0, np.nan), axis=0)

    common = infl.index.intersection(weights.index)
    print(f"[ca] CPI leaves selected: {len(cols)} (depth <= 4 cut)")
    return infl.loc[common], weights.loc[common], {c: labels[c] for c in cols}


def headline_ca_cpi_yoy(client: Optional[StatCanClient] = None,
                        force: bool = False) -> pd.Series:
    """Y/y % change of All-items CPI (member 2 of 18-10-0004, Canada)."""
    client = client or StatCanClient()
    raw = client.cpi(force=force)
    allitems = _pivot_quarterly(raw[raw["COORDINATE"] == "2.2"], "2.")
    s = allitems.iloc[:, 0].dropna().asfreq("MS")
    return yoy_inflation(s).rename("ca_cpi_yoy")
