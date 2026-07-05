"""
ism.eurostat
============

Client + parser for the Eurostat dissemination API (JSON-stat 2.0), the European
analogue of our FRED/BEA clients. This is the data backbone for porting the ISM
index to the euro area / EU.

API guide: https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started
Base:      https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?format=JSON&...

The category panel for Europe comes from the **HICP** (Harmonised Index of
Consumer Prices), which is disaggregated by COICOP — the European analogue of the
BEA PCE underlying-detail categories:
  * prc_hicp_midx : HICP monthly index (e.g. unit I15 = 2015=100) by COICOP   -> prices pi_{i,t}
  * prc_hicp_inw  : HICP item weights (per mille, annual) by COICOP            -> weights w_{i,t}

Everything here mirrors the US side: once an (inflation_panel, weights) pair is
built it flows through the SAME `ism.engine.compute_ism`. Only the data plumbing
differs.

NOTE: like BEA/FRED, the Eurostat host is blocked from this project's build
sandbox; this client is meant to run in your environment. The JSON-stat parser is
unit-tested on a synthetic payload.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, _request

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
RAW_EU = REPO_ROOT / "data" / "raw" / "eurostat"


# ---------------------------------------------------------------------------
# JSON-stat 2.0 parser
# ---------------------------------------------------------------------------
def parse_jsonstat(payload: Dict[str, Any]) -> pd.DataFrame:
    """Decode a JSON-stat 2.0 dataset into a tidy long DataFrame.

    Columns: one per dimension id (holding the category CODE) plus 'value'. The
    sparse `value` map is expanded using row-major strides over `size`.
    """
    dims = payload["id"]
    sizes = payload["size"]
    # row-major strides
    strides = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    # position -> code for each dimension
    pos2code = {}
    for dim in dims:
        idx = payload["dimension"][dim]["category"]["index"]
        if isinstance(idx, dict):
            pos2code[dim] = {pos: code for code, pos in idx.items()}
        else:  # list form: position is the list order
            pos2code[dim] = {pos: code for pos, code in enumerate(idx)}

    rows = []
    for flat, val in payload["value"].items():
        f = int(flat)
        rec = {}
        for i, dim in enumerate(dims):
            pos = (f // strides[i]) % sizes[i]
            rec[dim] = pos2code[dim][pos]
        rec["value"] = val
        rows.append(rec)
    return pd.DataFrame(rows)


def _eu_time_to_timestamp(s: pd.Series) -> pd.Series:
    """Eurostat monthly time codes ('2020-01' or '2020M01') -> month-start Timestamp."""
    t = s.astype(str).str.replace("M", "-", regex=False)
    return pd.to_datetime(t + "-01", errors="coerce")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class EurostatClient:
    """Minimal Eurostat dissemination-API client (cached + provenance)."""

    def __init__(self, cache_dir: Path = RAW_EU):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def dataset(self, code: str, filters: Optional[Dict[str, Any]] = None, force: bool = False) -> pd.DataFrame:
        """Fetch a dataset as a tidy long DataFrame (dimension codes + value + date).

        `filters` are appended as query params (e.g. {"freq":"M","unit":"I15",
        "geo":"EA","coicop":"CP00"}). A dimension may be repeated by passing a list
        value, which is expanded to multiple query params.
        """
        payload = self.payload(code, filters, force=force)
        df = parse_jsonstat(payload)
        if "time" in df.columns:
            df["date"] = _eu_time_to_timestamp(df["time"])
        return df

    def payload(self, code: str, filters: Optional[Dict[str, Any]] = None, force: bool = False) -> Dict[str, Any]:
        """Fetch (cached) and return the raw JSON-stat payload for a dataset.

        Useful when the caller needs dimension metadata (e.g. category labels)
        in addition to the values; `dataset()` is built on top of this.
        """
        filters = filters or {}
        # stable cache key
        key = code + "_" + "_".join(f"{k}-{','.join(v) if isinstance(v, list) else v}"
                                    for k, v in sorted(filters.items()))
        key = "".join(ch if ch.isalnum() or ch in "-_" else "" for ch in key)[:150]
        cache = self.cache_dir / f"{key}.json"
        if cache.exists() and not force:
            return json.loads(cache.read_text())
        params = [("format", "JSON"), ("lang", "EN")]
        for k, v in filters.items():
            for vv in (v if isinstance(v, list) else [v]):
                params.append((k, vv))
        resp = _request("GET", f"{EUROSTAT_BASE}/{code}", provider="EUROSTAT", params=params, timeout=120)
        payload = resp.json()
        cache.write_text(json.dumps(payload))
        (cache.with_suffix(".fetch.json")).write_text(json.dumps(
            {"dataset": code, "filters": filters}))
        return payload

    def dimension_labels(self, code: str, dim: str, filters: Optional[Dict[str, Any]] = None,
                         force: bool = False) -> Dict[str, str]:
        """{category code: human label} for one dimension of a dataset."""
        payload = self.payload(code, filters, force=force)
        return dict(payload["dimension"][dim]["category"].get("label", {}))


# ---------------------------------------------------------------------------
# HICP category panel + weights (the euro-area analogue of the PCE panel)
# ---------------------------------------------------------------------------
# ECOICOP version 2 (Jan 2026): Eurostat FROZE the v1 datasets (prc_hicp_midx /
# prc_hicp_inw) at 2025-12 and now publishes under new codes with a renamed
# COICOP dimension and an all-items code of "TOTAL" (was "CP00"). The v2
# datasets carry recalculated back-series to 1996, so we read v2 only.
HICP_INDEX_DATASET = "prc_hicp_minr"     # was prc_hicp_midx (frozen 2025-12)
HICP_WEIGHT_DATASET = "prc_hicp_iw"      # was prc_hicp_inw  (frozen 2025)
HICP_COICOP_DIM = "coicop18"             # was "coicop"
HICP_ALL_ITEMS = "TOTAL"                 # was "CP00"


def hicp_price_panel(client: EurostatClient, geo: str = "EA20", unit: str = "I15", force: bool = False) -> pd.DataFrame:
    """Monthly HICP index panel [time x COICOP] for a geography (default euro area).

    Pulls prc_hicp_minr (ECOICOP v2; back-series to 1996) for all COICOP codes.
    The CP-code structure still encodes the hierarchy (CP01 -> CP011 -> CP0111
    ...), the analogue of the BEA line levels used to choose the disaggregation
    level; the all-items aggregate is now "TOTAL".
    """
    df = client.dataset(HICP_INDEX_DATASET, {"freq": "M", "unit": unit, "geo": geo}, force=force)
    dim = HICP_COICOP_DIM if HICP_COICOP_DIM in df.columns else "coicop"
    wide = df.pivot_table(index="date", columns=dim, values="value", aggfunc="first").sort_index()
    return wide


def hicp_weights(client: EurostatClient, geo: str = "EA20", force: bool = False) -> pd.DataFrame:
    """Annual HICP item weights [year x COICOP] (per mille) from prc_hicp_iw (v2).

    HICP weights are annual; the caller forward-fills them to monthly to match the
    price panel before passing to the engine.
    """
    df = client.dataset(HICP_WEIGHT_DATASET, {"geo": geo}, force=force)
    dim = HICP_COICOP_DIM if HICP_COICOP_DIM in df.columns else "coicop"
    tcol = "time" if "time" in df.columns else df.columns[0]
    df["year"] = df[tcol].astype(str).str[:4].astype(int)
    return df.pivot_table(index="year", columns=dim, values="value", aggfunc="first").sort_index()


def hicp_labels(client: EurostatClient, geo: str = "EA20", force: bool = False) -> Dict[str, str]:
    """{COICOP code: label} for the HICP index dataset (one cheap call)."""
    return client.dimension_labels(HICP_INDEX_DATASET, HICP_COICOP_DIM,
                                   {"freq": "M", "geo": geo, "lastTimePeriod": "1"},
                                   force=force)


def monthly_weights_from_annual(annual_w: pd.DataFrame, month_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward-fill annual HICP weights onto a monthly index (weights set each Jan)."""
    w = annual_w.copy()
    w.index = pd.to_datetime(w.index.astype(str) + "-01-01")
    return w.reindex(month_index.union(w.index)).sort_index().ffill().reindex(month_index)


