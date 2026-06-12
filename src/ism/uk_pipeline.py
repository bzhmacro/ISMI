"""
ism.uk_pipeline
===============

UK port of the ISM index, built on ONS CPI by COICOP (dataset MM23). The
momentum engine is unchanged (`ism.engine.compute_ism`); this module only
builds the (inflation_panel, weights) pair and the UK control block, using the
mappings in config/sources_uk.yaml:

  geography            : United Kingdom
  category prices      : MM23 "CPI INDEX xx.x.x" at COICOP class level (NSA)
  category weights     : MM23 "CPI WEIGHTS xx.x.x" (annual per mille) -> monthly ffill
  headline             : "CPI INDEX 00: ALL ITEMS" (D7BT)
  unemployment / V-U   : ONS MGSX, MGSC, AP2Y via the /generator endpoint
  yield spread         : FRED IRLTLT01GBM156N - IR3TIB01GBM156N (10y gilt - 3m)
  equity index         : FTSE All-Share local file, FALLBACK = Shiller S&P 500
                         (user-approved trade-off; correlation is high)
  recession dummy      : UK technical recessions (manual list; no NBER analogue)

History: class indices start 1988-01 (67 of 84 leaves), so with the paper's
W=120 baseline the UK ISM begins ~1998. Sub-class (xx.x.x.x) detail exists but
only from 2015-01 — selectable via max_depth=3 once it has enough history.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .engine import ISMConfig, compute_ism
from .ons import (OnsClient, monthly_weights_from_annual, uk_cpi_price_panel,
                  uk_cpi_weights, uk_headline_index)
from .transforms import monthly_inflation, threemonth_inflation, yoy_inflation

# ONS series page URIs for the /generator endpoint (see sources_uk.yaml)
ONS_URIS = {
    "mgsx": "/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms",
    "mgsc": "/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsc/lms",
    "ap2y": "/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/ap2y/unem",
}


# ---------------------------------------------------------------------------
# Category panel (the UK analogue of build_hicp_panel / build_cpi_category_panel)
# ---------------------------------------------------------------------------
def build_uk_cpi_panel(client: Optional[OnsClient] = None, max_depth: int = 2,
                       fill_interior_gaps: bool = True, force: bool = False):
    """Build (inflation_panel, weights, labels) for the UK from ONS MM23.

    inflation = 100*dln(CPI class index); weights = monthly-ffilled annual CPI
    item weights (per mille), masked to where the price is defined and
    renormalised. Same shapes as the US/EU panels, so it flows straight into
    `compute_ism`. `labels` maps COICOP code -> display label.
    """
    client = client or OnsClient()
    price, labels = uk_cpi_price_panel(client, max_depth=max_depth, force=force)
    # MM23's monthly rows reach back to 1947 (RPI era); CPI columns only start
    # 1988 — trim the leading all-NaN block before building the panel.
    price = price.dropna(how="all")
    price = price.asfreq("MS")
    if fill_interior_gaps:  # same guard as the US CPI backbone
        price = price.interpolate(method="time", limit_area="inside")

    annual = uk_cpi_weights(client, list(price.columns), force=force)
    wm = monthly_weights_from_annual(annual, price.index)

    cols = [c for c in price.columns if c in wm.columns]
    price, wm = price[cols], wm[cols]

    infl = monthly_inflation(price)
    weights = wm.where(price.notna())
    weights = weights.div(weights.sum(axis=1).replace(0, np.nan), axis=0)

    common = infl.index.intersection(weights.index)
    print(f"[uk] CPI leaves selected: {len(cols)} (COICOP depth <= {max_depth} dots)")
    return infl.loc[common], weights.loc[common], {c: labels[c] for c in cols}


def compute_uk_ism(client: Optional[OnsClient] = None, max_depth: int = 2,
                   cfg: ISMConfig | None = None):
    """End-to-end UK ISM: returns (ISMResult, inflation_panel, weights)."""
    infl, weights, _ = build_uk_cpi_panel(client, max_depth=max_depth)
    res = compute_ism(infl, weights, cfg or ISMConfig())
    return res, infl, weights


def headline_uk_cpi_yoy(client: Optional[OnsClient] = None, force: bool = False) -> pd.Series:
    """12-month UK CPI inflation (%) from the all-items index (D7BT)."""
    s = uk_headline_index(client or OnsClient(), force=force).asfreq("MS")
    s = s.interpolate(method="time", limit_area="inside")
    return yoy_inflation(s)


# ---------------------------------------------------------------------------
# UK recession dummy (manual; no NBER/CEPR-style committee for the UK)
# ---------------------------------------------------------------------------
# Technical recessions (2+ consecutive quarters of negative GDP growth, ONS
# quarterly GDP), expressed as month ranges (first month of peak quarter ->
# last month of trough quarter).
UK_RECESSIONS = [
    ("1973-07", "1974-03"),
    ("1975-04", "1975-09"),
    ("1980-01", "1981-03"),
    ("1990-07", "1991-09"),
    ("2008-04", "2009-06"),
    ("2020-01", "2020-06"),
    ("2023-07", "2023-12"),
]


def uk_recession_dummy(index: pd.DatetimeIndex) -> pd.Series:
    """0/1 monthly UK technical-recession dummy."""
    d = pd.Series(0.0, index=index, name="recession")
    for start, end in UK_RECESSIONS:
        d.loc[(index >= pd.Timestamp(start + "-01")) & (index <= pd.Timestamp(end + "-01"))] = 1.0
    return d


# ---------------------------------------------------------------------------
# UK control block (defensive: reports what it could/could not fetch)
# ---------------------------------------------------------------------------
def build_uk_controls(client: Optional[OnsClient] = None, fred=None,
                      month_index: Optional[pd.DatetimeIndex] = None) -> pd.DataFrame:
    """Assemble the UK control block per config/sources_uk.yaml.

    Each control is attempted independently; failures are reported, not fatal.
    Returns a monthly DataFrame (subset of the columns that succeeded):
        cpi_yoy, cpi_3m, unemployment, vu_ratio, spread_10y_3m, equity, recession
    Inflation expectations (BoE/Ipsos, quarterly) and real disposable income
    (quarterly) are added by the UK notebook from their own sources, as on the
    EU side.

    Equity: prefers a local FTSE file (data/raw/external/ftse.csv, date+close);
    otherwise FALLS BACK to the Shiller S&P 500 (user-approved trade-off) and
    says so.
    """
    client = client or OnsClient()
    out = {}

    # Headline CPI -> yoy & 3m (high confidence)
    try:
        cpi = uk_headline_index(client).asfreq("MS")
        out["cpi_yoy"] = yoy_inflation(cpi).rename("cpi_yoy")
        out["cpi_3m"] = threemonth_inflation(cpi).rename("cpi_3m")
    except Exception as e:
        print(f"[uk-controls] headline CPI failed: {e}")

    # Unemployment rate (high confidence)
    une = None
    try:
        une = client.series_csv(ONS_URIS["mgsx"], "mgsx")
        out["unemployment"] = une.rename("unemployment")
    except Exception as e:
        print(f"[uk-controls] unemployment (MGSX) failed: {e}")

    # V/U: vacancy stock / unemployment level (2001+; no UK Barnichon splice)
    try:
        vac = client.series_csv(ONS_URIS["ap2y"], "ap2y")
        lvl = client.series_csv(ONS_URIS["mgsc"], "mgsc")
        out["vu_ratio"] = (vac / lvl.reindex(vac.index)).rename("vu_ratio")
    except Exception as e:
        print(f"[uk-controls] V/U (AP2Y/MGSC) failed: {e}")

    # Yield spread: 10y gilt - 3m interbank (FRED/OECD, monthly)
    try:
        from .datasources import FredClient
        fred = fred or FredClient()
        lt = fred.series("IRLTLT01GBM156N")
        st = fred.series("IR3TIB01GBM156N")
        for s in (lt, st):
            s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
        out["spread_10y_3m"] = (lt - st.reindex(lt.index)).rename("spread_10y_3m")
    except Exception as e:
        print(f"[uk-controls] yield spread failed: {e}")

    # Equity: FTSE local file preferred, Shiller S&P 500 fallback (approved)
    try:
        from .external_data import EXT_DIR, load_shiller_sp500
        ftse_path = EXT_DIR / "ftse.csv"
        if ftse_path.exists():
            df = pd.read_csv(ftse_path)
            datecol = next((c for c in df.columns if "date" in c.lower()), df.columns[0])
            valcol = next((c for c in df.columns
                           if c.lower() in ("close", "price", "adj close", "value")),
                          df.columns[-1])
            idx = pd.to_datetime(df[datecol], errors="coerce").dt.to_period("M").dt.to_timestamp()
            s = pd.Series(pd.to_numeric(df[valcol], errors="coerce").to_numpy(),
                          index=idx, name="equity")
            out["equity"] = s[~s.index.duplicated(keep="last")].dropna().sort_index()
            print("[uk-controls] equity = FTSE (local file)")
        else:
            out["equity"] = load_shiller_sp500().rename("equity")
            print("[uk-controls] equity = S&P 500 FALLBACK (no FTSE file; "
                  "drop data/raw/external/ftse.csv to switch)")
    except Exception as e:
        print(f"[uk-controls] equity failed: {e}")

    frame = pd.concat(out.values(), axis=1) if out else pd.DataFrame()
    if month_index is not None and not frame.empty:
        frame = frame.reindex(month_index.union(frame.index)).sort_index().reindex(month_index)
    if not frame.empty:
        frame["recession"] = uk_recession_dummy(frame.index)
    return frame
