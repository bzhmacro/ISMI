"""
export_release_calendar.py
==========================

Publish `config/release_calendar.yaml` to the website as
`web/data/release_calendar.json`, so the page can answer two questions without
any backend:

  * is there a newer print available than the one currently loaded?
  * if so, which gauge, and what reference month?

DESIGN NOTE — why the JSON carries UTC instants, not timezones
--------------------------------------------------------------
The calendar stores each release as a local wall time in an IANA zone (07:00
Europe/London, 08:30 America/New_York, ...). Converting *local wall time in an
arbitrary zone* to a UTC instant in browser JavaScript is genuinely awkward and
easy to get wrong by an hour twice a year — which is exactly the bug class that
made a 16:00 UTC cron miss every US winter release. So Python does the
conversion once, here, and the JSON ships a plain `availableUtc` timestamp per
release. The browser then only ever does `new Date(availableUtc) <= now`.

The file also embeds the vintages actually present in the committed
`ism.json` / `decomp.json` at export time, so the page can compute
"behind / current" from a single small fetch instead of re-downloading 27 MB
of panel data just to read the last date.

    python scripts/export_release_calendar.py
    python scripts/export_release_calendar.py --back 6 --forward 18
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ism.release_calendar import (  # noqa: E402
    committed_vintages,
    fmt_month,
    load_calendar,
    parse_month,
    shift_month,
)

DEST = ROOT / "web" / "data" / "release_calendar.json"
UTC = dt.timezone.utc


def build(back: int = 6, forward: int = 18) -> dict:
    cal = load_calendar()
    committed = committed_vintages()
    now = dt.datetime.now(UTC)

    gauges = []
    notes = []
    for name, g in cal.items():
        step = 3 if g.frequency == "quarterly" else 1
        cur = (now.year, now.month)
        if g.frequency == "quarterly":
            cur = (cur[0], ((cur[1] - 1) // 3) * 3 + 1)

        releases = []
        for i in range(-back, forward + 1, 1):
            ref = shift_month(cur, i * step)
            if g.frequency == "quarterly" and ref[1] not in (1, 4, 7, 10):
                continue
            releases.append({
                "ref": fmt_month(ref),
                "date": g.release_date(ref).isoformat(),
                "availableUtc": g.available_at_utc(ref)
                                 .astimezone(UTC).isoformat().replace("+00:00", "Z"),
                # `published` false => this row came from the conservative
                # fallback, not from the agency's calendar. The UI marks it
                # "estimated" so nobody reads a guess as a commitment.
                "published": g.is_published_date(ref),
            })
        releases.sort(key=lambda r: r["ref"])

        keys = [f"ism:{t}" for t in g.ism_targets] + \
               [f"decomp:{t}" for t in g.decomp_targets]
        present = [committed[k] for k in keys if committed.get(k)]

        gauges.append({
            "name": name,
            "label": g.label,
            "provider": g.provider,
            "frequency": g.frequency,
            "ci": g.ci,
            "source": g.source,
            "manualCommand": g.manual_command or None,
            "targets": keys,
            # oldest vintage across the gauge's targets — a gauge is only
            # "current" when everything it feeds is current
            "committed": min(present) if present else None,
            "committedByTarget": {k: committed.get(k) for k in keys},
            "releases": releases,
        })

        for n in g.notes:
            notes.append({"gauge": name, "note": n})

    return {
        "schema": 1,
        "generated_utc": now.isoformat(),
        "calendar_verified": str(
            (__import__("yaml").safe_load(
                (ROOT / "config" / "release_calendar.yaml").read_text(encoding="utf-8"))
             or {}).get("verified", "")),
        "gauges": gauges,
        "notes": notes,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[3])
    ap.add_argument("--back", type=int, default=6,
                    help="reference periods of history to include (default 6)")
    ap.add_argument("--forward", type=int, default=18,
                    help="reference periods ahead to include (default 18)")
    args = ap.parse_args(argv)

    payload = build(args.back, args.forward)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    behind = [g["name"] for g in payload["gauges"]
              if g["committed"] and any(
                  r["availableUtc"] <= payload["generated_utc"].replace("+00:00", "Z")
                  and r["ref"] > g["committed"] for r in g["releases"])]
    print(f"wrote {DEST} ({DEST.stat().st_size / 1024:.1f} KB; "
          f"{len(payload['gauges'])} gauges)")
    print(f"  behind right now: {', '.join(behind) if behind else '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
