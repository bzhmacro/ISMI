"""
validate_web_data.py
====================

Post-export sanity gate for the static site's data files, run by the
refresh-data GitHub Action *after* the exporters and *before* the commit. It
catches the ways a scheduled data refresh can go wrong -- a source returning
garbage, a gauge silently dropping out, dates failing to advance, or a panel
coming back empty -- so a broken refresh never gets committed and redeployed.

It deliberately validates the DATA (the freshly written JSON), not the engine
code: a data-only refresh never changes web/engine.js or src/ism, so the
Python/JS engine-parity tests belong in a code-change CI run, not here.

Checks, for web/data/ism.json and web/data/decomp.json:
  * valid JSON with the expected integer schema,
  * the default gauge is present, and no gauge that existed at git HEAD has
    disappeared (a dropped gauge is a silent regression),
  * every gauge has a sorted, non-trivial date axis whose latest point is not
    older than --max-stale-days (generous, to allow release lags + quarterly
    data), and did not move BACKWARDS versus the committed file,
  * every gauge's panel contains at least some finite numbers.

    python scripts/validate_web_data.py                 # both files
    python scripts/validate_web_data.py --max-stale-days 240
Exit code 0 = OK (safe to commit); non-zero = block the commit.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (path, schema, group_key) for each data file the site loads.
FILES = [
    (ROOT / "web" / "data" / "ism.json", 3, "backbones"),
    (ROOT / "web" / "data" / "decomp.json", 2, "scopes"),
]


def _parse_month(s: str) -> dt.date:
    """Accept 'YYYY-MM' or 'YYYY-MM-DD'."""
    parts = s.split("-")
    y, m = int(parts[0]), int(parts[1])
    d = int(parts[2]) if len(parts) > 2 else 1
    return dt.date(y, m, d)


def _any_finite(obj) -> bool:
    """True if any leaf number in a nested list/dict is finite."""
    stack = [obj]
    while stack:
        x = stack.pop()
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            if math.isfinite(x):
                return True
        elif isinstance(x, list):
            stack.extend(x)
        elif isinstance(x, dict):
            stack.extend(x.values())
    return False


def _committed_groups_and_latest(path: Path, group_key: str):
    """Groups + latest date per group from the version at git HEAD, or None."""
    rel = path.relative_to(ROOT).as_posix()
    try:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        if blob.returncode != 0:
            return None
        d = json.loads(blob.stdout)
    except Exception:
        return None
    out = {}
    for g, gv in (d.get(group_key) or {}).items():
        ds = gv.get("dates") or []
        out[g] = _parse_month(ds[-1]) if ds else None
    return out


def validate_file(path: Path, schema: int, group_key: str, max_stale_days: int) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{path.name}: file missing"]

    try:
        data = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        return [f"{path.name}: not valid JSON ({e})"]

    meta = data.get("meta", {})
    if meta.get("schema") != schema:
        errors.append(f"{path.name}: schema {meta.get('schema')!r}, expected {schema}")

    groups = data.get(group_key) or {}
    if not groups:
        return errors + [f"{path.name}: no '{group_key}' present"]

    default = meta.get("default_backbone") or meta.get("default_scope")
    if default and default not in groups:
        errors.append(f"{path.name}: default gauge '{default}' missing from {group_key}")

    prev = _committed_groups_and_latest(path, group_key)
    if prev:
        for g in prev:
            if g not in groups:
                errors.append(f"{path.name}: gauge '{g}' present at HEAD but dropped")

    today = dt.date.today()
    for g, gv in groups.items():
        ds = gv.get("dates") or []
        if len(ds) < 12:
            errors.append(f"{path.name}[{g}]: only {len(ds)} dates")
            continue
        try:
            parsed = [_parse_month(x) for x in ds]
        except Exception as e:  # noqa: BLE001
            errors.append(f"{path.name}[{g}]: unparseable date ({e})")
            continue
        if parsed != sorted(parsed):
            errors.append(f"{path.name}[{g}]: dates not sorted ascending")
        latest = parsed[-1]
        stale = (today - latest).days
        if stale > max_stale_days:
            errors.append(
                f"{path.name}[{g}]: latest date {ds[-1]} is {stale}d old "
                f"(> {max_stale_days}d)")
        if prev and prev.get(g) and latest < prev[g]:
            errors.append(
                f"{path.name}[{g}]: latest date {ds[-1]} moved BACKWARDS "
                f"from committed {prev[g].isoformat()[:7]}")
        if not _any_finite(gv.get("panel", {})):
            errors.append(f"{path.name}[{g}]: panel has no finite values")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-stale-days", type=int, default=240,
                    help="fail if a gauge's latest date is older than this "
                         "(default 240; covers quarterly lags + release delays)")
    args = ap.parse_args()

    all_errors: list[str] = []
    for path, schema, group_key in FILES:
        errs = validate_file(path, schema, group_key, args.max_stale_days)
        all_errors.extend(errs)
        status = "OK" if not errs else f"{len(errs)} problem(s)"
        print(f"{path.name}: {status}")

    if all_errors:
        print("\nVALIDATION FAILED:", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("\nAll data files valid — safe to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
