"""
ism.estat
=========

Client + parser for the e-Stat API (Japan's official statistics portal), the
Japanese analogue of our FRED/BEA/BLS/Eurostat/ONS clients. This is the data
backbone for porting the ISM index to Japan (see config/sources_japan.yaml).

ACCESS: e-Stat requires a free application ID — register at
https://www.e-stat.go.jp/api/ and set ``ESTAT_APP_ID`` in .env. Every fetch
method raises a clear error if the key is missing, and callers (the exporter,
the jp pipeline) degrade gracefully.

Endpoints used (REST 3.0, JSON):
  * getMetaInfo  : dimension metadata for a table — classification codes,
                   names and crucially the ``@level`` attribute that encodes
                   the item hierarchy (Japan's cat01 codes are flat 4-digit
                   identifiers; the hierarchy lives in the metadata).
  * getStatsData : the values, paginated (the API caps a response at 100k
                   records; we loop on NEXT_KEY until exhausted).

The 2020-base CPI table (statsDataId 0003427113, statistics 00200573) provides
monthly index values per item classification for Japan; once an
(inflation_panel, weights) pair is built it flows through the SAME
`ism.engine.compute_ism`. Only the data plumbing differs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .datasources import REPO_ROOT, _request, ApiError

ESTAT_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
RAW_JP = REPO_ROOT / "data" / "raw" / "estat"

CPI_2020_TABLE = "0003427113"   # 2020-base CPI, Japan, monthly, by item (cat01)


def _listify(x) -> list:
    """e-Stat JSON uses a bare object where a list has one element."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _jp_time_to_timestamp(code: str) -> Optional[pd.Timestamp]:
    """e-Stat monthly time codes ('2020000101' style or '2020-01') -> Timestamp.

    The CPI DB uses codes like ``2020000101`` = year 2020, month 01 (the middle
    digits vary by table; the year is the first 4 and the month the last 2).
    """
    s = str(code)
    if len(s) >= 6 and s[:4].isdigit() and s[-2:].isdigit():
        y, m = int(s[:4]), int(s[-2:])
        if 1 <= m <= 12:
            return pd.Timestamp(y, m, 1)
    return None


class EstatClient:
    """Minimal e-Stat REST client (cached + provenance), mirroring the others."""

    def __init__(self, app_id: Optional[str] = None, cache_dir: Path = RAW_JP):
        self.app_id = app_id or os.environ.get("ESTAT_APP_ID")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _check_key(self):
        if not self.app_id:
            raise ApiError("ESTAT", "missing application ID: register (free) at "
                           "https://www.e-stat.go.jp/api/ and set ESTAT_APP_ID in .env")

    def _get(self, endpoint: str, params: Dict[str, Any], cache_name: str,
             force: bool = False) -> Dict[str, Any]:
        cache = self.cache_dir / f"{cache_name}.json"
        if cache.exists() and not force:
            return json.loads(cache.read_text())
        self._check_key()
        q = {"appId": self.app_id, "lang": "J", **params}
        resp = _request("GET", f"{ESTAT_BASE}/{endpoint}", provider="ESTAT",
                        params=q, timeout=120)
        payload = resp.json()
        root = next(iter(payload.values()))
        status = root.get("RESULT", {}).get("STATUS")
        if status not in (0, "0"):
            raise ApiError("ESTAT", f"{endpoint} status {status}: "
                           f"{root.get('RESULT', {}).get('ERROR_MSG', '')}")
        cache.write_text(json.dumps(payload, ensure_ascii=False))
        (cache.with_suffix(".fetch.json")).write_text(json.dumps(
            {"endpoint": endpoint, "params": {k: v for k, v in params.items()}},
            ensure_ascii=False))
        return payload

    # -- metadata -------------------------------------------------------------
    def meta(self, table_id: str = CPI_2020_TABLE, force: bool = False) -> Dict[str, Any]:
        """getMetaInfo payload for a table (classification codes, names, levels)."""
        return self._get("getMetaInfo", {"statsDataId": table_id},
                         f"meta_{table_id}", force=force)

    def class_frame(self, table_id: str = CPI_2020_TABLE, dim: str = "cat01",
                    force: bool = False) -> pd.DataFrame:
        """One dimension's classification as a tidy frame (code, name, level, ...)."""
        payload = self.meta(table_id, force=force)
        root = next(iter(payload.values()))
        objs = _listify(root["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"])
        obj = next(o for o in objs if o.get("@id") == dim)
        rows = []
        for c in _listify(obj.get("CLASS")):
            rows.append({"code": c.get("@code"), "name": c.get("@name"),
                         "level": c.get("@level"), "unit": c.get("@unit"),
                         "parent": c.get("@parentCode")})
        return pd.DataFrame(rows)

    # -- data -----------------------------------------------------------------
    def stats_data(self, table_id: str = CPI_2020_TABLE,
                   filters: Optional[Dict[str, Any]] = None,
                   force: bool = False, max_pages: int = 50) -> pd.DataFrame:
        """getStatsData -> tidy long frame (one column per dimension + value).

        `filters` are passed through (e.g. {"cdArea": "00000", "cdTab": "1"}).
        Pagination via NEXT_KEY is handled transparently; pages are cached as
        one combined file per (table, filters) key.
        """
        filters = dict(filters or {})
        key = table_id + "_" + "_".join(f"{k}-{v}" for k, v in sorted(filters.items()))
        key = "".join(ch if ch.isalnum() or ch in "-_" else "" for ch in key)[:150]
        cache = self.cache_dir / f"data_{key}.parts.json"
        if cache.exists() and not force:
            parts = json.loads(cache.read_text())
        else:
            parts, start = [], 1
            for _ in range(max_pages):
                payload = self._get(
                    "getStatsData",
                    {"statsDataId": table_id, "startPosition": start,
                     "metaGetFlg": "Y" if start == 1 else "N", **filters},
                    f"tmp_{key}_{start}", force=True)
                root = next(iter(payload.values()))
                parts.append(payload)
                inf = root["STATISTICAL_DATA"]["RESULT_INF"]
                nxt = inf.get("NEXT_KEY")
                if not nxt:
                    break
                start = int(nxt)
            cache.write_text(json.dumps(parts, ensure_ascii=False))
            for p in self.cache_dir.glob(f"tmp_{key}_*"):
                p.unlink(missing_ok=True)
        return self._parts_to_frame(parts)

    @staticmethod
    def _parts_to_frame(parts: List[Dict[str, Any]]) -> pd.DataFrame:
        rows = []
        for payload in parts:
            root = next(iter(payload.values()))
            data = root["STATISTICAL_DATA"]["DATA_INF"]
            for v in _listify(data.get("VALUE")):
                rec = {k.lstrip("@"): val for k, val in v.items() if k.startswith("@")}
                rec["value"] = pd.to_numeric(v.get("$"), errors="coerce")
                rows.append(rec)
        df = pd.DataFrame(rows)
        if "time" in df.columns:
            df["date"] = df["time"].map(_jp_time_to_timestamp)
        return df
