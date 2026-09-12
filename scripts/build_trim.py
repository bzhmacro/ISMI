"""
build_trim.py
=============

Build the trimmed-mean / median inflation measures for every scope and validate
them against the published Cleveland Fed and Dallas Fed series.

    python scripts/build_trim.py                  # all scopes, validate, save
    python scripts/build_trim.py cpi45            # one scope
    python scripts/build_trim.py --cross-section  # also print the latest
                                                  # cross-section vs the bank's
    python scripts/build_trim.py --optimal-trim   # re-derive the trim points

Scopes
------
``cpi45``  the Cleveland Fed cut (45 components, regional OER split)
``cpi70``  the repo's 70 CPI item strata
``pce``    BEA PCE underlying detail (the Dallas Fed's gauge)
``uk`` ``fr`` ``de`` ``jp`` ``ca``  gauges reused from ``web/data/ism.json``

``pce`` and the country scopes read their panels from the committed
``web/data/ism.json`` when BEA is not reachable (``--from-web-data``, the
default when the BEA key is absent), so the whole model rebuilds offline from
what is already in the repo.

Outputs land in ``outputs/trim/`` as CSV: one file per scope with the rate,
the chained index, the 12-month rate and the category count, plus a
``validation.csv`` holding the comparison table.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from ism.trim_engine import (MEDIAN_CPI, TRIM16_CPI, TRIM_PCE,  # noqa: E402
                             TrimConfig, centred_moving_average, compute_trim,
                             optimal_trim)
from ism.trim_pipeline import (build_cleveland_panel, build_cpi70_panel,  # noqa: E402
                               build_pce_panel, panel_from_web_data)
from ism.trim_validate import (compare_latest_cross_section,  # noqa: E402
                               compare_to_official, official_series, summarise)

WEB_DATA = ROOT / "web" / "data" / "ism.json"
OUT_DIR = ROOT / "outputs" / "trim"

MEASURES = {"median": MEDIAN_CPI, "trim16": TRIM16_CPI, "trim_pce": TRIM_PCE}
WEB_SCOPES = ("uk", "fr", "de", "jp", "ca")


def load_web_payload() -> dict:
    if not WEB_DATA.exists():
        raise SystemExit(f"{WEB_DATA} not found; run scripts/export_web_data.py first")
    return json.loads(WEB_DATA.read_text())


def build_scope(scope: str, from_web_data: bool, force: bool = False):
    """Return the :class:`~ism.trim_pipeline.TrimPanel` for one scope."""
    if scope == "cpi45":
        return build_cleveland_panel(force=force)
    if scope == "cpi70":
        return build_cpi70_panel(force=force)
    if scope == "pce":
        if from_web_data:
            return _pce_from_web()
        return build_pce_panel(force=force)
    if scope in WEB_SCOPES:
        return panel_from_web_data(load_web_payload(), scope)
    raise SystemExit(f"unknown scope {scope!r}")


def _pce_from_web():
    """PCE panels taken from the committed website payload.

    The site already ships exactly the BEA 2.4.4U/2.4.5U-derived panels the
    trimmed mean needs, so this path rebuilds the Dallas-style measure with no
    BEA key and no network at all.
    """
    panel = panel_from_web_data(load_web_payload(), "pce", sa="none")
    return build_pce_panel(inflation_panel=panel.inflation, weights=panel.weights,
                           labels=panel.labels)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scopes", nargs="*",
                    default=["cpi45", "cpi70", "pce"],
                    help="scopes to build (default: cpi45 cpi70 pce)")
    ap.add_argument("--from-web-data", action="store_true",
                    help="build PCE from web/data/ism.json instead of BEA")
    ap.add_argument("--force", action="store_true", help="bypass download caches")
    ap.add_argument("--cross-section", action="store_true",
                    help="print the latest cross-section against the bank's own")
    ap.add_argument("--optimal-trim", action="store_true",
                    help="re-derive the trim points against a centred 36-month MA")
    ap.add_argument("--start", default="1998-01-01",
                    help="first month scored in the validation (default 1998-01)")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    from_web = args.from_web_data or not os.environ.get("BEA_API_KEY")
    if from_web and "pce" in args.scopes:
        print("[build_trim] PCE panels: web/data/ism.json "
              "(no BEA_API_KEY set)" if not args.from_web_data else
              "[build_trim] PCE panels: web/data/ism.json (--from-web-data)")

    args.out.mkdir(parents=True, exist_ok=True)
    official = official_series(force=args.force)
    reports = []

    for scope in args.scopes:
        panel = build_scope(scope, from_web, force=args.force)
        print(f"\n=== {scope}: {panel.label}")
        print(f"    {panel.n_categories} categories, "
              f"{panel.inflation.index[0]:%Y-%m} to {panel.inflation.index[-1]:%Y-%m}")
        print(f"    prices : {panel.source_note}")
        print(f"    weights: {panel.weight_note}")
        for note in panel.notes:
            print(f"    note   : {note}")

        frames = {}
        for name, base in MEASURES.items():
            cfg = TrimConfig(lower=base.lower, upper=base.upper, sa=panel.sa,
                             periods_per_year=panel.periods_per_year)
            res = compute_trim(panel.inflation, panel.weights, cfg)
            frames[name] = res.to_frame().add_prefix(f"{name}_")
            last = res.yoy.dropna()
            if len(last):
                print(f"    {name:9s} latest {last.index[-1]:%Y-%m}: "
                      f"{res.rate.dropna().iloc[-1]:6.2f}% 1m ann, "
                      f"{last.iloc[-1]:5.2f}% 12m")
        pd.concat(frames.values(), axis=1).to_csv(args.out / f"{scope}.csv")

        rep = compare_to_official(panel, MEASURES, official, start=args.start)
        if not rep.empty:
            print("\n    vs published:")
            print(rep.to_string(index=False,
                                float_format=lambda v: f"{v:7.3f}"))
            reports.append(rep)
        else:
            print("    (no published counterpart for this scope)")

        if args.cross_section and scope in ("cpi45", "cpi70", "pce"):
            bank = "dallas" if scope == "pce" else "cleveland"
            xs = compare_latest_cross_section(panel, bank=bank, force=args.force)
            if not xs.empty:
                print(f"\n    latest cross-section vs {bank} "
                      f"({xs.attrs.get('month', '')}), 12 largest weights:")
                print(xs.head(12).to_string(index=False,
                                            float_format=lambda v: f"{v:8.2f}"))
                xs.to_csv(args.out / f"{scope}_cross_section.csv", index=False)

        if args.optimal_trim:
            _report_optimal_trim(panel, args.out)

    summary = summarise(reports)
    if not summary.empty:
        summary.to_csv(args.out / "validation.csv", index=False)
        print(f"\n[build_trim] wrote {args.out}/validation.csv")
    return 0


def _report_optimal_trim(panel, out_dir: Path) -> None:
    """Re-derive the trim points the way the Reserve Banks chose theirs."""
    headline = (panel.weights * panel.inflation).sum(axis=1, min_count=1)
    headline_ann = 100.0 * ((1.0 + headline / 100.0) ** panel.periods_per_year - 1.0)
    reference = centred_moving_average(headline_ann, 36)
    grid = [round(x, 2) for x in [i / 100 for i in range(0, 51, 2)]]
    print("\n    re-deriving the trim points against a centred 36-month MA "
          f"of headline ({len(grid)}x{len(grid)} grid)...")
    scores = optimal_trim(panel.inflation, panel.weights, reference,
                          lower_grid=grid, upper_grid=grid,
                          cfg=TrimConfig(sa=panel.sa,
                                         periods_per_year=panel.periods_per_year))
    scores.to_csv(out_dir / f"{panel.key}_trim_grid.csv", index=False)
    print(scores.head(5).to_string(index=False,
                                   float_format=lambda v: f"{v:8.3f}"))


if __name__ == "__main__":
    raise SystemExit(main())
