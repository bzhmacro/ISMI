"""
ism.ons
=======

Client + parser for ONS (UK Office for National Statistics) time-series data,
the UK analogue of our FRED/BEA/BLS/Eurostat clients. This is the data backbone
for porting the ISM index to the United Kingdom (see config/sources_uk.yaml).

The old api.ons.gov.uk timeseries API was retired on 25/11/2024, so we use the
two surviving plain-HTTP routes:

  * the **bulk dataset CSV** (one download carries every series in a dataset),
    used for MM23 "Consumer price inflation time series" — this single file
    contains the full COICOP CPI index panel, the annual CPI weights, and the
    all-items headline:
        https://www.ons.gov.uk/file?uri=/economy/inflationandpriceindices/
            datasets/consumerpriceindices/current/mm23.csv

  * the **per-series generator CSV** for individual series outside MM23
    (e.g. labour-market series MGSX / MGSC / AP2Y):
        https://www.ons.gov.uk/generator?format=csv&uri=<series page uri>

MM23 layout note: the bulk CSV is *transposed* relative to FRED-style data —
column 0 ("Title") holds row labels (CDID, Unit, ... then time periods), and
each remaining column is one series, titled by its description (e.g.
"CPI INDEX 01.1.1 : BREAD & CEREALS 2015=100"). Time rows mix frequencies:
"1988" (annual), "1988 Q1" (quarterly), "1988 JAN" (monthly).

UK CPI is constructed on HICP methodology and published by COICOP, so the
COICOP class (xx.x.x) is the analogue of the BEA line levels / EU 4-digit cut.
Once an (inflation_panel, weights) pair is built it flows through the SAME
`ism.engine.compute_ism`. Only the data plumbing differs.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path
from typing import Optional

import pandas as pd

from .datasources import REPO_ROOT, _request, _write_provenance

ONS_BASE = "https://www.ons.gov.uk"
MM23_URL = (f"{ONS_BASE}/file?uri=/economy/inflationandpriceindices/"
            "datasets/consumerpriceindices/current/mm23.csv")
# Consumer Trends time-series bulk CSV (same wide layout as MM23): quarterly
# household final consumption expenditure by COICOP — nominal (CP) + chained
# volume (CVM) + implied deflators (IDEF), SA and NSA, quarterly from 1985 Q1
# at class level. Input for the UK supply/demand decomposition port
# (ism.decomp_ports.build_uk_panels; see config/sources_uk.yaml).
CT_URL = (f"{ONS_BASE}/file?uri=/economy/nationalaccounts/satelliteaccounts/"
          "datasets/consumertrends/current/ct.csv")
RAW_ONS = REPO_ROOT / "data" / "raw" / "ons"

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}

# titles look like "CPI INDEX 01.1.1 : BREAD & CEREALS 2015=100" or
# "CPI INDEX 12.7.0.2 Legal services and accountancy 2015=100" (no colon)
_TITLE_RE = re.compile(r"^CPI (INDEX|WEIGHTS) (\d\d(?:\.\d){0,3})\s*:?\s*(.*)$")

# Consumer Trends titles look like
#   "01.1.1 Food Bread and cereals CP SA £m"            (nominal)
#   "01.1.1 Food Bread and cereals CVM NAYear SA £m"    (chained volume)
#   "01.1.1 Food Bread and cereals IDEF NSA 2023=100"   (implied deflator)
_CT_TITLE_RE = re.compile(
    r"^(\d\d(?:\.\d)*)\s+(.*?)\s+(CP|CVM(?: NAYear)?|IDEF)\s+(SA|NSA)\s+(?:-\s+)?(£m|\d{4}=100)$")


def _parse_title(title: str):
    """-> (kind, code, label) for CPI INDEX / CPI WEIGHTS titles, else None."""
    m = _TITLE_RE.match(str(title).strip())
    if not m:
        return None
    kind, code, label = m.group(1).lower(), m.group(2), m.group(3)
    label = re.sub(r"\s*2015=100\s*$", "", label).strip()
    return kind, code, label


def _month_stamp(label: str) -> Optional[pd.Timestamp]:
    """'1988 JAN' -> Timestamp('1988-01-01'); None for annual/quarterly rows."""
    m = re.fullmatch(r"(\d{4}) ([A-Z]{3})", str(label).strip())
    if not m or m.group(2) not in _MONTHS:
        return None
    return pd.Timestamp(int(m.group(1)), _MONTHS[m.group(2)], 1)


def _quarter_stamp(label: str) -> Optional[pd.Timestamp]:
    """'1985 Q1' -> Timestamp('1985-01-01') (quarter start); else None."""
    m = re.fullmatch(r"(\d{4}) Q([1-4])", str(label).strip())
    if not m:
        return None
    return pd.Timestamp(int(m.group(1)), 3 * int(m.group(2)) - 2, 1)


class OnsClient:
    """Minimal ONS client (cached + provenance), mirroring the other clients.

    `mm23()` returns the raw bulk frame (Title-indexed, one column per series);
    `series_csv()` fetches a single series via the generator endpoint.
    """

    def __init__(self, cache_dir: Path = RAW_ONS):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mm23: Optional[pd.DataFrame] = None

    # -- bulk MM23 ----------------------------------------------------------
    def mm23(self, force: bool = False) -> pd.DataFrame:
        """The full MM23 CSV as a DataFrame indexed by the 'Title' column."""
        if self._mm23 is not None and not force:
            return self._mm23
        cache = self.cache_dir / "mm23.csv"
        if force or not cache.exists():
            resp = _request("GET", MM23_URL, provider="ONS", timeout=180)
            cache.write_bytes(resp.content)
            _write_provenance(cache, MM23_URL, {})
        df = pd.read_csv(cache, index_col=0, low_memory=False)
        self._mm23 = df
        return df

    # -- bulk Consumer Trends (quarterly HCE by COICOP) -----------------------
    def ct(self, force: bool = False) -> pd.DataFrame:
        """The full Consumer Trends bulk CSV (ct.csv), Title-indexed.

        Same wide layout as MM23: one column per series, rows = CDID/units
        header block then period labels (annual '1997', quarterly '1985 Q1').
        Carries CP (nominal £m), CVM (chained volume £m) and IDEF (implied
        deflator) for every COICOP division/group/class, SA and NSA.
        """
        if getattr(self, "_ct", None) is not None and not force:
            return self._ct
        cache = self.cache_dir / "ct.csv"
        if force or not cache.exists():
            resp = _request("GET", CT_URL, provider="ONS", timeout=180)
            cache.write_bytes(resp.content)
            _write_provenance(cache, CT_URL, {})
        df = pd.read_csv(cache, index_col=0, low_memory=False)
        self._ct = df
        return df

    # -- single series (generator endpoint) ----------------------------------
    def series_csv(self, uri: str, name: str, force: bool = False) -> pd.Series:
        """Fetch one ONS series page as a monthly Series via /generator.

        `uri` is the series page path, e.g.
        "/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms".
        Monthly rows ('1971 JAN') are kept; annual/quarterly rows dropped.
        """
        cache = self.cache_dir / f"{name}.csv"
        if force or not cache.exists():
            url = f"{ONS_BASE}/generator"
            resp = _request("GET", url, provider="ONS",
                            params={"format": "csv", "uri": uri}, timeout=60)
            cache.write_bytes(resp.content)
            _write_provenance(cache, url, {"uri": uri})
        raw = pd.read_csv(cache, header=None, names=["period", "value"], skiprows=1)
        idx = raw["period"].map(_month_stamp)
        s = pd.Series(pd.to_numeric(raw["value"], errors="coerce").to_numpy(),
                      index=idx, name=name)
        return s[s.index.notna()].dropna().sort_index()


# ---------------------------------------------------------------------------
# MM23 -> panels (the UK analogue of the BEA / BLS / Eurostat panel builders)
# ---------------------------------------------------------------------------
def _monthly_block(mm23: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Extract the monthly rows of MM23 for `cols` -> [month x col] floats."""
    stamps = mm23.index.to_series().map(_month_stamp)
    block = mm23.loc[stamps.notna(), cols].apply(pd.to_numeric, errors="coerce")
    block.index = stamps[stamps.notna()].to_numpy()
    return block.sort_index()


