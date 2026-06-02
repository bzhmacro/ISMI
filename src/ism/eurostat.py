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
        filters = filters or {}
        # stable cache key
        key = code + "_" + "_".join(f"{k}-{','.join(v) if isinstance(v, list) else v}"
                                    for k, v in sorted(filters.items()))
        key = "".join(ch if ch.isalnum() or ch in "-_" else "" for ch in key)[:150]
        cache = self.cache_dir / f"{key}.json"
        if cache.exists() and not force:
            payload = json.loads(cache.read_text())
        else:
            params = [("format", "JSON"), ("lang", "EN")]
            for k, v in filters.items():
                for vv in (v if isinstance(v, list) else [v]):
                    params.append((k, vv))
            resp = _request("GET", f"{EUROSTAT_BASE}/{code}", provider="EUROSTAT", params=params, timeout=120)
            payload = resp.json()
            cache.write_text(json.dumps(payload))
            (cache.with_suffix(".fetch.json")).write_text(json.dumps(
                {"dataset": code, "filters": filters}))
        df = parse_jsonstat(payload)
        if "time" in df.columns:
            df["date"] = _eu_time_to_timestamp(df["time"])
        return df


# ---------------------------------------------------------------------------
# HICP category panel + weights (the euro-area analogue of the PCE panel)
# ---------------------------------------------------------------------------
def hicp_price_panel(client: EurostatClient, geo: str = "EA20", unit: str = "I15", force: bool = False) -> pd.DataFrame:
    """Monthly HICP index panel [time x COICOP] for a geography (default euro area).

    Pulls prc_hicp_midx for all COICOP codes. The COICOP code structure encodes
    the hierarchy (CP00 -> CP01 -> CP011 -> CP0111 ...), the analogue of the BEA
    line levels used to choose the disaggregation level.
    """
    df = client.dataset("prc_hicp_midx", {"freq": "M", "unit": unit, "geo": geo}, force=force)
    wide = df.pivot_table(index="date", columns="coicop", values="value", aggfunc="first").sort_index()
    return wide


def hicp_weights(client: EurostatClient, geo: str = "EA20", force: bool = False) -> pd.DataFrame:
    """Annual HICP item weights [year x COICOP] (per mille) from prc_hicp_inw.

    HICP weights are annual; the caller forward-fills them to monthly to match the
    price panel before passing to the engine.
    """
    df = client.dataset("prc_hicp_inw", {"geo": geo}, force=force)
    tcol = "time" if "time" in df.columns else df.columns[0]
    df["year"] = df[tcol].astype(str).str[:4].astype(int)
    return df.pivot_table(index="year", columns="coicop", values="value", aggfunc="first").sort_index()


def monthly_weights_from_annual(annual_w: pd.DataFrame, month_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward-fill annual HICP weights onto a monthly index (weights set each Jan)."""
    w = annual_w.copy()
    w.index = pd.to_datetime(w.index.astype(str) + "-01-01")
    return w.reindex(month_index.union(w.index)).sort_index().ffill().reindex(month_index)
