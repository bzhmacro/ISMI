"""
build_statcan_manifest.py
=========================

Regenerate data/raw/statcan/manifest.json -- the chunked download plan that
scripts/fetch_statcan.py replays to rebuild the Canadian caches -- from the
pinned category sets in config/ca_hce_categories.csv and
config/ca_cpi_categories.csv.

The manifest is the ONE StatCan artifact that is committed (see .gitignore); the
bulky assembled caches under data/raw/statcan/ are rebuilt from it. Because it is
derived purely from config (no network), it is deterministic and safe to
regenerate in CI before the fetch step. Whenever the Canadian category sets
change, rerun this and commit the new manifest.

For each cube it emits one download entry per (price-basis x date-window x member
batch), batching members so every URL stays under the StatCan ~255-char limit:

    36-10-0124  HCE quarterly     dims [[1],[base],[1],MEMBERS], base in {1,2}
    18-10-0004  CPI monthly       dims [[2],MEMBERS]  (MEMBERS incl. 2 = All-items)
    18-10-0007  CPI basket weights dims [[1],MEMBERS,[1],[1]]

Each entry is {"file", "url", "max_rows"}; max_rows is a generous per-chunk row
ceiling so fetch_statcan.py can still detect a gross endpoint-layout change.

    python scripts/build_statcan_manifest.py            # writes manifest.json
    python scripts/build_statcan_manifest.py --check    # verify only, no write
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ism.statcan import (  # noqa: E402
    HCE_BASE_NOMINAL, HCE_BASE_REAL, PID_CPI, PID_CPI_W, PID_HCE,
    RAW_STATCAN, db_loading_url, load_ca_cpi_categories, load_ca_hce_categories,
)

URL_MAX = 250          # stay safely under StatCan's ~255-char cap
OPEN_END_YEAR = 2027   # treat an open-ended window as running to here for sizing

# Historical date windows per cube (as in the shipped manifest). Each cube's
# series is split by era so no single member/window CSV grows unbounded.
WINDOWS = {
    PID_HCE:   [("19750101", "19891231"), ("19900101", "20041231"),
                ("20050101", "20191231"), ("20200101", "")],
    PID_CPI:   [("19760101", "19881231"), ("19890101", "20011231"),
                ("20020101", "20141231"), ("20150101", "")],
    PID_CPI_W: [("19860101", "")],
}
PER_YEAR = {PID_HCE: 4, PID_CPI: 12, PID_CPI_W: 4}


def _batches(pid, template, slot, members, start, end):
    """Greedily split `members` into chunks whose db-loading URL fits URL_MAX."""
    out, cur = [], []
    for mid in members:
        trial = cur + [mid]
        dims = [list(x) for x in template]
        dims[slot] = trial
        if len(db_loading_url(pid, dims, start, end)) <= URL_MAX:
            cur = trial
        else:
            if cur:
                out.append(cur)
            cur = [mid]
    if cur:
        out.append(cur)
    return out


def _max_rows(pid, n_members, start, end):
    end_year = int((end or f"{OPEN_END_YEAR}1231")[:4])
    span_years = end_year - int(start[:4]) + 1
    periods = span_years * PER_YEAR[pid]
    return int(math.ceil(n_members * periods * 1.3)) + 50


def _cube_entries(pid, template, slot, members, tag):
    members = sorted(int(m) for m in members)
    entries = []
    for wi, (start, end) in enumerate(WINDOWS[pid], 1):
        for ci, batch in enumerate(_batches(pid, template, slot, members, start, end), 1):
            dims = [list(x) for x in template]
            dims[slot] = batch
            entries.append({
                "file": f"chunks{pid}/{tag}_w{wi}_c{ci:02d}.csv",
                "url": db_loading_url(pid, dims, start, end),
                "max_rows": _max_rows(pid, len(batch), start, end),
            })
    return entries


def build_manifest():
    hce = load_ca_hce_categories()
    cpi = load_ca_cpi_categories()

    hce_members = [int(m) for m in hce["member_id"]]
    cpi_members = sorted(set(int(m) for m in cpi["member_id_cpi"]) | {2})  # 2 = All-items
    wgt_members = [int(m) for m in cpi["member_id_w"]]

    manifest = []
    # 36-10-0124 HCE: both price bases (current $ and 2017-constant $).
    for base, btag in ((HCE_BASE_NOMINAL, "cur"), (HCE_BASE_REAL, "real")):
        manifest += _cube_entries(
            PID_HCE, [[1], [base], [1], []], 3, hce_members, f"hce_{btag}")
    # 18-10-0004 CPI monthly (Canada = geo member 2).
    manifest += _cube_entries(PID_CPI, [[2], []], 1, cpi_members, "cpi")
    # 18-10-0007 basket weights (Canada = geo member 1).
    manifest += _cube_entries(PID_CPI_W, [[1], [], [1], [1]], 1, wgt_members, "wgt")

    # Safety: no URL may exceed StatCan's limit.
    too_long = [e for e in manifest if len(e["url"]) > 255]
    if too_long:
        raise RuntimeError(f"{len(too_long)} URL(s) exceed 255 chars")
    return manifest


def main(argv=None):
    argv = argv or sys.argv[1:]
    manifest = build_manifest()
    dest = RAW_STATCAN / "manifest.json"

    if "--check" in argv:
        print(f"generated {len(manifest)} entries (not written)")
        return 0

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, separators=(",", ":")))
    print(f"wrote {dest} ({len(manifest)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
