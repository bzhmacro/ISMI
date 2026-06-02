"""
ism.controls
============

Assemble the control / predictor block used in Table 1, the local projections
(Eq. 9) and the LASSO (Table 2). Each control maps to a source in
config/sources.yaml. FRED provides most; the two long-history series the paper
uses that FRED lacks are loaded via ism.external_data:
  * V/U ratio  -> Barnichon (2010) HWI spliced to JOLTS over the unemployment level
  * S&P 500    -> Shiller ie_data.xls (FRED's SP500 is licence-limited to ~10y)

Columns (monthly, month-start index):
    pce_yoy, pce_3m, infl_exp_1y, vu_ratio, oil_wti, sp500, rdpi_yoy,
    spread_10y_ffr, nber_recession
"""

from __future__ import annotations

import pandas as pd

from .datasources import FredClient
from .transforms import yoy_inflation, threemonth_inflation, yoy_growth


def _ms(s: pd.Series) -> pd.Series:
    s = s.copy()
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
    return s


def build_controls(fred: FredClient | None = None) -> pd.DataFrame:
    """Fetch + transform all controls into one monthly frame.

    Uses ism.external_data for the V/U splice (Barnichon->JOLTS) and the Shiller
    S&P 500; both degrade gracefully to FRED-only if the external files are
    absent (V/U then starts in 2000; S&P uses the short FRED series).
    """
    fred = fred or FredClient()

    pcepi = _ms(fred.series("PCEPI"))
    pce_yoy = yoy_inflation(pcepi).rename("pce_yoy")
    pce_3m = threemonth_inflation(pcepi).rename("pce_3m")
    infl_exp = _ms(fred.series("MICH")).rename("infl_exp_1y").combine_first(
        pce_yoy.rename("infl_exp_1y"))                      # pre-1978 proxy (fn 14)
    oil = _ms(fred.series("WTISPLC")).rename("oil_wti")
    rdpi_yoy = yoy_growth(_ms(fred.series("DSPIC96"))).rename("rdpi_yoy")
    spread = (_ms(fred.series("GS10")) - _ms(fred.series("FEDFUNDS"))).rename("spread_10y_ffr")
    rec = _ms(fred.series("USREC")).rename("nber_recession")

    jolts, unemp = _ms(fred.series("JTSJOL")), _ms(fred.series("UNEMPLOY"))
    try:
        from .external_data import build_vu_ratio, load_barnichon_hwi, load_shiller_sp500
        try:
            barn = load_barnichon_hwi()
        except Exception as e:
            print(f"[controls] Barnichon HWI not found -> V/U from 2000 only: {e}")
            barn = None
        vu = build_vu_ratio(jolts, unemp, barn).rename("vu_ratio")
        try:
            sp500 = _ms(load_shiller_sp500()).rename("sp500")
        except Exception as e:
            print(f"[controls] Shiller S&P not available -> FRED SP500 (short): {e}")
            sp500 = _ms(fred.series("SP500")).rename("sp500")
    except Exception as e:
        print(f"[controls] external_data unavailable -> FRED-only fallbacks: {e}")
        vu = (jolts / unemp).rename("vu_ratio")
        try:
            sp500 = _ms(fred.series("SP500")).rename("sp500")
        except Exception:
            sp500 = pd.Series(dtype=float, name="sp500")

    return pd.concat([pce_yoy, pce_3m, infl_exp, vu, oil, sp500, rdpi_yoy, spread, rec], axis=1)
