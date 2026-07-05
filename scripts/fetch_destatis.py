"""
fetch_destatis.py
=================

One-shot downloader for the German decomposition input: GENESIS table
**81000-0120** (quarterly household consumption by purpose, nominal +
price-adjusted, from 1991). Run this ON YOUR MACHINE -- the project sandbox
blocks www-genesis.destatis.de -- with a (free) GENESIS API token:

    export DESTATIS_API_TOKEN=<token from your GENESIS-Online account>
    python scripts/fetch_destatis.py [--force] [--table 81000-0120]

Steps:
  1. helloworld/logincheck  -> verifies the token and prints the API's answer
  2. data/tablefile         -> downloads the ffcsv flat file to
                               data/raw/destatis/<table>.ffcsv.csv (+ provenance)
  3. parses it defensively and prints what was found: frequency, price bases,
     purpose categories, date range.

If the table turns out to be ANNUAL-only it warns loudly: in that case the
recommended fallback is to keep Germany out of the quarterly decomposition
(the other countries build regardless).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Load .env so DESTATIS_API_TOKEN / DESTATIS_API_KEY are available without an
# explicit `export` (mirrors scripts/build_decomp.py).
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from ism.datasources import ApiError, FetchError            # noqa: E402
from ism.destatis import (DE_HCE_TABLE, DestatisClient,      # noqa: E402
                          de_hce_panels)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Destatis GENESIS table (ffcsv)")
    ap.add_argument("--table", default=DE_HCE_TABLE)
    ap.add_argument("--force", action="store_true",
                    help="re-download even if the cache exists")
    args = ap.parse_args()

    client = DestatisClient()

    # 1. token check ---------------------------------------------------------
    try:
        print("[destatis] logincheck:", client.logincheck())
    except (ApiError, FetchError) as e:
        print(f"[destatis] FAILED: {e}", file=sys.stderr)
        return 1

    # 2. download -------------------------------------------------------------
    try:
        path = client.tablefile(args.table, force=args.force)
    except (ApiError, FetchError) as e:
        print(f"[destatis] download FAILED: {e}", file=sys.stderr)
        return 1
    print(f"[destatis] ffcsv cached at {path} "
          f"({path.stat().st_size/1e6:.2f} MB)")

    # 3. parse + summarise -----------------------------------------------------
    tidy = client.table_tidy(args.table)
    n_q = int(tidy["date"].notna().sum())
    measures = sorted(tidy["measure"].astype(str).unique())
    print(f"[destatis] rows: {len(tidy)} | quarterly rows: {n_q}")
    print(f"[destatis] measures: {measures}")

    if n_q == 0:
        print("\n" + "!" * 78)
        print("!! WARNING: no quarterly observations found -- the table looks")
        print("!! ANNUAL-only. A 40-quarter rolling VAR cannot be estimated on")
        print("!! annual data: keep Germany OUT of the quarterly decomposition")
        print("!! (ism.decomp_ports.build_de_panels will refuse to build).")
        print("!" * 78)
        return 2

    try:
        nominal, volume, labels = de_hce_panels(client)
    except ApiError as e:
        print(f"[destatis] panel build FAILED: {e}", file=sys.stderr)
        return 1
    i0, i1 = nominal.index[0], nominal.index[-1]
    print(f"[destatis] quarterly panel: {nominal.shape[1]} purposes, "
          f"{len(nominal)} quarters, {i0.year}Q{i0.quarter} -> "
          f"{i1.year}Q{i1.quarter}")
    for code, lab in labels.items():
        print(f"    {code}: {lab}")
    print("[destatis] done. build_de_panels() is now cache-first and offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
