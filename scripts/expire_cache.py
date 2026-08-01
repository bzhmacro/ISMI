"""
expire_cache.py
===============

Delete raw-cache entries that have gone stale, so the next export re-fetches.

WHY THIS EXISTS
---------------
Every provider client caches under `data/raw/<provider>/` with the same shape:

    if force or not cache.exists():
        ...download...

There is no expiry. Once a file is on disk it is never re-downloaded, and the
exporters never pass `force=True`. In CI that is invisible — a fresh runner has
an empty cache, so it always fetches live data — but **locally it silently
rebuilds the site from whatever is on disk**, however old.

That is not hypothetical. Running `export_web_data.py uk` against a cache from
12 June produced a UK backbone ending 2026-04, one month BEHIND the committed
2026-05, and `validate_web_data.py` correctly refused it ("latest date moved
BACKWARDS"). Canada is refreshed this way by design — StatCan is unreachable
from CI — so the local path is the one that matters most.

Deleting the stale file is the fix that needs no client changes: every client
already re-downloads when the cache is absent.

USAGE
-----
    python scripts/expire_cache.py --older-than-days 20 --dry-run
    python scripts/expire_cache.py --older-than-days 20            # do it
    python scripts/expire_cache.py --provider ons eurostat         # just these
    python scripts/expire_cache.py --all                           # nuke everything

Default threshold is 20 days: shorter than the ~28-31 day gap between monthly
releases, so a cache entry never survives into the next reference month, but
long enough that back-to-back runs on a release day do not re-download 300 MB.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# Provenance sidecars are rewritten with their payload; drop them together so a
# stale .fetch.json can never describe a freshly downloaded file.
SIDECAR_SUFFIXES = (".fetch.json",)


# Marker for entries we could not delete outright. Clients look for the exact
# cache filename, so a renamed file is just as expired as a deleted one.
EXPIRED_SUFFIX = ".expired"


def _payload_files(provider_dir: Path):
    return [f for f in provider_dir.rglob("*")
            if f.is_file()
            and not f.name.endswith(SIDECAR_SUFFIXES)
            and not f.name.endswith(EXPIRED_SUFFIX)]


def _remove(path: Path) -> str:
    """Delete `path`, falling back to renaming it aside.

    Cloud-synced folders (Dropbox, OneDrive, iCloud) and some network mounts
    refuse unlink while allowing rename. Since the clients re-download whenever
    the exact cache filename is missing, renaming expires the entry just as
    effectively — so a locked file must not abort the whole pass.
    """
    try:
        path.unlink(missing_ok=True)
        return "deleted"
    except OSError:
        pass
    try:
        target = path.with_name(path.name + EXPIRED_SUFFIX)
        if target.exists():
            try:
                target.unlink()
            except OSError:
                target = path.with_name(f"{path.name}.{int(time.time())}{EXPIRED_SUFFIX}")
        path.rename(target)
        return "renamed"
    except OSError as e:
        return f"FAILED ({e.strerror or e})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[3])
    ap.add_argument("--older-than-days", type=float, default=20.0,
                    help="expire cache entries older than this (default 20)")
    ap.add_argument("--provider", nargs="*", default=None,
                    help="only these provider dirs (default: all)")
    ap.add_argument("--all", action="store_true",
                    help="expire everything regardless of age")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be removed and stop")
    args = ap.parse_args(argv)

    if not RAW.exists():
        print(f"no cache at {RAW} — nothing to do")
        return 0

    cutoff = time.time() - args.older_than_days * 86400
    providers = sorted(p for p in RAW.iterdir() if p.is_dir())
    if args.provider:
        wanted = set(args.provider)
        unknown = wanted - {p.name for p in providers}
        if unknown:
            print(f"unknown provider(s): {', '.join(sorted(unknown))}; "
                  f"have: {', '.join(p.name for p in providers)}", file=sys.stderr)
            return 2
        providers = [p for p in providers if p.name in wanted]

    total_n = total_bytes = 0
    for pdir in providers:
        payloads = _payload_files(pdir)
        if not payloads:
            continue
        stale = payloads if args.all else [f for f in payloads
                                           if f.stat().st_mtime < cutoff]
        if not stale:
            newest = max(f.stat().st_mtime for f in payloads)
            print(f"  {pdir.name:12s} fresh  ({len(payloads)} files, newest "
                  f"{(time.time() - newest) / 86400:.1f}d old)")
            continue
        nbytes = sum(f.stat().st_size for f in stale)
        total_n += len(stale)
        total_bytes += nbytes
        print(f"  {pdir.name:12s} EXPIRE {len(stale)}/{len(payloads)} files "
              f"({nbytes / 1e6:.1f} MB)")
        if args.dry_run:
            continue
        renamed = failed = 0
        for f in stale:
            for sidecar in (f.with_name(f.name + s) for s in SIDECAR_SUFFIXES):
                if sidecar.exists():
                    _remove(sidecar)
            how = _remove(f)
            if how == "renamed":
                renamed += 1
            elif how.startswith("FAILED"):
                failed += 1
                if failed <= 3:
                    print(f"    ! could not expire {f.name}: {how}")
        if renamed:
            print(f"    ({renamed} renamed aside rather than deleted — "
                  f"cloud-synced or locked folder)")
        if failed:
            print(f"    ! {failed} file(s) could NOT be expired and will still "
                  f"be served from cache")
            total_n -= failed
        # tidy any empty subdirectories left behind
        for d in sorted((d for d in pdir.rglob("*") if d.is_dir()), reverse=True):
            try:
                if not any(d.iterdir()):
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass

    verb = "would expire" if args.dry_run else "expired"
    print(f"\n{verb} {total_n} file(s), {total_bytes / 1e6:.1f} MB"
          f"{' (dry run)' if args.dry_run else ''}")
    if not args.dry_run and total_n:
        print("next export will re-download these from the providers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
