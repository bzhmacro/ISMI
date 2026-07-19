"""
build_decomp.py
===============

End-to-end build + validation for the supply/demand decomposition
(Shapiro 2022-18), the CLI sibling of scripts/build_and_validate.py (ISM).

    python scripts/build_decomp.py                 # US headline+core + Canada + UK/FR/DE
    python scripts/build_decomp.py --proxy         # dev: US quantity = nominal/price
    python scripts/build_decomp.py --no-validate   # skip the FRBSF/BoC/sanity comparisons
    python scripts/build_decomp.py --no-gs         # skip the US goods/services split
    python scripts/build_decomp.py --no-canada     # skip the Canada scopes
    python scripts/build_decomp.py --no-ports      # skip the UK/France/Germany ports

Steps, for each US scope (headline, core):
  1. build (log price, log quantity, inflation, weights) from BEA 2.4.3U/4U/5U
  2. compute the binary baseline (J=12, W=120) AND the precision variant
     (cut=0.1, matching the FRBSF published series)
  3. save the monthly + yoy contributions and the shares to data/processed/
  4. validate the contributions against the FRBSF published CSVs (corr/RMSE/MAE)

Then, for Canada (Bank of Canada SAP 2026-33; total/goods/services):
  1. build from StatCan 36-10-0124 quarterly HCE (needs data/raw/statcan/ caches;
     rebuild with `python scripts/fetch_statcan.py`)
  2. compute the BoC baseline (J=4, W=40, quarterly)
  3. save contributions/shares to data/processed/
  4. validate against the paper's stated facts (peak ~6% 2022, supply > demand)

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
from ism.decomp_validate import (validate_decomp, validate_ca_decomp,        # noqa: E402
                                 sanity_quarterly_decomp)
from ism.decomp_ports import build_ca_panels, QUARTERLY_BASELINE             # noqa: E402

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
    elif scope in ("goods", "services"):
        from ism.decomp_pipeline import goods_services_keys
        gs = set(goods_services_keys(scope))
        keys = [k for k in keys if k in gs]
    p = price[keys].astype(float); nom = nominal[keys].astype(float)
    q = nom / p
    w = nom.div(nom.sum(axis=1).replace(0, np.nan), axis=0)
    return np.log(p), np.log(q), monthly_inflation(p, method="pct"), w


def main(argv=None):
    argv = argv or sys.argv[1:]
    proxy = "--proxy" in argv
    do_validate = "--no-validate" not in argv
    do_gs = "--no-gs" not in argv                # US goods/services split
    do_canada = "--no-canada" not in argv
    do_ports = "--no-ports" not in argv          # UK / France / Germany

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

    if do_gs:
        # US goods/services split (BEA table 2.4.5U aggregate: line < 150 = goods,
        # line >= 150 = services). Same monthly baseline as headline/core; FRBSF
        # publishes no goods/services overlay, so validation is internal coherence.
        for scope in ("goods", "services"):
            print(f"\n=== US ({scope.upper()}) ===")
            try:
                logp, logq, infl, w = _panels(scope, proxy)
            except Exception as exc:
                print(f"  build failed: {type(exc).__name__}: {exc}")
                continue
            print(f"  {logp.shape[1]} categories, {logp.shape[0]} months"
                  + (" (PROXY quantity)" if proxy else ""))
            res = compute_decomp(logp, logq, infl, w,
                                 DecompConfig(var_lags=12, window=120, precision_cut=0.0))
            res.contrib.to_csv(PROC / f"decomp_{scope}_binary_monthly.csv")
            res.contrib_yoy.to_csv(PROC / f"decomp_{scope}_binary_yoy.csv")
            res.shares.to_csv(PROC / f"decomp_{scope}_binary_shares.csv")
            print("  [binary] saved monthly/yoy/shares to data/processed/")
            if do_validate:
                rep = sanity_quarterly_decomp(res.contrib, res.contrib_yoy)
                print("  internal-coherence sanity:")
                print("    " + rep.to_string(index=False).replace("\n", "\n    "))

    if do_canada:
        for ca_scope in ("total", "goods", "services"):
            print(f"\n=== CANADA ({ca_scope.upper()}) ===")
            try:
                panels = build_ca_panels(scope=ca_scope, spec="levels")
            except Exception as exc:
                print(f"  build failed: {type(exc).__name__}: {exc}")
                print("  (needs data/raw/statcan/ caches — run scripts/fetch_statcan.py)")
                continue
            res = compute_decomp(panels.log_price, panels.log_quantity,
                                 panels.inflation, panels.weights, QUARTERLY_BASELINE)
            tag = f"ca_{ca_scope}"
            res.contrib.to_csv(PROC / f"decomp_{tag}_binary_qoq.csv")
            res.contrib_yoy.to_csv(PROC / f"decomp_{tag}_binary_yoy.csv")
            res.shares.to_csv(PROC / f"decomp_{tag}_binary_shares.csv")
            print(f"  [binary] saved qoq/yoy/shares to data/processed/")
            if do_validate and ca_scope == "total":
                rep = validate_ca_decomp(res.contrib_yoy)
                print("  vs Bank of Canada SAP 2026-33 (stated facts):")
                print("    " + rep.to_string(index=False).replace("\n", "\n    "))

    if do_ports:
        from ism.decomp_ports import PORTS
        for code in ("uk", "fr", "de", "jp"):
            print(f"\n=== {code.upper()} (quarterly national-accounts port) ===")
            try:
                panels = PORTS[code](spec="levels")
            except Exception as exc:
                need = {"de": "; Germany uses Eurostat namq_10_fcs — check network)",
                        "jp": "; Japan needs a free ESTAT_API_ID in .env)"}.get(code, ")")
                print(f"  build failed: {type(exc).__name__}: {exc}")
                print(f"  (needs the {code} data cache — see config/sources_*.yaml{need}")
                continue
            res = compute_decomp(panels.log_price, panels.log_quantity,
                                 panels.inflation, panels.weights, QUARTERLY_BASELINE)
            res.contrib.to_csv(PROC / f"decomp_{code}_binary_qoq.csv")
            res.contrib_yoy.to_csv(PROC / f"decomp_{code}_binary_yoy.csv")
            res.shares.to_csv(PROC / f"decomp_{code}_binary_shares.csv")
            if do_validate:
                rep = sanity_quarterly_decomp(res.contrib, res.contrib_yoy)
                print(f"  {len(panels.categories)} cats, "
                      f"{panels.log_price.index[0].year}Q{panels.log_price.index[0].quarter}"
                      f"–{panels.log_price.index[-1].year}Q{panels.log_price.index[-1].quarter} — sanity:")
                print("    " + rep.to_string(index=False).replace("\n", "\n    "))
            else:
                print("  [binary] saved qoq/yoy/shares to data/processed/")

    print("\nDone. Refresh the website with: python scripts/export_decomp_data.py"
          + (" --proxy" if proxy else ""))


if __name__ == "__main__":
    main()
