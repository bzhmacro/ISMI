"""
export_web_data.py  (TEMPLATE)
==============================

Write web/data/<name>.json: the *raw* (panel, weights) for every backbone, the
author overlay, any headline context series, and ONE precomputed baseline combo
for instant first paint. The site recomputes everything else live (see
references/web-port.md). Keep this self-fetching so a scheduled CI job needs no
committed data.

Run from the repo root after the pipeline is built:
    python scripts/export_web_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pkg.engine import Config, compute
# from pkg.pipeline import build_panel        # -> (panel, weights) for a backbone
# from pkg.datasources import load_sources

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "web" / "data" / "index.json"
SCHEMA = 3


def _ser(s: pd.Series) -> dict:
    """Serialise a monthly Series as {dates: [...], values: [...]} (NaN -> null)."""
    return {
        "dates": [d.strftime("%Y-%m") for d in s.index],
        "values": [None if pd.isna(v) else float(v) for v in s.values],
    }


def _panel(df: pd.DataFrame) -> dict:
    """Serialise a months x units panel as columns of values + a shared date axis."""
    return {
        "dates": [d.strftime("%Y-%m") for d in df.index],
        "units": list(map(str, df.columns)),
        "values": [[None if pd.isna(v) else float(v) for v in df[c].values]
                   for c in df.columns],
    }


def main():
    backbones = {}
    # for name in ("pce", "cpi"):
    #     panel, weights = build_panel(name)
    #     backbones[name] = {"inflation": _panel(panel), "weights": _panel(weights)}

    # One precomputed baseline combo for instant first paint.
    baseline = {}
    # panel, weights = build_panel("pce")
    # res = compute(panel, weights, Config())          # paper baseline
    # baseline = {"pce": {"Index": _ser(res["Index"]),
    #                     "S_pos": _ser(res["S_pos"]),
    #                     "S_neg": _ser(res["S_neg"])}}

    author = {}      # _ser(load_author_index())  -- the ground-truth overlay
    headline = {}    # _ser(load_headline_yoy())  -- context series

    payload = {
        "schema": SCHEMA,
        "generated_utc": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_through": "YYYY-MM",
        "backbones": backbones,
        "baseline": baseline,
        "author": author,
        "headline": headline,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload))
    print(f"wrote {OUT} (schema v{SCHEMA})")


if __name__ == "__main__":
    main()
