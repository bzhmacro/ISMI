"""
ism.eu_pipeline
===============

Euro-area port of the ISM index, built on Eurostat HICP-by-COICOP. The momentum
engine is unchanged (`ism.engine.compute_ism`); this module only builds the
(inflation_panel, weights) pair and the EU control block, using the VALIDATED
mappings in config/sources_europe.yaml:

  geography            : euro area (EA20; EA19/EA for longer history)
  category prices      : prc_hicp_midx (HICP index) by COICOP
  category weights     : prc_hicp_inw (annual HICP weights) -> monthly ffill
  inflation expectations: ei_bsco_m (EC Consumer Survey price-trends balance)
  equity index         : STOXX Europe 600 (external file)
  V/U ratio            : jvs vacancy rate (quarterly) / une_rt_m, interpolated
  yield spread         : irt_lt_mcby_m - irt_st_m
  recession dummy      : CEPR Euro Area Business Cycle Dating Committee dates

COICOP codes encode the hierarchy (CP00 > CP01 > CP011 > CP0111). We select the
"leaf" codes (the analogue of the BEA level-5 cut), optionally capped at a digit
depth. Exact Eurostat dimension codes for a few controls (esp. the ei_bsco_m
indicator and the jvs filters) can vary by vintage; the control builder is
defensive and reports what it could and could not fetch.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd

from .engine import ISMConfig, compute_ism
from .eurostat import (EurostatClient, hicp_price_panel, hicp_weights,
                       monthly_weights_from_annual)
from .transforms import monthly_inflation, yoy_inflation, threemonth_inflation


# ---------------------------------------------------------------------------
# COICOP leaf selection (analogue of the BEA level cut)
# ---------------------------------------------------------------------------
def select_coicop_leaves(price_panel: pd.DataFrame, max_digits: Optional[int] = 4,
                         exclude=("CP00",)) -> list[str]:
    """Return the leaf COICOP codes of the available tree.

    Keeps codes matching CP<digits> (drops analytic aggregates like GD, SERV,
    NRG, FOOD, TOT_X_NRG_FOOD and the all-items CP00). A code is a leaf if no
    longer code shares it as a prefix. If `max_digits` is set, the tree is first
    capped at that COICOP depth (e.g. 4 = COICOP class), so deeper sub-indices
    roll up to their class.
    """
    cols = [c for c in price_panel.columns if re.fullmatch(r"CP\d+", str(c)) and c not in exclude]
    if max_digits is not None:
        cols = [c for c in cols if (len(c) - 2) <= max_digits]
    colset = set(cols)
    leaves = [c for c in cols if not any(o != c and o.startswith(c) for o in colset)]
    return sorted(leaves)


def build_hicp_panel(client: EurostatClient, geo: str = "EA20", unit: str = "I15",
                     max_digits: Optional[int] = 4, force: bool = False):
    """Build (inflation_panel, weights) for the euro area from HICP.

    inflation = 100*dln(HICP index); weights = monthly-ffilled annual HICP item
    weights, renormalised over the selected leaves. Same shapes as the US panel,
    so it flows straight into `compute_ism`.
    """
    price = hicp_price_panel(client, geo=geo, unit=unit, force=force)
    leaves = select_coicop_leaves(price, max_digits=max_digits)
    price = price[leaves].dropna(how="all", axis=1)

    annual = hicp_weights(client, geo=geo, force=force)
    wm = monthly_weights_from_annual(annual, price.index)

    cols = [c for c in price.columns if c in wm.columns]
    price, wm = price[cols], wm[cols]
    infl = monthly_inflation(price)
    weights = wm.div(wm.sum(axis=1).replace(0, np.nan), axis=0)
    common = infl.index.intersection(weights.index)
    print(f"[eu] HICP leaves selected: {len(cols)} (geo={geo}, COICOP<= {max_digits} digits)")
    return infl.loc[common], weights.loc[common]


def compute_eu_ism(client: EurostatClient, geo: str = "EA20", max_digits: Optional[int] = 4,
                   cfg: ISMConfig | None = None):
    """End-to-end euro-area ISM: returns (ISMResult, inflation_panel, weights)."""
    infl, weights = build_hicp_panel(client, geo=geo, max_digits=max_digits)
    res = compute_ism(infl, weights, cfg or ISMConfig())
    return res, infl, weights


# ---------------------------------------------------------------------------
# CEPR euro-area recession dummy (manual)
# ---------------------------------------------------------------------------
# CEPR Euro Area Business Cycle Dating Committee peak->trough ranges (monthly approx).
CEPR_EA_RECESSIONS = [
    ("1974-09", "1975-03"),
    ("1980-01", "1982-03"),
    ("1992-01", "1993-09"),
    ("2008-01", "2009-06"),
    ("2011-07", "2013-03"),
    ("2019-10", "2020-06"),
]


def cepr_recession_dummy(index: pd.DatetimeIndex) -> pd.Series:
    """0/1 monthly euro-area recession dummy from the CEPR EABCDC dates."""
    d = pd.Series(0.0, index=index, name="recession")
    for start, end in CEPR_EA_RECESSIONS:
        d.loc[(index >= pd.Timestamp(start + "-01")) & (index <= pd.Timestamp(end + "-01"))] = 1.0
    return d


# ---------------------------------------------------------------------------
# EU control block (defensive: reports what it could/could not fetch)
# ---------------------------------------------------------------------------
def build_eu_controls(client: EurostatClient, geo: str = "EA20",
                      month_index: Optional[pd.DatetimeIndex] = None) -> pd.DataFrame:
    """Assemble the euro-area control block per the validated mapping.

    Robust to vintage differences in Eurostat dimension codes: each control is
    attempted independently and failures are reported, not fatal. Returns a
    monthly DataFrame (subset of the columns below that succeeded):
        hicp_yoy, hicp_3m, infl_exp_1y, vu_ratio, spread_10y_3m, recession
    Oil (Brent, global), equity (STOXX Europe 600) and real disposable income are
    added by the EU notebook from their own sources.
    """
    out = {}

    # Headline HICP -> yoy & 3m (high confidence)
    try:
        cp00 = hicp_price_panel(client, geo=geo)["CP00"]
        out["hicp_yoy"] = yoy_inflation(cp00).rename("hicp_yoy")
        out["hicp_3m"] = threemonth_inflation(cp00).rename("hicp_3m")
    except Exception as e:
        print(f"[eu-controls] headline HICP failed: {e}")

    # Unemployment rate (high confidence)
    try:
        une = client.dataset("une_rt_m", {"freq": "M", "s_adj": "SA", "age": "TOTAL",
                                          "sex": "T", "unit": "PC_ACT", "geo": geo})
        une = une.pivot_table(index="date", values="value", aggfunc="first").iloc[:, 0]
    except Exception as e:
        print(f"[eu-controls] unemployment failed: {e}"); une = None

    # V/U: quarterly job vacancy rate / unemployment rate, interpolated to monthly
    try:
        jvs = client.dataset("jvs_q_nace2", {"s_adj": "SA", "nace_r2": "B-S", "geo": geo})
        jvr = jvs.pivot_table(index="date", values="value", aggfunc="first").iloc[:, 0]
        jvr_m = jvr.resample("MS").interpolate()  # quarterly -> monthly
        if une is not None:
            vu = (jvr_m / une.reindex(jvr_m.index)).rename("vu_ratio")
            out["vu_ratio"] = vu
    except Exception as e:
        print(f"[eu-controls] V/U failed (jvs dimensions vary by vintage): {e}")

    # Inflation expectations: EC Consumer Survey price-trends-next-12m balance
    try:
        # indic code for "price trends over next 12 months" varies; try common ones.
        for indic in ("BS-PT12-BAL", "BS-IPT-BAL", "BS-PT-BAL"):
            try:
                bs = client.dataset("ei_bsco_m", {"s_adj": "SA", "indic": indic, "geo": geo})
                out["infl_exp_1y"] = bs.pivot_table(index="date", values="value", aggfunc="first").iloc[:, 0].rename("infl_exp_1y")
                break
            except Exception:
                continue
        if "infl_exp_1y" not in out:
            print("[eu-controls] inflation expectations: confirm ei_bsco_m 'indic' code on first run")
    except Exception as e:
        print(f"[eu-controls] inflation expectations failed: {e}")

    # Yield spread: 10y benchmark gov bond yield - 3m money market rate
    try:
        lt = client.dataset("irt_lt_mcby_m", {"geo": geo}).pivot_table(index="date", values="value", aggfunc="first").iloc[:, 0]
        st = client.dataset("irt_st_m", {"geo": geo}).pivot_table(index="date", values="value", aggfunc="first").iloc[:, 0]
        out["spread_10y_3m"] = (lt - st.reindex(lt.index)).rename("spread_10y_3m")
    except Exception as e:
        print(f"[eu-controls] yield spread failed: {e}")

    frame = pd.concat(out.values(), axis=1) if out else pd.DataFrame()
    if month_index is not None and not frame.empty:
        frame = frame.reindex(month_index.union(frame.index)).sort_index().reindex(month_index)
    if not frame.empty:
        frame["recession"] = cepr_recession_dummy(frame.index)
    return frame
