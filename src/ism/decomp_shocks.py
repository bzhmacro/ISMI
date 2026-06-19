"""
ism.decomp_shocks
=================

External shock series and macro controls for Section 4 of Shapiro (2022-18)
("Proof of concept"): how externally identified monetary-policy and oil-supply
shocks move the supply- and demand-driven contributions to inflation (Eq. 21).

Shocks
------
* HFI monetary-policy shock (Gürkaynak, Sack & Swanson 2005): the high-frequency
  surprise to the *slope* of the yield curve around FOMC announcements (the
  10-year on-the-run Treasury yield surprise minus the fed-funds surprise),
  1990-2016. Provide as data/raw/external/gss_shocks.csv (date + a column
  containing "slope"; alternatively target/path/slope factors, in which case the
  slope column is used).
* Oil-supply shock (Baumeister & Hamilton 2019): provide as
  data/raw/external/bh_oil_supply.csv (date + a shock column). The paper takes
  the NEGATIVE of the positive supply shock, so `negative=True` (default) flips
  the sign to represent a *negative* oil-supply shock. The Känzig (2021)
  oil-supply news shock (already in ism.external_data) is the paper's robustness
  alternative.

Controls (Eq. 21 Y_t): current + 6 lags of the demand and supply contributions,
the unemployment rate, the excess bond premium (Gilchrist & Zakrajšek 2012) and
a credit spread. Fetched from FRED where possible; the EBP is read from a local
CSV (data/raw/external/ebp.csv) or the FRED series "EBP" if available.

All loaders degrade gracefully (return None / empty) when a file or series is
unavailable, so the rest of the pipeline still runs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, FredClient

EXT_DIR = REPO_ROOT / "data" / "raw" / "external"


def _read_dated_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    date_col = next((c for c in df.columns if "date" in c.lower() or "time" in c.lower()),
                    df.columns[0])
    idx = pd.to_datetime(df[date_col].astype(str), errors="coerce")
    df = df.loc[idx.notna()].copy()
    df.index = idx[idx.notna()].dt.to_period("M").dt.to_timestamp()
    return df.drop(columns=[date_col], errors="ignore")


def load_gss_monetary(local: Optional[Path] = None) -> Optional[pd.Series]:
    """Gürkaynak-Sack-Swanson (2005) HFI monetary slope surprise, monthly.

    Returns Series "gss_slope" (months with no FOMC surprise are 0). None if the
    file is absent.
    """
    df = _read_dated_csv(local or (EXT_DIR / "gss_shocks.csv"))
    if df is None:
        return None
    col = next((c for c in df.columns if "slope" in c.lower()), None) or df.columns[-1]
    s = pd.to_numeric(df[col], errors="coerce")
    s = s.groupby(s.index).sum()                    # aggregate intra-month surprises
    return s.rename("gss_slope")


def load_bh_oil_supply(local: Optional[Path] = None, negative: bool = True) -> Optional[pd.Series]:
    """Baumeister-Hamilton (2019) oil-supply shock, monthly.

    `negative=True` returns the negative of the (positive) supply shock, matching
    the paper's "negative oil supply shock". None if the file is absent.
    """
    df = _read_dated_csv(local or (EXT_DIR / "bh_oil_supply.csv"))
    if df is None:
        return None
    col = next((c for c in df.columns
                if any(k in c.lower() for k in ("supply", "oil", "shock"))), df.columns[-1])
    s = pd.to_numeric(df[col], errors="coerce")
    if negative:
        s = -s
    return s.rename("bh_oil_supply")


def load_ebp(fred: Optional[FredClient] = None, local: Optional[Path] = None) -> Optional[pd.Series]:
    """Excess bond premium (Gilchrist & Zakrajšek 2012), monthly.

    Tries data/raw/external/ebp.csv (a column containing "ebp"), then the FRED
    series. Returns Series "ebp" or None.
    """
    df = _read_dated_csv(local or (EXT_DIR / "ebp.csv"))
    if df is not None:
        col = next((c for c in df.columns if "ebp" in c.lower()), df.columns[-1])
        return pd.to_numeric(df[col], errors="coerce").rename("ebp")
    try:
        fred = fred or FredClient()
        s = fred.series("EBP")
        s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
        return s.rename("ebp")
    except Exception:
        return None


def macro_controls(fred: Optional[FredClient] = None) -> pd.DataFrame:
    """Control frame Y_t for Eq. (21): unemployment, a credit spread, and EBP.

    All from FRED (monthly), aligned on a month-start index. Missing pieces are
    simply omitted; the LP uses whatever is present.
    """
    fred = fred or FredClient()
    out = {}
    for name, sid in [("unrate", "UNRATE"), ("credit_spread", "BAA10YM")]:
        try:
            s = fred.series(sid)
            s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
            out[name] = s
        except Exception:
            pass
    ebp = load_ebp(fred)
    if ebp is not None:
        out["ebp"] = ebp
    return pd.DataFrame(out)


def recession_peak_dummy(index: pd.DatetimeIndex) -> pd.Series:
    """0/1 dummy marking NBER recession *peaks* (onset months), for Fig. 4.

    Peaks (business-cycle peaks / recession onsets) from the NBER chronology.
    """
    peaks = ["1969-12", "1973-11", "1980-01", "1981-07", "1990-07",
             "2001-03", "2007-12", "2020-02"]
    s = pd.Series(0.0, index=index, name="rec_peak")
    for p in peaks:
        ts = pd.Timestamp(p + "-01")
        if ts in s.index:
            s.loc[ts] = 1.0
    return s
