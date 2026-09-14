#!/usr/bin/env python3
"""Build the wage model: fetch, assemble, estimate, validate, save.

    python scripts/build_wage.py                # build everything
    python scripts/build_wage.py --countries US UK
    python scripts/build_wage.py --force        # ignore the raw-data cache
    python scripts/build_wage.py --no-effective-mw   # skip the 102 state pulls

Writes:
    data/wage/panel_<CC>.csv     one quarterly panel per country
    data/wage/fits.json          estimated coefficients (panel + per country)
    data/wage/validation.txt     the check report

Run ``scripts/export_wage_data.py`` afterwards to refresh the website payload.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import pandas as pd  # noqa: E402

from ism.wage_engine import (WageConfig, fit_panel_wage_equation,  # noqa: E402
                             fit_price_equation, fit_wage_equation,
                             price_to_wage_gain, spiral_gain, wage_to_price_gain)
from ism.wage_pipeline import ALL_COUNTRIES, build_panel  # noqa: E402
from ism.wage_validate import estimation_samples, report, validate_all  # noqa: E402

OUT = REPO / "data" / "wage"


def fit_to_dict(fit) -> dict:
    return {
        "names": fit.names,
        "beta": [float(b) for b in fit.beta],
        "se": [float(s) for s in fit.se],
        "r2": float(fit.r2),
        "nobs": int(fit.nobs),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", nargs="*", default=list(ALL_COUNTRIES))
    ap.add_argument("--force", action="store_true", help="ignore the raw cache")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if args.quiet:
        warnings.filterwarnings("ignore")

    OUT.mkdir(parents=True, exist_ok=True)
    cfg = WageConfig()

    panels = {}
    for c in args.countries:
        print(f"building {c} ...", flush=True)
        panels[c] = build_panel(c, cfg, force=args.force)
        panels[c].to_csv(OUT / f"panel_{c}.csv")

    print("estimating ...", flush=True)
    panel_fit = fit_panel_wage_equation(panels, cfg)
    fits = {"panel_wage": fit_to_dict(panel_fit),
            "panel_wage_nolambda": fit_to_dict(
                fit_panel_wage_equation(panels, cfg, interact=False)),
            "countries": {}}
    for c, d in panels.items():
        entry = {}
        try:
            entry["wage"] = fit_to_dict(fit_wage_equation(d, cfg, interact=False))
        except Exception as exc:  # noqa: BLE001
            entry["wage_error"] = str(exc)
        try:
            pf = fit_price_equation(d, cfg)
            entry["price"] = fit_to_dict(pf)
            entry["M"] = float(wage_to_price_gain(pf))
            g = spiral_gain(panel_fit, pf, d["lambda"].dropna())
            entry["G_latest"] = float(g["G"].iloc[-1])
            entry["lambda_latest"] = float(g["lambda"].iloc[-1])
            # lambda and G must be read at the SAME date, or the published
            # table does not reproduce as Lambda(lambda) x M. Both are the
            # calendar-year mean.
            win = g.loc["1975-01-01":"1975-12-31"]
            entry["G_1975"] = float(win["G"].mean()) if len(win) else None
            entry["lambda_1975"] = float(win["lambda"].mean()) if len(win) else None
        except Exception as exc:  # noqa: BLE001
            entry["price_error"] = str(exc)
        fits["countries"][c] = entry

    fits["Lambda_curve"] = {str(round(x, 2)): float(price_to_wage_gain(panel_fit, x))
                            for x in [i / 20 for i in range(21)]}
    (OUT / "fits.json").write_text(json.dumps(fits, indent=2))

    samples = estimation_samples(panels, cfg)
    samples.to_csv(OUT / "estimation_samples.csv")
    print(samples.to_string(), flush=True)

    print("validating ...", flush=True)
    txt = report(validate_all(panels, cfg=cfg))
    (OUT / "validation.txt").write_text(txt)
    print(txt)
    return 0 if "FAIL" not in txt else 1


if __name__ == "__main__":
    raise SystemExit(main())