# ---------------------------------------------------------------------------
# Quarterly household consumption by DURABILITY (the decomposition port's data)
# ---------------------------------------------------------------------------
# Eurostat national accounts dataset namq_10_fcs, "Final consumption aggregates
# by durability", quarterly, seasonally + calendar adjusted (SCA). The four
# household leaves (na_item) are durable / semi-durable / non-durable goods and
# services -- the same coarse four-way split used by the Japan SNA port. Both
# nominal (CP_MEUR) and chain-linked real (CLV20_MEUR) are available, so an
# implicit deflator and a real quantity can be formed per category. Works for
# ANY EU/EEA geo (geo="DE", "FR", "IT", "ES", ...). Input for
# ism.decomp_ports.build_de_panels (and portable to other EU countries).
NAMQ_FCS_DATASET = "namq_10_fcs"
EU_HCE_DURABILITY = {                # na_item -> (key, English label)
    "P311_S14": ("durable", "Durable goods"),
    "P312_S14": ("semidurable", "Semi-durable goods"),
    "P313_S14": ("nondurable", "Non-durable goods"),
    "P314_S14": ("services", "Services"),
}


def _eu_quarter_to_timestamp(code) -> Optional[pd.Timestamp]:
    """Eurostat quarterly period code 'YYYY-Qn' -> quarter-start Timestamp."""
    s = str(code)
    if "-Q" in s:
        y, q = s.split("-Q", 1)
        if y.isdigit() and q.isdigit() and 1 <= int(q) <= 4:
            return pd.Timestamp(int(y), 3 * int(q) - 2, 1)
    return None


def eu_hce_panels(client: Optional[EurostatClient] = None, geo: str = "DE",
                  ref_unit: str = "CLV20_MEUR", force: bool = False):
    """(nominal, volume, labels) for quarterly HCE by durability (Eurostat namq_10_fcs).

    nominal = current-price (CP_MEUR); volume = chain-linked real (`ref_unit`,
    default 2020-referenced CLV). Four durability leaves, SCA. Same
    (nominal, volume, labels) contract as the other quarterly decomposition
    ports; `geo` selects the country (DE, FR, IT, ES, NL, ...).
    """
    client = client or EurostatClient()

    def _wide(unit: str) -> pd.DataFrame:
        df = client.dataset(NAMQ_FCS_DATASET,
                            {"freq": "Q", "geo": geo, "s_adj": "SCA", "unit": unit},
                            force=force)
        df = df[df["na_item"].isin(EU_HCE_DURABILITY)].copy()
        df["d"] = df["time"].map(_eu_quarter_to_timestamp)
        df = df.dropna(subset=["d"])
        df["key"] = df["na_item"].map(lambda k: EU_HCE_DURABILITY[k][0])
        return df.pivot_table(index="d", columns="key", values="value",
                              aggfunc="first").sort_index()

    nominal = _wide("CP_MEUR")
    volume = _wide(ref_unit)
    labels = {key: lab for key, lab in EU_HCE_DURABILITY.values()}
    cols = [c for c in nominal.columns if c in volume.columns]
    return nominal[cols], volume[cols], {c: labels[c] for c in cols}
