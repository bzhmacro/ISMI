"""
build_decomp.py
===============

End-to-end build + validation for the supply/demand decomposition
(Shapiro 2022-18), the CLI sibling of scripts/build_and_validate.py (ISM).

    python scripts/build_decomp.py                 # headline + core, BEA (needs U20403)
    python scripts/build_decomp.py --proxy         # dev: quantity = nominal/price
    python scripts/build_decomp.py --no-validate   # skip the FRBSF comparison

Steps, for each scope (headline, core):
  1. build (log price, log quantity, inflation, weights) from BEA 2.4.3U/4U/5U
  2. compute the binary baseline (J=12, W=120) AND the precision variant
     (cut=0.1, matching the FRBSF published series)
  3. save the monthly + yoy contributions and the shares to data/processed/
  4. validate the contributions against the FRBSF published CSVs (corr/RMSE/MAE)

Run `python scripts/export_decomp_data.py` afterwards to refresh the web payload.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from ism.decomp_engine import DecompConfig, compute_decomp                    # noqa: E402
from ism.decomp_pipeline import build_decomp_panels, bea_wide, load_categories, core_exclusions  # noqa: E402
from ism.datasources import BeaClient, REPO_ROOT                              # noqa: E402
from ism.transforms import monthly_inflation                                 # noqa: E402
from ism.decomp_validate import validate_decomp                              # noqa: E402

PROC = REPO_ROOT / "data" / "processed"


def _panels(scope, proxy):
    if not proxy:
        p = build_decomp_panels(scope=scope, spec="levels", inflation_method="pct")
        return p.log_price, p.log_quantity, p.inflation, p.weights
    bea = BeaClient()
    price = bea_wide(bea, "U20404"); nominal = bea_wide(bea, "U20405")
    keys = [k for k in load_categories()["key"].astype(str)
            if k in price.columns and k in nominal.columns]
    if scope == "core":
        keys = [k for k in keys if k not in core_exclusions()]
    p = price[keys].astype(float); nom = nominal[keys].astype(float)
    q = nom / p
    w = nom.div(nom.sum(axis=1).replace(0, np.nan), axis=0)
    return np.log(p), np.log(q), monthly_inflation(p, method="pct"), w


def main(argv=None):
    argv = argv or sys.argv[1:]
    proxy = "--proxy" in argv
    do_validate = "--no-validate" not in argv

    PROC.mkdir(parents=True, exist_ok=True)
    for scope in ("headline", "core"):
        print(f"\n=== {scope.upper()} ===")
        try:
            logp, logq, infl, w = _panels(scope, proxy)
        except Exception as exc:
            print(f"  build failed: {type(exc).__name__}: {exc}")
            continue
        print(f"  {logp.shape[1]} categories, {logp.shape[0]} months"
              + (" (PROXY quantity)" if proxy else ""))

        for tag, cut in [("binary", 0.0), ("precision", 0.1)]:
            res = compute_decomp(logp, logq, infl, w,
                                 DecompConfig(var_lags=12, window=120, precision_cut=cut))
            res.contrib.to_csv(PROC / f"decomp_{scope}_{tag}_monthly.csv")
            res.contrib_yoy.to_csv(PROC / f"decomp_{scope}_{tag}_yoy.csv")
            res.shares.to_csv(PROC / f"decomp_{scope}_{tag}_shares.csv")
            print(f"  [{tag}] saved monthly/yoy/shares to data/processed/")

            if do_validate:
                rep = validate_decomp(res.contrib_yoy, scope=scope, kind="yoy")
                if rep is not None and len(rep):
                    print(f"  [{tag}] vs FRBSF (yoy):")
                    print(rep.to_string(index=False).replace("\n", "\n    "))

    print("\nDone. Refresh the website with: python scripts/export_decomp_data.py"
          + (" --proxy" if proxy else ""))


if __name__ == "__main__":
    main()
