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
    python scripts/fetch_statcan.py --only cpi --recent
                                               # what CI runs (see below)

    --only cpi|hce  restrict to the CPI cubes (18-10-0004 + 18-10-0007, the ca
                    gauge) or the quarterly HCE cube (36-10-0124, the ca_hce
                    decomposition scopes).
    --recent        refetch every OPEN-ENDED chunk (endDate blank: the latest
                    window of each batch and the weight vintages), fetch closed
                    historical windows only when missing. With the chunk
                    directory restored from the Actions cache this is ~15
                    requests for the CPI instead of ~51, and the result is
                    identical to a full pull: closed windows hold only history.

REACHABILITY. StatCan sits behind Cloudflare and, intermittently, answers
automated clients with a bot challenge (HTTP 403, "cf-mitigated: challenge",
a "Vérification de sécurité / Security Check" page) — on every endpoint,
including the official WDS API. 2026-11-16 a GitHub runner and the analysis
sandbox both got straight through; 2026-11-18 both were challenged. The
challenge is deliberate, so it is never worked around: this script stops at
the first 403 with exit code 3, and CI treats that as "Canada keeps its last
data" (the step is continue-on-error and annotates the run), never as a failed
refresh of the other gauges. When it persists, run this locally from a machine
StatCan lets through.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ism.datasources import ApiError, _request                        # noqa: E402
from ism.statcan import RAW_STATCAN, assemble_chunks, compact_db_csv  # noqa: E402

ONLY = {"cpi": {"chunks18100004", "chunks18100007"}, "hce": {"chunks36100124"}}

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
    recent = "--recent" in argv
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
        if only not in ONLY:
            raise SystemExit(f"--only takes one of {sorted(ONLY)}, not {only!r}")
    manifest = json.loads((RAW_STATCAN / "manifest.json").read_text())
    _prune_stale_chunks(manifest)
    if only:
        manifest = [m for m in manifest if m["file"].split("/")[0] in ONLY[only]]
    for i, item in enumerate(manifest, 1):
        dest = RAW_STATCAN / item["file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Skip a cached chunk only if it actually holds data rows; an
        # empty/header-only chunk (a query that returned nothing) is re-fetched
        # without needing --force. --recent always refetches open-ended chunks
        # (they are the ones a new release changes).
        open_ended = "endDate=&" in item["url"]
        if dest.exists() and not force and not (recent and open_ended) \
                and _chunk_has_data(dest):
            continue
        try:
            resp = _request("GET", item["url"], provider="StatCan", timeout=180)
        except ApiError as exc:
            if str(getattr(exc, "code", "")) == "403":
                challenged = "Security Check" in str(exc) or "cf-" in str(exc).lower()
                print(f"[statcan] HTTP 403 on {item['file']}"
                      + (" — StatCan's bot challenge (Cloudflare)." if challenged else ".")
                      + " Stopping; caches left as they were.", file=sys.stderr)
                sys.exit(3)
            raise
        df = compact_db_csv(resp.text)
        if len(df) > item["max_rows"]:
            raise RuntimeError(f"{item['file']}: {len(df)} rows > expected max "
                               f"{item['max_rows']} — endpoint layout changed?")
        df.to_csv(dest, index=False)
        print(f"[{i}/{len(manifest)}] {item['file']}: {len(df)} rows")
        time.sleep(1.0)                      # be polite
    for pid, out in ASSEMBLE:
        if only and f"chunks{pid}" not in ONLY[only]:
            continue
        assemble_chunks(pid, out)
    print("done — caches rebuilt.")


if __name__ == "__main__":
    main()
