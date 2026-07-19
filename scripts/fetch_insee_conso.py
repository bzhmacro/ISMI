"""
fetch_insee_conso.py
====================

Fetch + parse + validate INSEE's quarterly "Consommation des ménages — par
produit" Excel tables (t_conso_val.xls + t_conso_vol.xls), the ~40-product
backbone for the finer France decomposition port (`ism.insee.fr_hce_panels`,
level="detail"). The SDMX/BDM quarterly consumption is only A17 (~17 products);
this detailed panel lives in the Insee Résultats Excel release instead, so it
must be scraped. Run from a machine that can reach insee.fr, with `xlrd`
installed (`pip install xlrd`); this project's analysis sandbox blocks the host.

    python scripts/fetch_insee_conso.py                 # fetch + cache + validate
    python scripts/fetch_insee_conso.py --release 8958309
    python scripts/fetch_insee_conso.py --force         # re-download, ignore cache
    python scripts/fetch_insee_conso.py --diagnose      # dump raw sheet geometry

Find the latest release id on the "Consommation des ménages" Insee Résultats
landing page and pass it with --release (or bump ism.insee.CONSO_RELEASE). The
script prints how many products were parsed, the period span, a sample of the
product labels, and a nominal cross-check against the A17 total (the additive
sanity signal). If parsing finds nothing, --diagnose dumps the top-left grid so
the layout can be re-mapped.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from ism.insee import (InseeClient, CONSO_RELEASE, CONSO_FILES, CONSO_FILE_URL,  # noqa: E402
                       parse_conso_xls, fr_hce_panels_detail, validate_conso_vs_a17)
from ism.datasources import _request                                            # noqa: E402


def _diagnose(release: str, client: InseeClient) -> None:
    """Download the raw .xls files and print their top-left geometry."""
    import pandas as pd
    for valo, name in CONSO_FILES.items():
        url = CONSO_FILE_URL.format(release=release, name=name)
        print(f"\n=== {name} ({url}) ===")
        resp = _request("GET", url, provider="INSEE", timeout=180)
        raw = client.cache_dir / name
        raw.write_bytes(resp.content)
        sheets = pd.read_excel(raw, sheet_name=None, header=None, engine="xlrd")
        for sn, g in sheets.items():
            print(f"  sheet {sn!r}: shape {g.shape}")
            print(g.iloc[:12, :8].to_string(max_colwidth=22))


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    release = CONSO_RELEASE
    if "--release" in argv:
        release = argv[argv.index("--release") + 1]
    force = "--force" in argv
    client = InseeClient()

    if "--diagnose" in argv:
        _diagnose(release, client)
        return 0

    print(f"Fetching INSEE t_conso release {release} ...")
    df = client.conso_detail(force=force, release=release)
    n_products = df["product"].nunique()
    periods = sorted(df["period"].unique())
    labels = client.detail_labels()
    print(f"  parsed {n_products} products, {len(periods)} quarters "
          f"({periods[0]} .. {periods[-1]})")
    print("  sample products:")
    for code, lab in list(labels.items())[:12]:
        print(f"    {code:<38} {lab}")

    # build the panels (confirms both V and L align on the same products)
    nominal, volume, _ = fr_hce_panels_detail(client)
    print(f"  panels: nominal {nominal.shape}, volume {volume.shape}")

    # additive nominal cross-check against the A17 total
    try:
        rep = validate_conso_vs_a17(client)
        print("\n  cross-check Σ(detailed products) vs A17 total (nominal):")
        print("    " + rep.round(1).to_string().replace("\n", "\n    "))
        gap = rep["pct_gap"].abs().mean()
        print(f"  mean |gap| = {gap:.2f}%  "
              + ("OK (additive, small residual)" if gap < 5 else
                 "LARGE — inspect the parse (--diagnose) before trusting it"))
    except Exception as exc:
        print(f"  cross-check skipped ({type(exc).__name__}: {exc})")

    print(f"\nCached -> {client._detail_csv}")
    print("France decomposition will now use the ~40-product panel; rebuild with "
          "`python scripts/build_decomp.py --no-canada` and refresh the site with "
          "`python scripts/export_decomp_data.py fr`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
