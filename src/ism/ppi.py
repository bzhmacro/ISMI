"""
ism.ppi
=======

**The producer-price inputs to the PCE deflator**, for the CPI-to-PCE bridge.

Why PPI belongs on that page
----------------------------
About a fifth of PCE is priced from something other than the CPI, and the
single largest piece of it -- medical services, 17.6% of PCE against 6.1% of
the CPI -- is priced from the **producer** price index, because PCE counts what
insurers actually pay rather than what a household is billed.  A bridge built on
the CPI alone is therefore blind in exactly the place where the two gauges
diverge most, which is why the fitted CPI pass-through for medical services is
about 0.31 rather than 1.

Adding the PPI series BEA actually uses is not a refinement; it is most of the
remaining information.  Measured pseudo-out-of-sample on the group-level
nowcast, one month at a time, fitting only on data available before the month
being predicted:

    group                RMSE, CPI only    RMSE, CPI + PPI    improvement
    medical_services            0.166             0.071            57%
    health_insurance            0.414             0.253            39%
    public_transport            1.650             1.307            21%
    financial_services      (no CPI counterpart)  0.519         PPI is the only input

And the timing is the reason this is worth having at all: the PPI for a month is
published within a day or two of the CPI for the same month, both roughly two
weeks before the PCE.  So on CPI day the inputs to these groups are already
known, and the bridge can use them.

What is pinned, and why
-----------------------
``config/ppi_bridge_series.csv`` names one row per (group, PPI series), with the
flat file that holds it.  The file has to be named because the PPI-by-industry
database splits across about eighty files with no rule mapping a series id to
one of them -- so the alternative to pinning would be downloading the whole
database to find four series.

Seasonal adjustment
-------------------
The PPI-by-industry flat files carry **only unadjusted** series.  Regressing a
seasonally adjusted PCE change on an unadjusted PPI change would feed the PPI's
seasonal into the fit as noise, so the series are deseasonalised here with the
same month-effect estimator the trimmed-mean model uses
(:func:`ism.trim_engine.deseasonalise`), re-centred so the annual average is
untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .datasources import REPO_ROOT, BlsFlatFileClient
from .transforms import monthly_inflation
from .trim_engine import deseasonalise

BRIDGE_CSV = REPO_ROOT / "config" / "ppi_bridge_series.csv"


def load_bridge_series(path: Optional[Path] = None) -> pd.DataFrame:
    """Load ``config/ppi_bridge_series.csv``.

    Columns: ``group`` (a concordance group), ``series_id``, ``label``,
    ``file`` (the flat file holding it) and ``note`` (why BEA prices that
    spending this way -- shown on the website).
    """
    path = path or BRIDGE_CSV
    return pd.read_csv(path)


def fetch_ppi_levels(
    series: Optional[pd.DataFrame] = None,
    bls: Optional[BlsFlatFileClient] = None,
    force: bool = False,
) -> pd.DataFrame:
    """Monthly PPI index levels, one column per ``label``, NSA as published."""
    series = series if series is not None else load_bridge_series()
    bls = bls or BlsFlatFileClient(database="pc")
    got = bls.fetch_many(series["series_id"].tolist(), force=force,
                         files=sorted(set(series["file"])))
    cols = {}
    for row in series.itertuples():
        s = got.get(row.series_id)
        if s is not None and len(s):
            cols[row.label] = s
    if not cols:
        return pd.DataFrame()
    out = pd.DataFrame(cols).sort_index()
    out.index = pd.to_datetime(out.index).to_period("M").to_timestamp()
    return out[~out.index.duplicated(keep="last")].asfreq("MS")


def ppi_inflation(
    levels: Optional[pd.DataFrame] = None,
    sa: str = "dummy",
    sa_window: int = 120,
    **kwargs,
) -> pd.DataFrame:
    """Seasonally adjusted month-over-month PPI inflation (%, ``100*dln P``).

    ``sa="dummy"`` estimates one set of month effects per series over the whole
    sample; ``"rolling"`` re-estimates them from a trailing window and so uses
    no future data.  ``"none"`` passes the unadjusted change through, which is
    wrong for this purpose and offered only for inspection.
    """
    levels = levels if levels is not None else fetch_ppi_levels(**kwargs)
    if levels.empty:
        return levels
    return deseasonalise(monthly_inflation(levels), method=sa, window=sa_window)


def group_regressors(
    ppi_infl: pd.DataFrame,
    series: Optional[pd.DataFrame] = None,
) -> dict[str, list[str]]:
    """``{concordance group: [PPI column labels]}`` for the bridge."""
    series = series if series is not None else load_bridge_series()
    out: dict[str, list[str]] = {}
    for row in series.itertuples():
        if row.label in ppi_infl.columns:
            out.setdefault(row.group, []).append(row.label)
    return out
