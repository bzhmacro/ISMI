#!/usr/bin/env python3
"""Export the wage model's payload for the website: web/data/wage.json.

The site recomputes the model in the browser rather than plotting stored
results, so what ships is *inputs*, not outputs: the country panels, the
coverage database, the income shares, the scheme and wedge tables, and the
Python-estimated coefficients that the browser twin has to reproduce. The one
exception is the panel wage equation, which is shipped fitted as well as
refittable, so the page has something to draw before the worker has run.

    python scripts/export_wage_data.py
    python scripts/export_wage_data.py --check    # verify an existing payload
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ism.wage_engine import (WageConfig, fit_panel_wage_equation,  # noqa: E402
                             fit_price_equation, wage_to_price_gain)

DATA = REPO / "data" / "wage"
OUT = REPO / "web" / "data" / "wage.json"

# Series the page plots or recomputes from. Everything else in the panel is
# working state and is left on disk: the payload is downloaded by every visitor.
SERIES = [
    "gw", "gp", "gp_core", "gw_q", "gp_q", "grpe", "grpf", "slack", "slack_vu",
    "gpty", "dmw", "h", "h_disc", "catchup", "catchup_bb", "pistar", "pigap",
    "lambda", "wedge", "scheme", "real_wage", "transfer_share",
    "lvl_wage", "lvl_minwage", "lvl_benefit", "lvl_handout", "lvl_price",
    "cov_automatic", "cov_public", "cov_minwage", "cov_benchmark",
    "populist", "election",
]

COUNTRY_META = {
    "US": {"name": "United States", "modelled": True, "currency": "USD"},
    "UK": {"name": "United Kingdom", "modelled": True, "currency": "GBP"},
    "FR": {"name": "France", "modelled": True, "currency": "EUR"},
    "DE": {"name": "Germany", "modelled": True, "currency": "EUR"},
    "BE": {"name": "Belgium", "modelled": False, "currency": "EUR"},
    "IT": {"name": "Italy", "modelled": False, "currency": "EUR"},
    "ES": {"name": "Spain", "modelled": False, "currency": "EUR"},
}


def records(df: pd.DataFrame) -> list:
    """A config table as JSON records, with NaN turned into null.

    ``DataFrame.to_dict(orient="records")`` keeps NaN, and ``json.dumps`` then
    writes the bare token ``NaN`` -- which Python's own loader accepts and every
    browser's ``JSON.parse`` rejects. The payload looked fine from Python and
    broke the page. Hence this.
    """
    return df.astype(object).where(pd.notna(df), None).to_dict(orient="records")


def clean(values) -> list:
    """NaN and infinity are not JSON. Round to 6dp: the payload is downloaded by
    every visitor and the sixth decimal of an annualised percentage is noise."""
    out = []
    for v in values:
        f = float(v)
        out.append(None if not math.isfinite(f) else round(f, 6))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        payload = json.loads(OUT.read_text())
        n = len(payload["countries"])
        pts = sum(len(c["dates"]) for c in payload["countries"].values())
        print(f"{OUT}: {n} countries, {pts} quarters, "
              f"{OUT.stat().st_size / 1024:.0f} KB")
        return 0

    panels = {}
    for p in sorted(DATA.glob("panel_*.csv")):
        code = p.stem.split("_")[1]
        panels[code] = pd.read_csv(p, index_col=0, parse_dates=True)
    if not panels:
        print("no panels found; run scripts/build_wage.py first", file=sys.stderr)
        return 1

    cfg = WageConfig()
    panel_fit = fit_panel_wage_equation(panels, cfg)          # partially pooled
    pooled_fit = fit_panel_wage_equation(panels, cfg, free=())  # for comparison

    countries = {}
    for code, d in panels.items():
        entry = {
            "code": code,
            **COUNTRY_META.get(code, {"name": code, "modelled": False}),
            "dates": [ts.strftime("%Y-%m-%d") for ts in d.index],
            "series": {},
        }
        for col in SERIES:
            if col in d.columns:
                entry["series"][col] = clean(d[col].to_numpy())
        try:
            pf = fit_price_equation(d, cfg)
            entry["price_fit"] = {"names": pf.names,
                                  "beta": clean(pf.beta),
                                  "se": clean(pf.se),
                                  "r2": round(float(pf.r2), 6),
                                  "nobs": int(pf.nobs)}
            entry["M"] = round(float(wage_to_price_gain(pf)), 6)
        except Exception as exc:  # noqa: BLE001
            entry["price_error"] = str(exc)
        countries[code] = entry

    shares = pd.read_csv(REPO / "config" / "wage_income_shares.csv", comment="#")
    schemes = pd.read_csv(REPO / "config" / "wage_schemes.csv", comment="#")
    coverage = pd.read_csv(REPO / "config" / "indexation_coverage.csv", comment="#")
    uprating = pd.read_csv(REPO / "config" / "wage_uprating.csv", comment="#")
    wedge = pd.read_csv(REPO / "config" / "wage_cpi_wedge.csv", comment="#")

    payload = {
        "meta": {
            "model": "wage",
            "title": "Wages, indexation and the spiral gain",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "frequency": "quarterly",
            "base_period": "2019-Q4",
            "config": {"lags": cfg.lags, "anchor_q": cfg.anchor_q,
                       "homogeneity": cfg.homogeneity,
                       "elasticities": cfg.elasticities,
                       "window": cfg.window},
            "notes": (
                "Growth rates are four-quarter log changes in percent. The "
                "catch-up term is the negative of the deviation of the log real "
                "wage from its one-sided local linear trend. lambda is built "
                "from config/indexation_coverage.csv. Countries flagged "
                "modelled=false are reference cases that identify the lambda "
                "interaction but are not the paper's subject."
            ),
        },
        "panel_fit": {"names": panel_fit.names, "beta": clean(panel_fit.beta),
                      "se": clean(panel_fit.se), "r2": round(float(panel_fit.r2), 6),
                      "nobs": int(panel_fit.nobs),
                      "free": ["gw", "pistar", "slack"]},
        "panel_fit_pooled": {"names": pooled_fit.names, "beta": clean(pooled_fit.beta),
                             "se": clean(pooled_fit.se),
                             "r2": round(float(pooled_fit.r2), 6),
                             "nobs": int(pooled_fit.nobs), "free": []},
        "countries": countries,
        "shares": records(shares),
        "schemes": records(schemes),
        "coverage": records(coverage),
        "uprating": records(uprating),
        "wedge": records(wedge),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False turns a silent NaN into a build failure rather than a
    # payload that only breaks in the browser.
    OUT.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False))
    pts = sum(len(c["dates"]) for c in countries.values())
    print(f"wrote {OUT} — {len(countries)} countries, {pts} quarters, "
          f"{OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
