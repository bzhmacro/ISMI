"""
fetch_statcan.py
================

Full local refresh of the Canadian data caches (run this on YOUR machine —
www150.statcan.gc.ca is blocked from the hosted analysis sandbox, so the
repo ships assembled caches; this script rebuilds them from source).

For each cube it walks data/raw/statcan/manifest.json (generated from the
pinned category sets in config/ca_hce_categories.csv and
config/ca_cpi_categories.csv), pulls every chunk through the db-loading CSV
endpoint, compacts to (REF_DATE, COORDINATE, VALUE), then assembles the three
caches the clients read:

    data/raw/statcan/36100124_ca_sa.csv    (decomp: quarterly HCE, SA, 2 bases)
    data/raw/statcan/18100004_ca.csv       (ISM: monthly CPI leaves + All-items)
    data/raw/statcan/18100007_ca.csv       (ISM: basket weights by vintage)

    python scripts/fetch_statcan.py            # everything missing
    python scripts/fetch_statcan.py --force    # refetch all chunks
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ism.datasources import _request                                  # noqa: E402
from ism.statcan import RAW_STATCAN, assemble_chunks, compact_db_csv  # noqa: E402

ASSEMBLE = [
    ("36100124", "36100124_ca_sa.csv"),
    ("18100004", "18100004_ca.csv"),
    ("18100007", "18100007_ca.csv"),
]


def _prune_stale_chunks(manifest):
    """Delete any chunk files NOT listed in the manifest.

    assemble_chunks() globs chunks<pid>/*.csv, so a stray file from an earlier
    fetch attempt (different member batching / naming) would silently pollute the
    assembled cache. Keep only the manifest's expected filenames per chunk dir.
    """
    expected = {}
    for item in manifest:
        p = RAW_STATCAN / item["file"]
        expected.setdefault(p.parent, set()).add(p.name)
    for chunk_dir, names in expected.items():
        if not chunk_dir.exists():
            continue
        for f in chunk_dir.glob("*.csv"):
            if f.name not in names:
                print(f"[prune] removing stale chunk {f.relative_to(RAW_STATCAN)}")
                f.unlink()


def _chunk_has_data(path) -> bool:
    """True if a cached chunk CSV has at least one data row beyond the header."""
    try:
        with open(path, encoding="utf-8") as f:
            f.readline()                       # header
            return any(line.strip() for line in f)
    except OSError:
        return False


def main(argv=None):
    argv = argv or sys.argv[1:]
    force = "--force" in argv
    manifest = json.loads((RAW_STATCAN / "manifest.json").read_text())
    _prune_stale_chunks(manifest)
    for i, item in enumerate(manifest, 1):
        dest = RAW_STATCAN / item["file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Skip a cached chunk only if it actually holds data rows; an
        # empty/header-only chunk (a query that returned nothing) is re-fetched
        # without needing --force.
        if dest.exists() and not force and _chunk_has_data(dest):
            continue
        resp = _request("GET", item["url"], provider="StatCan", timeout=180)
        df = compact_db_csv(resp.text)
        if len(df) > item["max_rows"]:
            raise RuntimeError(f"{item['file']}: {len(df)} rows > expected max "
                               f"{item['max_rows']} — endpoint layout changed?")
        df.to_csv(dest, index=False)
        print(f"[{i}/{len(manifest)}] {item['file']}: {len(df)} rows")
        time.sleep(1.0)                      # be polite
    for pid, out in ASSEMBLE:
        assemble_chunks(pid, out)
    print("done — caches rebuilt.")


if __name__ == "__main__":
    main()
