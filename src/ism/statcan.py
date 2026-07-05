"""
ism.statcan
===========

Client + parsers for Statistics Canada (StatCan) tables, the Canadian analogue
of our FRED/BEA/BLS/ONS/Eurostat clients. Data backbone for BOTH Canadian
models (see config/sources_canada.yaml):

  * the **supply/demand decomposition** (BoC SAP 2026-33): table 36-10-0124
    "Detailed household final consumption expenditure, Canada, quarterly" —
    current prices (nominal) + 2017 constant prices (real), seasonally
    adjusted at quarterly rates, ~99 pinned leaf categories from 1961Q1
    (config/ca_hce_categories.csv);
  * the **ISM momentum index**: tables 18-10-0004 (CPI monthly, NSA, by
    product) + 18-10-0007 (CPI basket weights by vintage), Canada geography,
    pinned leaves in config/ca_cpi_categories.csv.

Fetch routes (in order of preference):

  1. **Assembled cache** under data/raw/statcan/ — always used when present.
     The caches are compact CSVs (REF_DATE, COORDINATE, VALUE) assembled from
     chunked pulls of the "db loading" CSV endpoint; `assemble_chunks()`
     rebuilds them from data/raw/statcan/chunks<pid>/*.csv.
  2. **db-loading CSV endpoint** (plain GET, no key) for member/date subsets:
       https://www150.statcan.gc.ca/t1/tbl1/en/dtl!downloadDbLoadingData-
           nonTraduit.action?pid={pid}01&latestN=N&startDate=YYYYMMDD
           &endDate=YYYYMMDD&csvLocale=en&selectedMembers=[[..],[..],..]
     Used by `fetch_*` methods when run on a machine with open access to
     www150.statcan.gc.ca (the analysis sandbox blocks the host; caches are
     shipped so everything still builds).
  3. **WDS full-table zip** for bulk refresh (scripts/fetch_statcan.py):
       https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{pid}/en

Conventions and gotchas (verified against live metadata, 2026-07):
  * REF_DATE is 'YYYY-MM'; for quarterly tables the month is the quarter's
    first month ('1990-01' = 1990Q1). All caches use UTF-8 (BOM stripped).
  * COORDINATE encodes the member ids dimension-by-dimension ('1.2.1.47' =
    Canada . 2017-constant . SA . member 47 for 36-10-0124).
  * 18-10-0004: Canada is Geography member 2; product names carry base-period
    suffixes (' (2013=100)') that must be stripped before matching weights.
  * 18-10-0007: Canada is Geography member 1(!); product member ids DIFFER
    from 18-10-0004 — align by cleaned name; some names have trailing spaces.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote

import pandas as pd

from .datasources import REPO_ROOT, _request, _write_provenance

RAW_STATCAN = REPO_ROOT / "data" / "raw" / "statcan"
CONFIG_DIR = REPO_ROOT / "config"

BASE_TBL = "https://www150.statcan.gc.ca/t1/tbl1/en"
WDS_ZIP = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{pid}/en"

PID_HCE = "36100124"        # detailed HCE, quarterly (decomposition)
PID_CPI = "18100004"        # CPI monthly NSA by product (ISM)
PID_CPI_W = "18100007"      # CPI basket weights by vintage (ISM)

#: price-basis member ids in 36-10-0124's "Prices" dimension
HCE_BASE_NOMINAL = 1        # current prices
HCE_BASE_REAL = 2           # 2017 constant prices


def _strip_base_suffix(name: str) -> str:
    """Drop ' (2013=100)'-style base tags + outer whitespace from CPI names."""
    return re.sub(r"\s*\(\d{4,6}=100\)\s*$", "", str(name)).strip()


# ---------------------------------------------------------------------------
# URL builder + chunk assembly (shared with scripts/fetch_statcan.py)
# ---------------------------------------------------------------------------
def db_loading_url(pid: str, selected_members: list[list[int]],
                   start: str = "", end: str = "") -> str:
    """The db-loading CSV GET URL for a member/date subset of a cube.

    `selected_members` is one list of member ids per dimension, in cube order;
    dates are 'YYYYMMDD' (empty = unbounded).
    """
    members = json.dumps(selected_members, separators=(",", ":"))
    return (f"{BASE_TBL}/dtl!downloadDbLoadingData-nonTraduit.action?"
            f"pid={pid}01&latestN=0&startDate={start}&endDate={end}"
            f"&csvLocale=en&selectedMembers={quote(members)}")


def metadata_url(pid: str) -> str:
    """The cube-metadata CSV GET URL (dimensions, members, hierarchy)."""
    return f"{BASE_TBL}/dtl!downloadCubeMetaData-nonTraduit.action?pid={pid}01&csvLocale=en"


def compact_db_csv(text: str) -> pd.DataFrame:
    """Verbose db-loading CSV text -> compact (REF_DATE, COORDINATE, VALUE)."""
    from io import StringIO
    df = pd.read_csv(StringIO(text.lstrip("﻿")), dtype=str)
    need = ["REF_DATE", "COORDINATE", "VALUE"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"db-loading CSV missing columns {missing}; got {list(df.columns)[:8]}")
    return df[need]


def assemble_chunks(pid: str, out_name: str,
                    chunk_dir: Optional[Path] = None) -> Path:
    """Concatenate chunks<pid>/*.csv -> one deduplicated compact cache CSV.

    Chunks are compact (REF_DATE, COORDINATE, VALUE) files written by the
    chunked fetch (see docstring above / scripts/fetch_statcan.py). Returns
    the assembled cache path (data/raw/statcan/<out_name>).
    """
    chunk_dir = chunk_dir or (RAW_STATCAN / f"chunks{pid}")
    files = sorted(chunk_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no chunks in {chunk_dir}")
    frames = [pd.read_csv(f, dtype=str) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["VALUE"]).drop_duplicates(["REF_DATE", "COORDINATE"])
    df = df.sort_values(["COORDINATE", "REF_DATE"])
    out = RAW_STATCAN / out_name
    df.to_csv(out, index=False)
    _write_provenance(out, f"assembled from {len(files)} chunks in {chunk_dir.name}", {})
    print(f"[statcan] assembled {out.name}: {len(df)} rows from {len(files)} chunks")
    return out


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class StatCanClient:
    """Cache-first StatCan client (mirrors OnsClient / EurostatClient).

    Reads the assembled caches when present; otherwise fetches member/date
    subsets through the db-loading endpoint with `requests` (works wherever
    www150.statcan.gc.ca is reachable — NOT from the analysis sandbox, whose
    proxy blocks the host; run scripts/fetch_statcan.py locally instead).
    """

    def __init__(self, cache_dir: Path = RAW_STATCAN):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- generic subset fetch (requests route) -------------------------------
    def fetch_subset(self, pid: str, selected_members: list[list[int]],
                     start: str = "", end: str = "") -> pd.DataFrame:
        url = db_loading_url(pid, selected_members, start, end)
        resp = _request("GET", url, provider="StatCan", timeout=180)
        return compact_db_csv(resp.text)

    # -- cached compact tables ------------------------------------------------
    def _cached(self, name: str) -> Optional[pd.DataFrame]:
        path = self.cache_dir / name
        if path.exists():
            return pd.read_csv(path, dtype={"REF_DATE": str, "COORDINATE": str})
        return None

    def hce(self, force: bool = False) -> pd.DataFrame:
        """Compact 36-10-0124 subset: Canada, SA, both price bases, pinned leaves."""
        cached = None if force else self._cached("36100124_ca_sa.csv")
        if cached is not None:
            return cached
        cats = load_ca_hce_categories()
        members = sorted(cats["member_id"].astype(int))
        frames = []
        for base in (HCE_BASE_NOMINAL, HCE_BASE_REAL):
            for lo, hi in (("19750101", "19941231"), ("19950101", "20141231"),
                           ("20150101", "")):
                frames.append(self.fetch_subset(
                    PID_HCE, [[1], [base], [1], members], lo, hi))
        df = pd.concat(frames, ignore_index=True).drop_duplicates(
            ["REF_DATE", "COORDINATE"])
        out = self.cache_dir / "36100124_ca_sa.csv"
        df.to_csv(out, index=False)
        _write_provenance(out, db_loading_url(PID_HCE, [[1], [0], [1], members]), {})
        return df

    def cpi(self, force: bool = False) -> pd.DataFrame:
        """Compact 18-10-0004 subset: Canada (geo member 2), pinned leaves."""
        cached = None if force else self._cached("18100004_ca.csv")
        if cached is not None:
            return cached
        cats = load_ca_cpi_categories()
        members = sorted(set(cats["member_id_cpi"].astype(int)) | {2})  # 2 = All-items (headline)
        frames = []
        spans = [("19760101", "19891231"), ("19900101", "20031231"),
                 ("20040101", "20171231"), ("20180101", "")]
        for lo, hi in spans:
            frames.append(self.fetch_subset(PID_CPI, [[2], members], lo, hi))
        df = pd.concat(frames, ignore_index=True).drop_duplicates(
            ["REF_DATE", "COORDINATE"])
        out = self.cache_dir / "18100004_ca.csv"
        df.to_csv(out, index=False)
        _write_provenance(out, db_loading_url(PID_CPI, [[2], members]), {})
        return df

    def cpi_weights(self, force: bool = False) -> pd.DataFrame:
        """Compact 18-10-0007 subset: Canada (geo member 1), link-month prices."""
        cached = None if force else self._cached("18100007_ca.csv")
        if cached is not None:
            return cached
        cats = load_ca_cpi_categories()
        members = sorted(cats["member_id_w"].astype(int))
        # dims: Geography . Products . Price period of weight . Geographic distribution.
        # Geographic distribution member 1 = "Distribution to selected geographies"
        # (where the per-product Canada weights live); member 2 = "Distribution to
        # Canada" only carries the All-items 100%. The db-loading endpoint also
        # needs a date range for this Occasional table (empty dates return an
        # error), so pull from 1986 (the table's first basket year) onward.
        sel = [[1], members, [1], [1]]
        df = self.fetch_subset(PID_CPI_W, sel, "19860101", "")
        out = self.cache_dir / "18100007_ca.csv"
        df.to_csv(out, index=False)
        _write_provenance(out, db_loading_url(PID_CPI_W, sel, "19860101", ""), {})
        return df


# ---------------------------------------------------------------------------
# Pinned category sets
# ---------------------------------------------------------------------------
def load_ca_hce_categories() -> pd.DataFrame:
    """The pinned 36-10-0124 leaf set (config/ca_hce_categories.csv).

    99 leaves = 116 tree leaves minus 15 'adjusting entry' members and the
    net-expenditure-abroad block (members 125/126/127). Includes the three
    cannabis leaves (2018Q4+; absent until a full window, as everywhere else),
    so the effective pre-2018 cross-section is 96 — the BoC paper's count.
    `gs` tags each leaf G(oods)/S(ervices) for the goods/services scopes
    (paper Figs. 3-4); judgment calls documented in docs/DECISIONS.md.
    """
    return pd.read_csv(CONFIG_DIR / "ca_hce_categories.csv")


def load_ca_cpi_categories() -> pd.DataFrame:
    """The pinned CPI leaf set (config/ca_cpi_categories.csv), name-aligned
    across 18-10-0004 (member_id_cpi) and 18-10-0007 (member_id_w)."""
    return pd.read_csv(CONFIG_DIR / "ca_cpi_categories.csv")


# ---------------------------------------------------------------------------
# Panels: decomposition (quarterly HCE)
# ---------------------------------------------------------------------------
def _pivot_quarterly(df: pd.DataFrame, coord_prefix: str,
                     member_pos: int = -1) -> pd.DataFrame:
    """Compact rows with COORDINATE '<prefix>...' -> [date x member].

    `member_pos` locates the category member inside the dot-separated
    COORDINATE (default: last component; the weights cube 18-10-0007 uses
    position 1, its second component).
    """
    sub = df[df["COORDINATE"].str.startswith(coord_prefix)].copy()
    sub["member"] = sub["COORDINATE"].str.split(".").str[member_pos].astype(int)
    sub["date"] = pd.to_datetime(sub["REF_DATE"] + "-01")
    sub["value"] = pd.to_numeric(sub["VALUE"], errors="coerce")
    return sub.pivot_table(index="date", columns="member", values="value",
                           aggfunc="first").sort_index()


def ca_hce_panels(client: Optional[StatCanClient] = None, scope: str = "total",
                  force: bool = False):
    """(nominal, volume, labels) for the Canadian decomposition.

    nominal = current-price HCE ($M, SA at quarterly rates); volume = 2017
    constant-price HCE. `scope` filters the pinned leaves by the G/S tag:
    "total" | "goods" | "services".
    """
    client = client or StatCanClient()
    cats = load_ca_hce_categories()
    if scope == "goods":
        cats = cats[cats["gs"] == "G"]
    elif scope == "services":
        cats = cats[cats["gs"] == "S"]
    elif scope != "total":
        raise ValueError("scope must be 'total', 'goods' or 'services'")

    raw = client.hce(force=force)
    nominal = _pivot_quarterly(raw, f"1.{HCE_BASE_NOMINAL}.1.")
    volume = _pivot_quarterly(raw, f"1.{HCE_BASE_REAL}.1.")

    keep = [m for m in cats["member_id"] if m in nominal.columns and m in volume.columns]
    key_by_id = dict(zip(cats["member_id"], cats["key"]))
    label_by_id = dict(zip(cats["member_id"], cats["label"]))
    nominal = nominal[keep].rename(columns=key_by_id)
    volume = volume[keep].rename(columns=key_by_id)
    labels = {key_by_id[m]: label_by_id[m] for m in keep}
    return nominal, volume, labels


# ---------------------------------------------------------------------------
# Panels: ISM (monthly CPI + vintage weights)
# ---------------------------------------------------------------------------
def ca_cpi_price_panel(client: Optional[StatCanClient] = None,
                       force: bool = False):
    """Monthly CPI index panel [month x key] + {key: label} (Canada, NSA)."""
    client = client or StatCanClient()
    cats = load_ca_cpi_categories()
    raw = client.cpi(force=force)
    panel = _pivot_quarterly(raw, "2.")            # geo member 2; monthly dates
    keep = [m for m in cats["member_id_cpi"] if m in panel.columns]
    key_by_id = dict(zip(cats["member_id_cpi"], cats["key"]))
    panel = panel[keep].rename(columns=key_by_id)
    labels = dict(zip(cats["key"], cats["label"]))
    return panel, {k: labels[k] for k in panel.columns}


def ca_cpi_weights(client: Optional[StatCanClient] = None,
                   keys: Optional[Iterable[str]] = None,
                   force: bool = False) -> pd.DataFrame:
    """Basket weights [vintage year x key] (percent, link-month prices).

    REF_DATE in 18-10-0007 is the basket reference YEAR; each vintage's
    weights are applied from the month the basket goes live (see
    ism.ca_pipeline.monthly_weights_from_vintages).
    """
    client = client or StatCanClient()
    cats = load_ca_cpi_categories()
    raw = client.cpi_weights(force=force)
    panel = _pivot_quarterly(raw, "1.", member_pos=1)   # '1.<product>.1.2' 
    keep = [m for m in cats["member_id_w"] if m in panel.columns]
    key_by_id = dict(zip(cats["member_id_w"], cats["key"]))
    panel = panel[keep].rename(columns=key_by_id)
    panel.index = panel.index.year
    if keys is not None:
        panel = panel[[k for k in keys if k in panel.columns]]
    return panel
