"""
ism.official_trim
=================

The **published** limited-influence inflation measures, for overlay and
validation:

* Federal Reserve Bank of Cleveland -- median CPI and 16% trimmed-mean CPI,
  plus the current month's component table (which component held the median,
  and what was trimmed).
* Federal Reserve Bank of Dallas -- trimmed mean PCE (1-, 6- and 12-month), plus
  the current month's component detail showing exactly which categories fell
  inside the 24% / 31% cut.

Both banks publish flat files that need no key and no registration, which is
why this module talks to them directly rather than going through FRED:
the bank files carry the **whole history in one request**, the index levels as
well as the rates, and -- in the component tables -- the cross-section itself,
which is the thing you actually want when a print surprises.

Every download is cached with a provenance sidecar like the rest of the repo.

Files
-----
``usinflationdata.csv`` (Cleveland)
    One wide monthly file from 1947: CPI, core CPI, PCE, core PCE, PPI, and
    both Cleveland measures, each as SA index, m/m, y/y and annualised m/m.
    The "Revised" columns (Dec-82=100) are the current methodology and start in
    1983; the "Original" columns (Jan-67=100) are the pre-2005 vintage, kept for
    the earlier history.  We read the revised series and fall back to the
    original before 1983.
``mediancpi_component_table.csv`` (Cleveland)
    The latest month's 45 components, sorted by annualised change, with
    normalised relative importance and its cumulative sum -- i.e. the exact
    object our estimator builds internally.
``pcehist.xlsx`` / ``detail.xlsx`` (Dallas)
    Trimmed mean PCE history from 1977, and the current month's component
    detail with a colour key marking "Cut from bottom" / "Included" /
    "Cut from top" / "Trim point".
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import fetch_url_bytes

CLEVELAND_BASE = "https://www.clevelandfed.org/-/media/files/webcharts/mediancpi"
DALLAS_BASE = "https://www.dallasfed.org/-/media/documents/research/pce"

#: The "csv" path on clevelandfed.org actually serves the ZIP, so we ask for
#: the ZIP by name and read the CSV out of it -- one fewer surprise than a file
#: whose extension lies.
CLEVELAND_HISTORY_URL = f"{CLEVELAND_BASE}/usinflationdata.zip?sc_lang=en"
CLEVELAND_HISTORY_MEMBER = "usinflationdata.csv"
CLEVELAND_COMPONENTS_URL = f"{CLEVELAND_BASE}/mediancpi_component_table.csv?sc_lang=en"
DALLAS_HISTORY_URL = f"{DALLAS_BASE}/pcehist.xlsx"
DALLAS_DETAIL_URL = f"{DALLAS_BASE}/detail.xlsx"

#: Statistics Canada table 18-10-0256 ("measures of core inflation - Bank of
#: Canada definitions").  The whole-table ZIP is one request, no key, whole
#: history -- the same posture as the two Reserve Bank files above.
STATCAN_CORE_URL = "https://www150.statcan.gc.ca/n1/tbl/csv/18100256-eng.zip"
STATCAN_CORE_MEMBER = "18100256.csv"

#: Bank of Japan, "Indicators for Core CPI".  One workbook, one sheet, every
#: measure on every CPI base.
BOJ_CORE_URL = "https://www.boj.or.jp/en/research/research_data/cpi/cpirev.xlsx"
BOJ_CORE_SHEET = "chart"
BOJ_HEADER_ROW = 3          # English measure names
BOJ_BASE_ROW = 4            # "2020base", "2015base", ...
BOJ_FIRST_ROW = 5           # first month

#: Substrings that identify each StatCan series in the "Alternative measures"
#: dimension.  Matched as an AND of plain substrings, because the labels are
#: long sentences that StatCan rewords.
_STATCAN_MEASURES = {
    "trim_yoy": ("CPI-trim", "year-over-year"),
    "median_yoy": ("CPI-median", "year-over-year"),
    "trim_index": ("CPI-trim", "index"),
    "median_index": ("CPI-median", "index"),
}

#: Bank of Japan measure names as they appear in the workbook's English header.
_BOJ_COLUMNS = {
    "trim10_yoy": "Trimmed mean(y/y % chg.)",
    "median_yoy": "Weighted median(y/y % chg.)",
    "mode_yoy": "Mode(y/y % chg.)",
    "diffusion": "Diffusion index(% points)",
}

#: Column fragments identifying the series we lift out of the Cleveland file.
#: Matching on a fragment rather than the full string keeps the loader working
#: when they re-word a header, which they have done.
_CLEVELAND_COLUMNS = {
    "median_index": "Revised FRB Cleveland Median CPI SA, (Dec-82=100)",
    "median_mm": "Revised FRB Cleveland Median CPI SA, (Dec-82=100) % Change - Period to Period",
    "median_yoy": "Revised FRB Cleveland Median CPI SA, (Dec-82=100) % Change - Year to Year",
    "median_saar": "Revised FRB Cleveland Median CPI SAAR",
    "trim16_index": "Revised 16% trimmed mean SA, (Dec-82=100)",
    "trim16_mm": "Revised 16% trimmed mean SA, (Dec-82=100) % Change - Period to Period",
    "trim16_yoy": "Revised 16% trimmed mean SA, (Dec-82=100) % Change - Year to Year",
    "trim16_saar": "Revised 16% trimmed mean SAAR",
    "cpi_yoy": "CPI-U: All Items NSA, (1982-84=100) % Change - Year to Year",
    "cpi_saar": "CPI-U: All Items SAAR",
    "core_cpi_yoy": "CPI-U: All Items Less Food and Energy NSA, (1982-84=100) % Change - Year to Year",
    "core_cpi_saar": "CPI-U: All Items Less Food and Energy SAAR",
    "pce_yoy": "PCE: Chain Price Index SA, (2005=100) % Change - Year to Year",
    "core_pce_yoy": "PCE less Food & Energy: Chain Price Index SA, (2005=100) % Change - Year to Year",
    "core_pce_saar": "PCE less Food & Energy: Chain Price Index SAAR",
}

#: Pre-2005-vintage Cleveland columns, used only before 1983.
_CLEVELAND_ORIGINAL = {
    "median_saar": "Original FRB Cleveland Median CPI SAAR",
    "median_yoy": "Original FRB Cleveland Median CPI SA, (Jan-67=100) % Change - Year to Year",
    "trim16_saar": "Original 16% trimmed mean SAAR",
    "trim16_yoy": "Original 16% trimmed mean SA, (Jan-67=100) % Change - Year to Year",
}


# ----------------------------------------------------------------------------
# Cleveland Fed
# ----------------------------------------------------------------------------
def cleveland_history(force: bool = False, splice_original: bool = True) -> pd.DataFrame:
    """Monthly frame of the Cleveland measures and their reference series.

    Columns are the keys of :data:`_CLEVELAND_COLUMNS`.  The file's second row
    is an agency-attribution row, not data, and is skipped; ``#N/A`` is the
    missing marker.

    ``splice_original`` fills the pre-1983 gap in the revised measures with the
    original-vintage series.  The two are different methodologies (the revision
    changed the seasonal adjustment and the component set), so the splice is a
    display convenience -- validation should use the revised span, and
    :func:`ism.trim_validate.compare_to_official` does.
    """
    path = fetch_url_bytes(CLEVELAND_HISTORY_URL, "cleveland_usinflationdata.zip",
                           force=force)
    raw = pd.read_csv(_maybe_unzip(path, CLEVELAND_HISTORY_MEMBER),
                      skiprows=[1], encoding="latin-1")
    raw["Date"] = pd.to_datetime(raw["Date"], format="%m/%d/%Y", errors="coerce")
    raw = raw.dropna(subset=["Date"]).set_index("Date").sort_index()
    raw = raw.replace("#N/A", np.nan).apply(pd.to_numeric, errors="coerce")

    out = {}
    for name, fragment in _CLEVELAND_COLUMNS.items():
        col = _first_column(raw, fragment)
        if col is not None:
            out[name] = raw[col]
    frame = pd.DataFrame(out)

    if splice_original:
        for name, fragment in _CLEVELAND_ORIGINAL.items():
            col = _first_column(raw, fragment)
            if col is None or name not in frame:
                continue
            frame[name] = frame[name].combine_first(raw[col])
    frame.index.name = "date"
    return frame


def cleveland_components(force: bool = False) -> pd.DataFrame:
    """Latest-month component table: the cross-section the median was taken of.

    Returns ``[component, rate_ann, ri, cum_ri]``.  ``ri`` is already normalised
    to sum to 100 over the 45 components, so it can be compared directly with
    the weight vector our pipeline builds -- which is the sharpest available
    check that the versioned weights are right.
    """
    path = fetch_url_bytes(CLEVELAND_COMPONENTS_URL,
                           "cleveland_component_table.csv", force=force)
    df = pd.read_csv(path, encoding="latin-1")
    df.columns = ["component", "rate_ann", "ri", "cum_ri"][:len(df.columns)]
    df["component"] = df["component"].astype(str).str.strip()
    for c in ("rate_ann", "ri", "cum_ri"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ----------------------------------------------------------------------------
# Dallas Fed
# ----------------------------------------------------------------------------
def dallas_history(force: bool = False) -> pd.DataFrame:
    """Trimmed mean PCE at 1-, 6- and 12-month horizons, annualised, from 1977.

    Columns ``m1``, ``m6``, ``m12``.  The workbook uses ``#NAN`` for missing and
    carries four header rows above the data.
    """
    path = fetch_url_bytes(DALLAS_HISTORY_URL, "dallas_pcehist.xlsx", force=force)
    raw = pd.read_excel(path, sheet_name=0, header=None,
                        usecols=[0, 1, 2, 3], names=["date", "m1", "m6", "m12"])
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw = raw.dropna(subset=["date"]).set_index("date").sort_index()
    out = raw.replace(["#NAN", "#N/A"], np.nan).apply(pd.to_numeric, errors="coerce")
    out = out.dropna(how="all")
    out.index.name = "date"
    return out


def dallas_detail(force: bool = False) -> pd.DataFrame:
    """Latest-month PCE component detail, with the trim labels Dallas applied.

    Returns ``[component, rate_ann, weight, cum_weight, status]`` where
    ``status`` is one of ``cut_bottom`` / ``included`` / ``cut_top``.  The
    workbook itself only colours the rows, but the cumulative weight column
    reproduces the labels exactly against the published 24% / 31% cut, so we
    derive them rather than parse cell fills.
    """
    path = fetch_url_bytes(DALLAS_DETAIL_URL, "dallas_detail.xlsx", force=force)
    raw = pd.read_excel(path, sheet_name=0, header=None)
    head = None
    for i in range(min(12, len(raw))):
        row = [str(v).strip().lower() for v in raw.iloc[i].tolist()]
        if any("annualized" in v for v in row):
            head = i
            break
    if head is None:
        raise ValueError("could not find the header row in the Dallas detail sheet")

    body = raw.iloc[head + 1:, :4].copy()
    body.columns = ["component", "rate_ann", "weight", "cum_weight"]
    body = body.dropna(subset=["component"])
    body["component"] = body["component"].astype(str).str.strip()
    for c in ("rate_ann", "weight", "cum_weight"):
        body[c] = pd.to_numeric(body[c], errors="coerce")
    body = body.dropna(subset=["rate_ann", "weight"]).reset_index(drop=True)

    lo, hi = 24.0, 69.0          # the published trim: 24% bottom, 31% top
    prev = body["cum_weight"] - body["weight"]
    body["status"] = np.where(body["cum_weight"] <= lo, "cut_bottom",
                     np.where(prev >= hi, "cut_top", "included"))
    return body



# ----------------------------------------------------------------------------
# Bank of Canada / Statistics Canada
# ----------------------------------------------------------------------------
def statcan_core_history(force: bool = False) -> pd.DataFrame:
    """The Bank of Canada's preferred core measures, from StatCan table 18-10-0256.

    CPI-trim and CPI-median are the two limited-influence measures in the pair;
    both are computed on the *monthly* cross-section, which is the same object
    our estimator trims -- so unlike most foreign gauges these are a real
    validation target, not just an overlay.

    Two caveats that the comparison cannot paper over, both stated in the table's
    own metadata:

    * the Bank's inputs are **tax-adjusted** (the effect of changes in indirect
      taxes is removed) and seasonally adjusted with StatCan's per-series
      specifications; ours are neither, so a gap of a tenth or two is expected
      rather than a bug;
    * since the January 2024 reference month the published year-over-year
      figures are computed from index values rounded to one decimal.

    Returns columns ``trim_yoy``, ``median_yoy`` (published y/y, %),
    ``trim_index``, ``median_index`` (1989-01 = 100) and ``trim_saar`` /
    ``median_saar`` (annualised month-over-month, derived from those indexes so
    the 1-month horizon can be scored at all).
    """
    path = fetch_url_bytes(STATCAN_CORE_URL, "statcan_18100256.zip", force=force)
    raw = pd.read_csv(_maybe_unzip(path, STATCAN_CORE_MEMBER),
                      encoding="utf-8-sig", low_memory=False)
    raw = raw[raw["GEO"].astype(str).str.strip() == "Canada"]
    raw["date"] = pd.to_datetime(raw["REF_DATE"], format="%Y-%m", errors="coerce")
    raw = raw.dropna(subset=["date"])
    raw["VALUE"] = pd.to_numeric(raw["VALUE"], errors="coerce")

    measure = raw["Alternative measures"].astype(str)
    out = {}
    for name, needles in _STATCAN_MEASURES.items():
        hit = measure.str.contains(needles[0], case=False, regex=False)
        for extra in needles[1:]:
            hit &= measure.str.contains(extra, case=False, regex=False)
        block = raw[hit]
        if block.empty:
            continue
        out[name] = (block.set_index("date")["VALUE"]
                     .groupby(level=0).last().sort_index())
    frame = pd.DataFrame(out).sort_index()

    for m in ("trim", "median"):
        lvl = frame.get(f"{m}_index")
        if lvl is not None:
            frame[f"{m}_saar"] = 100.0 * ((lvl / lvl.shift(1)) ** 12 - 1.0)
    frame.index.name = "date"
    return frame


# ----------------------------------------------------------------------------
# Bank of Japan
# ----------------------------------------------------------------------------
def boj_core_history(force: bool = False) -> pd.DataFrame:
    """The Bank of Japan's core indicators from ``cpirev.xlsx``.

    The Research and Statistics Department publishes a 10% trimmed mean, a
    weighted median, a mode and a diffusion index, each as a **year-over-year**
    rate and each estimated separately on every CPI base (2000, 2005, 2010,
    2015, 2020, 2025).  We splice newest-base-first, which is how the Bank's own
    charts present them.

    The methodological difference that matters: the Bank trims the
    cross-section of *twelve-month* price changes (Hogen, Kawamoto and Nakahama,
    "Core Inflation and the Business Cycle", BoJ Review 2015-E-6, Chart 4),
    whereas Cleveland, Dallas and the Bank of Canada trim the *monthly*
    cross-section and chain the result.  Our engine does the latter, so the BoJ
    series belongs on the chart as a published reference -- the same measure in
    spirit, built on a different cross-section -- and the scores in
    :func:`ism.trim_validate.compare_to_official` should be read as agreement
    between two constructions, not as a replication test.

    The Bank's figures also strip "institutional factors" (consumption-tax
    changes, free-education policies, the 2021 mobile-phone cuts, travel
    subsidies, energy-cost relief); the official CPI we trim does not.

    Returns ``trim10_yoy``, ``median_yoy``, ``mode_yoy``, ``diffusion``.
    """
    path = fetch_url_bytes(BOJ_CORE_URL, "boj_cpirev.xlsx", force=force)
    raw = pd.read_excel(path, sheet_name=BOJ_CORE_SHEET, header=None)

    dates = pd.to_datetime(raw.iloc[BOJ_FIRST_ROW:, 0], errors="coerce")
    keep = dates.notna().to_numpy()
    idx = pd.DatetimeIndex(dates[keep]).to_period("M").to_timestamp()

    #: newest base first, so ``combine_first`` down the list back-fills history
    def _base_rank(label: str) -> int:
        digits = "".join(ch for ch in str(label) if ch.isdigit())
        return -int(digits) if digits else 1

    out = {}
    for name, fragment in _BOJ_COLUMNS.items():
        cols = [c for c in range(raw.shape[1])
                if fragment.lower() in " ".join(str(raw.iat[BOJ_HEADER_ROW, c])
                                                .split()).lower()]
        cols.sort(key=lambda c: _base_rank(raw.iat[BOJ_BASE_ROW, c]))
        series = None
        for c in cols:
            s = pd.Series(pd.to_numeric(raw.iloc[BOJ_FIRST_ROW:, c][keep],
                                        errors="coerce").to_numpy(), index=idx)
            series = s if series is None else series.combine_first(s)
        if series is not None:
            out[name] = series.groupby(level=0).last()
    frame = pd.DataFrame(out).sort_index().dropna(how="all")
    frame.index.name = "date"
    return frame

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _maybe_unzip(path: Path, member: str) -> io.BytesIO | Path:
    """Return a readable handle, transparently unwrapping a ZIP archive.

    The Cleveland Fed changes its mind about whether a download is the CSV or
    a ZIP containing it (and serves the ZIP under a ``.csv`` URL), so sniff the
    magic bytes rather than trusting the extension.
    """
    import zipfile
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic != b"PK":
        return path
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith(member)]
        if not names:
            raise ValueError(f"{path.name} has no member ending in {member!r}")
        return io.BytesIO(zf.read(names[0]))


def _first_column(frame: pd.DataFrame, fragment: str) -> Optional[str]:
    """First column whose name contains ``fragment`` (whitespace-normalised)."""
    target = " ".join(fragment.split()).lower()
    for col in frame.columns:
        if target in " ".join(str(col).split()).lower():
            return col
    return None
