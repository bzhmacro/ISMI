"""
ism.nordic
==========

Quarterly household consumption by purpose for Norway (SSB) and Sweden (SCB),
the inputs to the supply/demand decomposition ports.  Both agencies run a
keyless PX-Web API (POST a JSON query, get JSON-stat back).  The CPI side of
both countries comes from Eurostat's HICP, exactly as for France and Germany
(Norway and Sweden are in the HICP as EEA/EU members), so only the national
accounts live here.

* **Sweden** -- SCB table ``NR0103ENS2010T14KvN`` (NR/NR0103/NR0103B):
  household consumption expenditure by purpose, COICOP 2018 divisions 01-13,
  seasonally adjusted, current prices and constant prices (reference year
  2025), SEK million, quarterly from 1981-Q1.

* **Norway** -- SSB table ``14658``: household final consumption by COICOP 2018
  division (13), quarterly from 1978-Q1, NOK million.  SSB publishes the
  *volume* seasonally adjusted but current prices **only unadjusted**.  The
  deflator is therefore formed unadjusted (current / constant, both NSA) and its
  quarterly seasonal is removed with the same transparent estimator the trimmed
  mean page uses (`ism.trim_engine.deseasonalise`, quarter dummies re-estimated
  on a trailing 40-quarter window, no look-ahead); nominal is then rebuilt as
  SA deflator x SA volume so the shared `panels_from_nominal_real` contract
  holds.  See docs/DECISIONS.md.

Divisions only: neither agency publishes consumption by purpose below the
division at quarterly frequency.  Direct purchases abroad / by non-residents
(the domestic-to-national bridge) are excluded, as for the other ports.
"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, _request, _write_provenance

RAW_NORDIC = REPO_ROOT / "data" / "raw" / "nordic"
SCB_TABLE = ("https://api.scb.se/OV0104/v1/doris/en/ssd/NR/NR0103/NR0103B/"
             "NR0103ENS2010T14KvN")
SSB_TABLE = "https://data.ssb.no/api/v0/en/table/14658"
SE_DIVISIONS = [f"CP{i:02d}" for i in range(1, 14)]
NO_DIVISIONS = [f"pub61{c}" for c in "ABCDEFGHIJKLM"]


def _post(url: str, query: dict, name: str, force: bool = False) -> dict:
    RAW_NORDIC.mkdir(parents=True, exist_ok=True)
    path = RAW_NORDIC / name
    if path.exists() and not force:
        return json.loads(path.read_text())
    resp = _request("POST", url, provider=name.split("_")[0], json_body=query, timeout=120)
    payload = resp.json()
    path.write_text(json.dumps(payload))
    _write_provenance(path, url, {"query": json.dumps(query)})
    return payload


def _jsonstat2(payload: dict) -> pd.DataFrame:
    """JSON-stat 2.0 dataset -> tidy frame (one column per dimension + value)."""
    ids, sizes = payload["id"], payload["size"]
    cats = []
    for d in ids:
        idx = payload["dimension"][d]["category"]["index"]
        order = sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx)
        cats.append(order)
    grid = pd.MultiIndex.from_product(cats, names=ids).to_frame(index=False)
    vals = payload["value"]
    if isinstance(vals, dict):
        full = [None] * int(np.prod(sizes))
        for k, v in vals.items():
            full[int(k)] = v
        vals = full
    grid["value"] = pd.to_numeric(pd.Series(vals), errors="coerce")
    return grid


def _labels(payload: dict, dim: str) -> dict:
    return payload["dimension"][dim]["category"]["label"]


def _quarter_index(codes: pd.Series) -> pd.DatetimeIndex:
    s = codes.astype(str).str.upper()
    y = s.str.slice(0, 4).astype(int)
    q = s.str.slice(5, 6).astype(int)
    return pd.to_datetime(dict(year=y, month=3 * q - 2, day=1))


# ---------------------------------------------------------------------------
# Sweden
# ---------------------------------------------------------------------------
def se_hce_panels(force: bool = False):
    """(nominal, volume, labels): 13 SA COICOP divisions, quarterly, SEK m."""
    query = {"query": [
        {"code": "Andamal", "selection": {"filter": "item", "values": SE_DIVISIONS}},
        {"code": "ContentsCode", "selection": {"filter": "item",
                                               "values": ["0000079O", "0000079L"]}},
    ], "response": {"format": "json-stat2"}}
    payload = _post(SCB_TABLE, query, "scb_hce_purpose_sa.json", force=force)
    df = _jsonstat2(payload)
    df["date"] = _quarter_index(df["Tid"])
    labels = {k: v.split(" ", 1)[-1].capitalize()
              for k, v in _labels(payload, "Andamal").items()}

    def wide(code):
        return (df[df["ContentsCode"] == code]
                .pivot_table(index="date", columns="Andamal", values="value")
                .reindex(columns=SE_DIVISIONS).sort_index())

    return wide("0000079O"), wide("0000079L"), labels


# ---------------------------------------------------------------------------
# Norway
# ---------------------------------------------------------------------------
def no_hce_panels(force: bool = False, sa_window: int = 40):
    """(nominal, volume, labels): 13 COICOP divisions, quarterly, NOK m.

    volume  = SSB constant-price series, seasonally adjusted (published);
    nominal = SA deflator x SA volume, the deflator being SSB's unadjusted
              current / constant ratio with a rolling quarter-dummy seasonal
              removed (see the module docstring).
    """
    from .trim_engine import deseasonalise

    query = {"query": [
        {"code": "UtgifterHushold", "selection": {"filter": "item", "values": NO_DIVISIONS}},
        {"code": "ContentsCode", "selection": {"filter": "item",
                                               "values": ["Priser", "FastePriser",
                                                          "FastePriserSesJust"]}},
    ], "response": {"format": "json-stat2"}}
    payload = _post(SSB_TABLE, query, "ssb_hce_purpose.json", force=force)
    df = _jsonstat2(payload)
    df["date"] = _quarter_index(df["Tid"])
    labels = _labels(payload, "UtgifterHushold")

    def wide(code):
        return (df[df["ContentsCode"] == code]
                .pivot_table(index="date", columns="UtgifterHushold", values="value")
                .reindex(columns=NO_DIVISIONS).sort_index())

    cur, const, vol_sa = wide("Priser"), wide("FastePriser"), wide("FastePriserSesJust")
    ok = (cur > 0) & (const > 0)
    log_defl = np.log((cur / const).where(ok))
    dlog = log_defl.diff()
    dlog_sa = deseasonalise(dlog, method="rolling", window=sa_window, periods_per_year=4)
    # re-chain the adjusted changes from the first observed level of each series
    log_sa = dlog_sa.fillna(0.0).cumsum() + log_defl.bfill().iloc[0]
    log_sa = log_sa.where(log_defl.notna())
    nominal = np.exp(log_sa) * vol_sa
    return nominal, vol_sa, labels
