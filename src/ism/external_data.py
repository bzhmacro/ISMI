"""
ism.external_data
=================

Loaders for the long-history / non-API series the paper uses but that FRED does
not provide in full:

  * Shiller S&P 500 (monthly, 1871-present)  -> the "S&P 500 level" control.
    FRED's SP500 is licence-limited to ~10 years.
  * Barnichon (2010) composite Help-Wanted Index -> long-history vacancies,
    spliced to JOLTS job openings (JTSJOL, 2000m12+) to build the V/U ratio back
    to the 1950s. (The paper, fn 15, uses exactly this splice.)
  * Kanzig (2021) oil-supply news shock -> Section 5.2 validation (Fig 3b).
  * Romer & Romer (2024) attempted-disinflation dates -> Section 5.1 (Fig 3a),
    stated in the paper text and hard-coded here.

DESIGN / IMPORTANT
------------------
This project's sandbox cannot reach these hosts, and the exact on-disk format of
the Barnichon and Kanzig files can vary by vintage. So each loader:
  1. prefers a LOCAL cached file at a documented path (so you stay in control of
     the exact vintage), and
  2. falls back to a best-effort download from the documented URL, and
  3. raises a clear, actionable error if neither is available.

Expected local file formats are documented in each function's docstring and in
config/sources.yaml. If a download parser ever mismatches a new vintage, drop the
file at the documented local path in the documented 2-column shape and the rest
of the pipeline is unaffected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, fetch_url_bytes, fetch_url_csv

EXT_DIR = REPO_ROOT / "data" / "raw" / "external"


# ---------------------------------------------------------------------------
# Shiller S&P 500 (monthly level)
# ---------------------------------------------------------------------------
SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"


def load_shiller_sp500(local: Optional[Path] = None, force: bool = False) -> pd.Series:
    """Monthly S&P 500 composite price level from Robert Shiller's ie_data.xls.

    Local cache: data/raw/external/ie_data.xls (downloaded if missing).

    The "Data" sheet stores the month as a fractional year where the two decimals
    are the month (1871.01 = Jan 1871, 1871.10 = Oct 1871, 1871.12 = Dec 1871).
    We locate the header row containing "Date" and read the comprehensive S&P
    price column "P". Returns a month-start indexed float Series named "sp500".
    """
    path = local or (EXT_DIR / "ie_data.xls")
    if not path.exists() or force:
        path = fetch_url_bytes(SHILLER_URL, "ie_data.xls", force=force)

    raw = pd.read_excel(path, sheet_name="Data", header=None)
    # Find the header row (the row whose first cells include "Date" and "P").
    hdr = None
    for i in range(min(15, len(raw))):
        rowvals = [str(x).strip() for x in raw.iloc[i].tolist()]
        if "Date" in rowvals and "P" in rowvals:
            hdr = i
            break
    if hdr is None:
        raise ValueError("Could not locate the Shiller 'Data' header row (Date / P).")

    df = pd.read_excel(path, sheet_name="Data", header=hdr)
    df = df[["Date", "P"]].copy()
    df = df[pd.to_numeric(df["Date"], errors="coerce").notna()]
    fy = df["Date"].astype(float)
    year = np.floor(fy).astype(int)
    # round to avoid float artefacts: .01->1 ... .12->12
    month = (np.round((fy - year) * 100)).astype(int).clip(1, 12)
    idx = pd.to_datetime(dict(year=year, month=month, day=1))
    s = pd.Series(pd.to_numeric(df["P"], errors="coerce").to_numpy(), index=idx, name="sp500")
    return s[~s.index.duplicated(keep="last")].sort_index()


# ---------------------------------------------------------------------------
# Barnichon vacancies -> V/U ratio (spliced to JOLTS)
# ---------------------------------------------------------------------------
BARNICHON_URL = "https://docs.google.com/uc?export=download&id=barnichon_hwi"  # placeholder; see docstring


def load_barnichon_hwi(local: Optional[Path] = None) -> pd.Series:
    """Barnichon (2010) composite Help-Wanted Index, monthly.

    Local file (preferred): data/raw/external/barnichon_hwi.csv with two columns
    -- a date column (YYYY-MM, YYYYMM, or YYYYMmm) and the index value. Source:
    Regis Barnichon's data page (https://sites.google.com/site/regisbarnichon/data,
    file "Composite HWI"). We keep this as a user-supplied file because the hosted
    format changes between vintages.

    Returns a month-start indexed float Series named "hwi".
    """
    path = local or (EXT_DIR / "barnichon_hwi.csv")
    if not path.exists():
        raise FileNotFoundError(
            f"Barnichon HWI not found at {path}. Download the 'Composite HWI' file "
            "from https://sites.google.com/site/regisbarnichon/data and save it "
            "there as two columns (date, index)."
        )
    df = pd.read_csv(path)
    # be liberal about column names
    cols = {c.lower(): c for c in df.columns}
    datecol = next((cols[c] for c in cols if "date" in c or c in ("month", "time", "obs")), df.columns[0])
    valcol = next((c for c in df.columns if c != datecol), df.columns[-1])
    d = df[datecol].astype(str).str.strip().str.replace("M", "-", regex=False).str.replace("m", "-", regex=False)
    # handle YYYYMM (no separator)
    d = d.where(d.str.contains("-"), d.str[:4] + "-" + d.str[4:6])
    idx = pd.to_datetime(d + "-01", errors="coerce")
    s = pd.Series(pd.to_numeric(df[valcol], errors="coerce").to_numpy(), index=idx, name="hwi")
    return s.dropna().sort_index()


def build_vu_ratio(
    jolts_openings: pd.Series,
    unemployment_level: pd.Series,
    barnichon: Optional[pd.Series] = None,
) -> pd.Series:
    """Vacancy/unemployment ratio, splicing Barnichon HWI (pre-2000) to JOLTS.

    Splice: scale the Barnichon index to JOLTS units over their overlap (so the
    level is continuous), prefer JOLTS where available, then divide by the
    unemployment level. If `barnichon` is None, falls back to JOLTS-only (the
    ratio then starts in 2000).

    All inputs monthly, month-start indexed. Returns Series "vu_ratio".
    """
    jolts = jolts_openings.copy()
    if barnichon is not None and len(barnichon) > 0:
        overlap = jolts.index.intersection(barnichon.index)
        if len(overlap) >= 6:
            scale = (jolts.reindex(overlap) / barnichon.reindex(overlap)).median()
            hist = barnichon * scale
            vac = jolts.combine_first(hist)  # JOLTS wins on the overlap
        else:
            vac = jolts
    else:
        vac = jolts
    vu = (vac / unemployment_level).rename("vu_ratio")
    return vu.dropna()


# ---------------------------------------------------------------------------
# Kanzig (2021) oil supply news shock
# ---------------------------------------------------------------------------
def load_kanzig_oil_shock(local: Optional[Path] = None) -> pd.Series:
    """Kanzig (2021) oil-supply news shock, monthly.

    Local file (preferred): data/raw/external/kanzig_oilshock.csv with a date
    column and the shock series (the OPEC-announcement high-frequency surprise).
    Source: Diego Kanzig's replication files (https://www.diegokaenzig.com/research,
    "The macroeconomic effects of oil supply news"; series often named
    'OilSupplyNewsShock' or 'shock'). Returns Series "oil_news_shock".
    """
    path = local or (EXT_DIR / "kanzig_oilshock.csv")
    if not path.exists():
        raise FileNotFoundError(
            f"Kanzig oil-supply news shock not found at {path}. Download the shock "
            "series from https://www.diegokaenzig.com/research and save it there as "
            "two columns (date, shock)."
        )
    df = pd.read_csv(path)
    datecol = next((c for c in df.columns if "date" in c.lower() or "time" in c.lower()), df.columns[0])
    valcol = next((c for c in df.columns if c != datecol and
                   ("shock" in c.lower() or "news" in c.lower())), None) or \
             next((c for c in df.columns if c != datecol), df.columns[-1])
    d = df[datecol].astype(str).str.strip().str.replace("M", "-", regex=False)
    d = d.where(d.str.contains("-"), d.str[:4] + "-" + d.str[4:6])
    idx = pd.to_datetime(d + "-01" if not d.str.count("-").gt(1).any() else d, errors="coerce")
    s = pd.Series(pd.to_numeric(df[valcol], errors="coerce").to_numpy(), index=idx, name="oil_news_shock")
    return s.dropna().sort_index()


# ---------------------------------------------------------------------------
# Romer & Romer (2024) attempted-disinflation dates (from the paper text)
# ---------------------------------------------------------------------------
# Section 5.1: five episodes since 1969 plus a Sept-2022 episode the authors add.
ROMER_ROMER = {
    "low_commitment": ["1974-04", "1978-08"],
    # baseline shock set = medium-to-high commitment episodes:
    "medium_high": ["1979-10", "1981-05", "1988-12", "2022-09"],
}


def romer_romer_dummy(index: pd.DatetimeIndex, which: str = "medium_high") -> pd.Series:
    """A 0/1 monthly impulse series with 1 on the attempted-disinflation dates.

    `which` in {"medium_high" (baseline), "low_commitment", "all"}.
    """
    dates = ROMER_ROMER["medium_high"] + ROMER_ROMER["low_commitment"] if which == "all" \
        else ROMER_ROMER[which]
    stamps = {pd.Timestamp(d + "-01") for d in dates}
    return pd.Series([1.0 if t in stamps else 0.0 for t in index], index=index, name="rr_shock")


# ---------------------------------------------------------------------------
# STOXX Europe 600 (euro-area equity control) -- VALIDATED choice for the EU port
# ---------------------------------------------------------------------------
def load_stoxx_europe_600(local: Optional[Path] = None) -> pd.Series:
    """Monthly STOXX Europe 600 price level (the EU analogue of the S&P 500 control).

    Local file (preferred): data/raw/external/stoxx600.csv with a date column and
    a price/close column. Eurostat has no equity index, so this is user-supplied
    from a public source (e.g. STOXX, Stooq ticker ^STOXX, or Yahoo ^STOXX).
    Returns a month-start indexed float Series named "stoxx600" (month-end close
    resampled to month start).
    """
    path = local or (EXT_DIR / "stoxx600.csv")
    if not path.exists():
        raise FileNotFoundError(
            f"STOXX Europe 600 not found at {path}. Download monthly close prices "
            "(e.g. Stooq ^STOXX) and save as two columns (date, close)."
        )
    df = pd.read_csv(path)
    datecol = next((c for c in df.columns if "date" in c.lower()), df.columns[0])
    valcol = next((c for c in df.columns if c.lower() in ("close", "price", "adj close", "value")),
                  df.columns[-1])
    idx = pd.to_datetime(df[datecol], errors="coerce").dt.to_period("M").dt.to_timestamp()
    s = pd.Series(pd.to_numeric(df[valcol], errors="coerce").to_numpy(), index=idx, name="stoxx600")
    return s[~s.index.duplicated(keep="last")].dropna().sort_index()
