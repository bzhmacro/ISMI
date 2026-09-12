"""
build_cpi_ri.py
===============

Pin the BLS December **relative importances** for the repo's CPI item strata
into ``config/cpi_ri_by_year.csv`` -- the anchor table behind the versioned CPI
weights (:mod:`ism.cpi_ri`).

Run it when BLS publishes a new December table (mid-January each year); the rest
of the pipeline then works offline from the committed CSV.

    python scripts/build_cpi_ri.py                 # 1997 -> latest available
    python scripts/build_cpi_ri.py --from 2020     # refresh recent years only
    python scripts/build_cpi_ri.py --force         # ignore the download cache

What it does
------------
1. Downloads each December table (per-year workbook from 2020, archive zip
   before that) and parses it into ``label -> relative importance``.
2. Joins on the exact labels pinned in ``config/cpi_categories.csv``, reports
   any stratum that failed to match, and renormalises each December to 100 over
   the pinned set.
3. Writes one column per December year.

Any year whose match rate falls below ``--min-match`` (default 100% of strata)
is reported loudly: a silently missing stratum reweights every other one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ism.cpi_ri import (  # noqa: E402
    FIRST_NEW_STRUCTURE_YEAR, RI_CSV, build_ri_by_year,
)
from ism.cpi_pipeline import load_cpi_categories  # noqa: E402
from ism.trim_pipeline import (  # noqa: E402
    CLEVELAND_RI_CSV, build_cleveland_ri, load_cleveland_components,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cut", choices=("strata", "cleveland", "both"),
                    default="both",
                    help="which cross-section to pin: the 70 item strata, the "
                         "45-component Cleveland cut, or both (default)")
    ap.add_argument("--from", dest="start", type=int,
                    default=FIRST_NEW_STRUCTURE_YEAR,
                    help=f"first December year (default {FIRST_NEW_STRUCTURE_YEAR})")
    ap.add_argument("--to", dest="end", type=int, default=None,
                    help="last December year (default: last completed year)")
    ap.add_argument("--force", action="store_true",
                    help="re-download instead of using the cached files")
    ap.add_argument("--min-match", type=float, default=1.0,
                    help="fraction of strata that must match (default 1.0)")
    ap.add_argument("--out", type=Path, default=RI_CSV)
    args = ap.parse_args()

    end = args.end or (dt.date.today().year - 1)
    if args.start < FIRST_NEW_STRUCTURE_YEAR:
        print(f"[build_cpi_ri] clamping start to {FIRST_NEW_STRUCTURE_YEAR} "
              "(the 1998 item-structure revision)")
        args.start = FIRST_NEW_STRUCTURE_YEAR

    years = list(range(args.start, end + 1))
    status = 0

    if args.cut in ("cleveland", "both"):
        comp = load_cleveland_components()
        print(f"[build_cpi_ri] Cleveland cut: {len(comp)} components x "
              f"{len(years)} Decembers")
        clev = build_cleveland_ri(comp, years, force=args.force)
        clev.reset_index().to_csv(CLEVELAND_RI_CSV, index=False,
                                  float_format="%.6f")
        print(f"[build_cpi_ri] wrote {CLEVELAND_RI_CSV} "
              f"({clev.shape[0]} components x {clev.shape[1]} Decembers)")
        if args.cut == "cleveland":
            return 0

    cats = load_cpi_categories()
    print(f"[build_cpi_ri] {len(cats)} strata x {len(years)} Decembers "
          f"({years[0]}-{years[-1]})")

    table = build_ri_by_year(cats, years, force=args.force)

    # Merge with anything already pinned so a partial refresh keeps old columns.
    if args.out.exists() and (args.start > FIRST_NEW_STRUCTURE_YEAR):
        old = pd.read_csv(args.out).set_index("key")
        old.columns = [int(c) for c in old.columns]
        table = old.drop(columns=[c for c in old.columns if c in table.columns],
                         errors="ignore").join(table, how="outer")
        table = table.sort_index(axis=1)

    bad = []
    for year in table.columns:
        rate = float(table[year].notna().mean())
        if rate < args.min_match:
            bad.append((year, rate))
    for year, rate in bad:
        print(f"[build_cpi_ri] WARNING {year}: only {rate:.0%} of strata matched")

    out = table.reset_index().rename(columns={"index": "key"})
    out.to_csv(args.out, index=False, float_format="%.6f")
    print(f"[build_cpi_ri] wrote {args.out} "
          f"({out.shape[0]} strata x {out.shape[1] - 1} Decembers)")

    # A quick eyeball of the drift the static vector was hiding.
    first, last = table.columns[0], table.columns[-1]
    delta = (table[last] - table[first]).sort_values()
    labels = cats.set_index("key")["label"]
    print(f"\nbiggest weight moves, Dec {first} -> Dec {last} (pp):")
    for key in list(delta.index[:5]) + list(delta.index[-5:]):
        print(f"  {labels.get(key, key):45s} {table.loc[key, first]:6.2f} -> "
              f"{table.loc[key, last]:6.2f}  ({delta[key]:+.2f})")
    return 1 if bad else status


if __name__ == "__main__":
    raise SystemExit(main())
