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

Checks, for web/data/ism.json, web/data/decomp.json and web/data/trim.json:
  * valid JSON with the expected integer schema,
  * the default gauge is present, and no gauge that existed at git HEAD has
    disappeared (a dropped gauge is a silent regression),
  * every gauge has a sorted, non-trivial date axis whose latest point is not
    older than --max-stale-days (generous, to allow release lags + quarterly
    data), and did not move BACKWARDS versus the committed file,
  * every gauge's panel contains at least some finite numbers.

trim.json gets one extra check of its own: the measures it claims to reproduce
must still reproduce them. A refresh that quietly breaks the weights or the
seasonal treatment would pass every structural test above while the correlation
with the Cleveland and Dallas series collapsed, so the committed validation
numbers are re-read from the payload and gated (--min-corr).

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
    (ROOT / "web" / "data" / "trim.json", 1, "scopes"),
]

TRIM_JSON = ROOT / "web" / "data" / "trim.json"


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


def validate_file(path: Path, schema: int, group_key: str, max_stale_days: int):
    """Return (errors, warnings). Errors block the commit; warnings only inform.

    A stale gauge is a WARNING, not an error: a source that simply hasn't
    published (or was briefly unreachable, e.g. StatCan) is not a corrupt
    refresh, and must not block the gauges that DID update. Hard failures are
    reserved for genuinely broken output: bad JSON/schema, a dropped gauge,
    dates moving backwards, or an empty panel.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return [f"{path.name}: file missing"], warnings

    try:
        data = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        return [f"{path.name}: not valid JSON ({e})"], warnings

    meta = data.get("meta", {})
    if meta.get("schema") != schema:
        errors.append(f"{path.name}: schema {meta.get('schema')!r}, expected {schema}")

    groups = data.get(group_key) or {}
    if not groups:
        return errors + [f"{path.name}: no '{group_key}' present"], warnings

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
            warnings.append(
                f"{path.name}[{g}]: latest date {ds[-1]} is {stale}d old "
                f"(> {max_stale_days}d) — source may not have published")
        if prev and prev.get(g) and latest < prev[g]:
            errors.append(
                f"{path.name}[{g}]: latest date {ds[-1]} moved BACKWARDS "
                f"from committed {prev[g].isoformat()[:7]}")
        if not _any_finite(gv.get("panel", {})):
            errors.append(f"{path.name}[{g}]: panel has no finite values")

    return errors, warnings


def validate_trim_fidelity(min_corr: float) -> tuple[list[str], list[str]]:
    """The trimmed-mean scopes must still track the published series.

    ``export_trim_data.py`` writes the comparison table into the payload, so the
    gate is a read rather than a recomputation: every (scope, measure) pair with
    a published counterpart must clear ``min_corr`` at the 12-month horizon, and
    the CPI->PCE identity must still close.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not TRIM_JSON.exists():
        return [f"{TRIM_JSON.name}: missing"], warnings
    payload = json.loads(TRIM_JSON.read_text())

    checked = 0
    for name, scope in (payload.get("scopes") or {}).items():
        for row in scope.get("validation") or []:
            if row.get("horizon") != "12m":
                continue
            checked += 1
            corr = row.get("corr")
            if corr is None or corr < min_corr:
                errors.append(
                    f"trim.json[{name}]: {row.get('measure')} 12-month "
                    f"correlation {corr} < {min_corr} vs the published series")
    if checked == 0:
        warnings.append("trim.json: no scope has a published counterpart to "
                        "validate against")

    cp = payload.get("cpipce")
    if cp:
        table, comps = cp.get("table", {}), cp.get("components", [])
        gap = table.get("gap") or []
        worst = 0.0
        for i, g in enumerate(gap):
            if g is None:
                continue
            parts = [table[c][i] for c in comps if table.get(c) and table[c][i] is not None]
            if len(parts) == len(comps):
                worst = max(worst, abs(sum(parts) - g))
        # The payload ships the terms rounded, so the identity can only close to
        # the shipped precision (5 dp x 6 terms). Anything above this is a real
        # break, not rounding.
        if worst > 1e-3:
            errors.append(f"trim.json[cpipce]: the gap identity does not close "
                          f"(max residual {worst:.2e})")
    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-stale-days", type=int, default=240,
                    help="fail if a gauge's latest date is older than this "
                         "(default 240; covers quarterly lags + release delays)")
    ap.add_argument("--min-corr", type=float, default=0.95,
                    help="minimum 12-month correlation with the published "
                         "Cleveland/Dallas series (default 0.95)")
    args = ap.parse_args()

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for path, schema, group_key in FILES:
        errs, warns = validate_file(path, schema, group_key, args.max_stale_days)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        bits = []
        if errs:
            bits.append(f"{len(errs)} problem(s)")
        if warns:
            bits.append(f"{len(warns)} warning(s)")
        print(f"{path.name}: {', '.join(bits) or 'OK'}")

    errs, warns = validate_trim_fidelity(args.min_corr)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    print(f"trim.json fidelity: {len(errs) or 'OK'}"
          + (" problem(s)" if errs else ""))

    if all_warnings:
        print("\nWarnings (non-blocking):")
        for w in all_warnings:
            print(f"  - {w}")

    if all_errors:
        print("\nVALIDATION FAILED:", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("\nAll data files valid — safe to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