def _annual_block(mm23: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Extract the annual rows of MM23 for `cols` -> [year x col] floats."""
    yearly = mm23.index.to_series().astype(str).str.fullmatch(r"\d{4}")
    block = mm23.loc[yearly.fillna(False), cols].apply(pd.to_numeric, errors="coerce")
    block.index = block.index.astype(int)
    return block.sort_index()


def coicop_catalogue(mm23: pd.DataFrame) -> pd.DataFrame:
    """All CPI INDEX / CPI WEIGHTS columns -> tidy (kind, code, label, title, cdid)."""
    rows = []
    cdid = mm23.iloc[0] if mm23.index[0] == "CDID" else None
    for title in mm23.columns:
        parsed = _parse_title(title)
        if parsed:
            kind, code, label = parsed
            rows.append({"kind": kind, "code": code, "label": label, "title": title,
                         "cdid": None if cdid is None else str(cdid.get(title, "")).strip()})
    return pd.DataFrame(rows)


def select_coicop_leaves(codes: list[str], max_depth: int = 2) -> list[str]:
    """Leaf COICOP codes of the available tree, capped at `max_depth` dots.

    depth = number of dots: '01'=0 (division), '01.1'=1 (group), '01.1.1'=2
    (class), '01.1.1.1'=3 (sub-class). Default cap 2 keeps the class level —
    sub-classes only start 2015-01, too short for the 120m rolling window. A
    code is a leaf if no longer (dot-separated) code extends it. '00' excluded.
    """
    cs = sorted({c for c in codes if c != "00" and c.count(".") <= max_depth})
    return [c for c in cs if not any(o.startswith(c + ".") for o in cs)]


def uk_cpi_price_panel(client: OnsClient, max_depth: int = 2,
                       force: bool = False) -> tuple[pd.DataFrame, dict[str, str]]:
    """Monthly CPI index panel [month x COICOP code] + {code: label} from MM23."""
    mm23 = client.mm23(force=force)
    cat = coicop_catalogue(mm23)
    idx = cat[cat["kind"] == "index"]
    leaves = select_coicop_leaves(idx["code"].tolist(), max_depth=max_depth)
    sel = idx[idx["code"].isin(leaves)].drop_duplicates("code")
    panel = _monthly_block(mm23, sel["title"].tolist())
    panel.columns = sel["code"].tolist()
    labels = dict(zip(sel["code"], sel["label"]))
    return panel, labels


def uk_cpi_weights(client: OnsClient, codes: list[str], force: bool = False) -> pd.DataFrame:
    """Annual CPI weights [year x COICOP code] (per mille) from MM23."""
    mm23 = client.mm23(force=force)
    cat = coicop_catalogue(mm23)
    wts = cat[(cat["kind"] == "weights") & cat["code"].isin(codes)].drop_duplicates("code")
    block = _annual_block(mm23, wts["title"].tolist())
    block.columns = wts["code"].tolist()
    return block


def monthly_weights_from_annual(annual_w: pd.DataFrame,
                                month_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward-fill annual CPI weights onto a monthly index (set each January).

    Same convention as the EU port (`ism.eurostat.monthly_weights_from_annual`):
    the year-Y weights apply from Y-01 and are carried forward until updated.
    """
    w = annual_w.copy()
    w.index = pd.to_datetime(w.index.astype(str) + "-01-01")
    return w.reindex(month_index.union(w.index)).sort_index().ffill().reindex(month_index)


def uk_headline_index(client: OnsClient, force: bool = False) -> pd.Series:
    """All-items CPI index (CDID D7BT, 2015=100), monthly."""
    mm23 = client.mm23(force=force)
    title = next(t for t in mm23.columns
                 if str(t).upper().startswith("CPI INDEX 00"))
    return _monthly_block(mm23, [title]).iloc[:, 0].dropna().rename("uk_cpi")


# ---------------------------------------------------------------------------
# Consumer Trends -> quarterly HCE panels (for the supply/demand decomposition)
# ---------------------------------------------------------------------------
def _quarterly_block(ct: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Extract the quarterly rows of ct.csv for `cols` -> [quarter x col]."""
    stamps = ct.index.to_series().map(_quarter_stamp)
    block = ct.loc[stamps.notna(), cols].apply(pd.to_numeric, errors="coerce")
    block.index = stamps[stamps.notna()].to_numpy()
    return block.sort_index()


def ct_catalogue(ct: pd.DataFrame) -> pd.DataFrame:
    """COICOP-coded Consumer Trends columns -> tidy catalogue.

    Columns: code, label, measure ('cp' | 'cvm' | 'idef'), adj ('SA' | 'NSA'),
    title, cdid. Non-COICOP analytic series (durability splits, tourism and
    national-concept adjustments) carry no leading numeric code and are
    excluded by construction.
    """
    rows = []
    cdid = ct.iloc[0] if ct.index[0] == "CDID" else None
    for title in ct.columns:
        m = _CT_TITLE_RE.match(str(title).strip())
        if not m:
            continue
        code, label, measure, adj = m.group(1), m.group(2), m.group(3), m.group(4)
        rows.append({
            "code": code,
            "label": label.strip(),
            "measure": "cvm" if measure.startswith("CVM") else measure.lower(),
            "adj": adj,
            "title": title,
            "cdid": None if cdid is None else str(cdid.get(title, "")).strip(),
        })
    return pd.DataFrame(rows)


def uk_hce_panels(client: OnsClient, adj: str = "SA", max_depth: int = 2,
                  force: bool = False):
    """Quarterly (nominal, volume) HCE panels [quarter x COICOP] + labels.

    The UK analogue of BEA 2.4.5U / 2.4.3U for the supply/demand decomposition:
    `nominal` is current-price expenditure (CP, £m) and `volume` the chained
    volume measure (CVM, £m), for the leaf COICOP codes present in BOTH
    measures (144 class-level leaves, quarterly from 1985 Q1). `adj="SA"`
    mirrors the seasonally adjusted BEA/StatCan inputs; "NSA" is available for
    robustness. Deflator (price) construction happens in ism.decomp_ports.
    """
    if adj not in ("SA", "NSA"):
        raise ValueError("adj must be 'SA' or 'NSA'")
    ct = client.ct(force=force)
    cat = ct_catalogue(ct)
    cat = cat[cat["adj"] == adj]
    cp = cat[cat["measure"] == "cp"].drop_duplicates("code").set_index("code")
    cvm = cat[cat["measure"] == "cvm"].drop_duplicates("code").set_index("code")
    both = sorted(set(cp.index) & set(cvm.index))
    leaves = select_coicop_leaves(both, max_depth=max_depth)
    nominal = _quarterly_block(ct, cp.loc[leaves, "title"].tolist())
    nominal.columns = leaves
    volume = _quarterly_block(ct, cvm.loc[leaves, "title"].tolist())
    volume.columns = leaves
    labels = {c: cp.loc[c, "label"] for c in leaves}
    return nominal, volume, labels


def uk_hce_deflator_yoy(client: OnsClient, adj: str = "SA",
                        force: bool = False) -> Optional[pd.Series]:
    """Y/y % change of the total-HCE implied deflator (context series)."""
    ct = client.ct(force=force)
    cands = [t for t in ct.columns
             if str(t).startswith("0 ") and "IDEF" in str(t)
             and f" {adj} " in str(t)]
    if not cands:
        return None
    s = _quarterly_block(ct, [cands[0]]).iloc[:, 0].dropna()
    return (100.0 * (s / s.shift(4) - 1.0)).rename("uk_hce_deflator_yoy")
