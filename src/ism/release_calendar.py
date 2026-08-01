"""
release_calendar.py
===================

Answers one question: **which gauges are behind, right now?**

The refresh job used to fire once a month on the 3rd, which is the worst day of
the month to pick — US CPI is the only gauge that publishes before the 15th, so
every other gauge was being fetched roughly five weeks stale. This module
replaces that with a calendar gate:

    expected vintage  (from config/release_calendar.yaml)
    committed vintage (from web/data/ism.json + web/data/decomp.json)
    -> a gauge is DUE when expected > committed

which makes the refresh **self-healing**. A daily run does nothing on the ~25
days a month when no release has landed, refreshes exactly the gauge that just
published on the days one has, and — because "due" is defined by the data and
not by the calendar day — automatically retries tomorrow if a source was down,
instead of silently waiting a month for the next cron.

Two details that matter:

* A gauge is due when the *expected* vintage exceeds the *committed* one, never
  merely because today is a release day. So a run that fires an hour late, or a
  release that slips two days, or a whole missed cron, all resolve themselves.
* The `dates` blocks in the YAML are transcribed from agency calendars and are
  the source of truth; the `fallback` rules are deliberately conservative
  backstops for months past the published horizon. Erring late means the gate
  may notice a release a few days after the fact — never that it claims a
  release which has not happened.

CLI
---
    python -m ism.release_calendar report            # freshness table, all gauges
    python -m ism.release_calendar due               # space-separated gauge names
    python -m ism.release_calendar due --target ism      # -> "pce cpi uk"
    python -m ism.release_calendar due --target decomp   # -> "headline core goods services"
    python -m ism.release_calendar due --github-output   # writes $GITHUB_OUTPUT
    python -m ism.release_calendar horizon          # how far the published dates run
    python -m ism.release_calendar next             # upcoming releases

Exit codes for `due`: 0 always (an empty due-set is a normal no-op, not a
failure). `report` exits 1 if any CI-refreshable gauge is behind, so it can
double as a monitor.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

try:  # stdlib since 3.9, but the tz database itself may be absent (bare Windows)
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
CALENDAR_PATH = ROOT / "config" / "release_calendar.yaml"
ISM_JSON = ROOT / "web" / "data" / "ism.json"
DECOMP_JSON = ROOT / "web" / "data" / "decomp.json"

UTC = dt.timezone.utc


# ---------------------------------------------------------------------------
# month arithmetic (YYYY-MM strings are the lingua franca of both JSON files)
# ---------------------------------------------------------------------------

def parse_month(s: str) -> tuple[int, int]:
    """'2026-07' or '2026-07-01' -> (2026, 7)."""
    parts = str(s).split("-")
    return int(parts[0]), int(parts[1])


def fmt_month(ym: tuple[int, int]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


def shift_month(ym: tuple[int, int], n: int) -> tuple[int, int]:
    y, m = ym
    i = (y * 12 + (m - 1)) + n
    return i // 12, i % 12 + 1


def last_day_of(year: int, month: int) -> int:
    nxt = dt.date(year + (month == 12), (month % 12) + 1, 1)
    return (nxt - dt.timedelta(days=1)).day


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

@dataclass
class Gauge:
    name: str
    label: str
    provider: str
    frequency: str
    ci: bool
    ism_targets: list[str]
    decomp_targets: list[str]
    release_time: dt.time
    timezone: str
    utc_hour_fallback: int
    fetch_delay_hours: int
    lookback_months: int
    fallback_lag_months: int
    fallback_day: object          # int or the string "last"
    # Reference-month -> day override. Several agencies publish LATER than usual
    # for the January reference month because of annual reweighting (Eurostat
    # 2026-02-25 vs its usual 16th-20th; Destatis 2026-02-17 vs its usual
    # 10th-13th), so a single fallback day would fire early every January.
    fallback_month_overrides: dict[int, object] = field(default_factory=dict)
    dates: dict[str, str] = field(default_factory=dict)
    expect: dict = field(default_factory=dict)   # machine-checkable date shape
    rule: str = ""
    source: str = ""
    manual_command: str = ""
    notes: list[str] = field(default_factory=list)

    # -- release timing ----------------------------------------------------

    def fallback_release_date(self, ref: tuple[int, int]) -> dt.date:
        """The conservative backstop for a reference month past the published
        horizon. Deliberately late: guessing early would make the gate ask for a
        vintage that does not exist yet."""
        day = self.fallback_month_overrides.get(ref[1], self.fallback_day)
        y, m = shift_month(ref, self.fallback_lag_months)
        d = last_day_of(y, m) if day == "last" else min(int(day), last_day_of(y, m))
        return dt.date(y, m, d)

    def release_date(self, ref: tuple[int, int]) -> dt.date:
        """Publication date for a reference month: published if known, else the
        conservative fallback."""
        key = fmt_month(ref)
        if key in self.dates:
            y, m, d = (int(x) for x in str(self.dates[key]).split("-"))
            return dt.date(y, m, d)
        return self.fallback_release_date(ref)

    def is_published_date(self, ref: tuple[int, int]) -> bool:
        return fmt_month(ref) in self.dates

    def release_instant_utc(self, ref: tuple[int, int]) -> dt.datetime:
        """Release moment in UTC, DST-correct where the tz database is present."""
        local_naive = dt.datetime.combine(self.release_date(ref), self.release_time)
        if ZoneInfo is not None:
            try:
                return local_naive.replace(tzinfo=ZoneInfo(self.timezone)).astimezone(UTC)
            except Exception:  # noqa: BLE001 — missing tzdata; fall through
                pass
        # No tz database: pin to the configured UTC hour on the release date.
        # utc_hour_fallback >= 24 would mean the previous UTC day (Japan), but
        # we keep it simple and clamp — the fetch delay absorbs the difference.
        return dt.datetime.combine(
            self.release_date(ref), dt.time(min(self.utc_hour_fallback, 23)), tzinfo=UTC)

    def available_at_utc(self, ref: tuple[int, int]) -> dt.datetime:
        return self.release_instant_utc(ref) + dt.timedelta(hours=self.fetch_delay_hours)

    # -- vintage -----------------------------------------------------------

    def _candidate_refs(self, now: dt.datetime) -> Iterable[tuple[int, int]]:
        """Reference periods newest-first, respecting the gauge's frequency."""
        cur = (now.year, now.month)
        if self.frequency == "quarterly":
            cur = (cur[0], ((cur[1] - 1) // 3) * 3 + 1)
            step = -3
        else:
            step = -1
        for i in range(self.lookback_months // abs(step) + 1):
            yield shift_month(cur, i * step)

    def expected_vintage(self, now: dt.datetime) -> str | None:
        """Newest reference period that should be fetchable by `now` (UTC)."""
        for ref in self._candidate_refs(now):
            if now >= self.available_at_utc(ref):
                return fmt_month(ref)
        return None

    def next_release(self, now: dt.datetime) -> tuple[str, dt.date] | None:
        """(reference period, release date) of the next publication after now."""
        cur = (now.year, now.month)
        if self.frequency == "quarterly":
            cur = (cur[0], ((cur[1] - 1) // 3) * 3 + 1)
        step = 3 if self.frequency == "quarterly" else 1
        ref = shift_month(cur, -2 * step)
        for _ in range(2 * (self.lookback_months // step + 1)):
            if self.release_instant_utc(ref) > now:
                return fmt_month(ref), self.release_date(ref)
            ref = shift_month(ref, step)
        return None

    def published_through(self) -> str | None:
        return max(self.dates) if self.dates else None


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_calendar(path: Path | None = None) -> dict[str, Gauge]:
    path = path or CALENDAR_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {}) or {}
    out: dict[str, Gauge] = {}
    for name, g in (raw.get("gauges") or {}).items():
        hh, mm = (int(x) for x in str(g["release_time"]).split(":"))
        targets = g.get("targets") or {}
        fb = g.get("fallback") or {}
        notes = []
        for key in ("annual_update", "rebasing"):
            if g.get(key):
                blk = g[key]
                notes.append(f"{key} {blk.get('date', '?')}: {(blk.get('note') or '').strip()}")
        out[name] = Gauge(
            name=name,
            label=g.get("label", name),
            provider=g.get("provider", ""),
            frequency=g.get("frequency", "monthly"),
            ci=bool(g.get("ci", True)),
            ism_targets=list(targets.get("ism") or []),
            decomp_targets=list(targets.get("decomp") or []),
            release_time=dt.time(hh, mm),
            timezone=g.get("timezone", "UTC"),
            utc_hour_fallback=int(g.get("utc_hour_fallback", 12)),
            fetch_delay_hours=int(g.get("fetch_delay_hours",
                                        defaults.get("fetch_delay_hours", 3))),
            lookback_months=int(g.get("lookback_months",
                                      defaults.get("lookback_months", 24))),
            fallback_lag_months=int(fb.get("lag_months", 1)),
            fallback_day=fb.get("day", "last"),
            fallback_month_overrides={int(k): v for k, v in
                                      (fb.get("month_overrides") or {}).items()},
            dates={str(k): str(v) for k, v in (g.get("dates") or {}).items()},
            expect=dict(g.get("expect") or {}),
            rule=(g.get("rule") or "").strip(),
            source=g.get("source", ""),
            manual_command=(g.get("manual_command") or "").strip(),
            notes=notes,
        )
    return out


def committed_vintages() -> dict[str, str | None]:
    """Latest reference period actually present in the committed web data.

    Keys are NAMESPACED — "ism:ca", "decomp:ca" — because the two files reuse
    names: `ca` is both an ism backbone (monthly CPI) and a decomp scope
    (quarterly HCE), on completely different release schedules. A flat dict
    lets the quarterly scope masquerade as the monthly backbone and the gate
    silently stops asking for Canadian CPI.

    A file that fails to parse yields no vintages, which makes every gauge look
    behind — the correct, loud behaviour. (web/data/decomp.json was committed
    with unresolved merge-conflict markers at one point, and nothing noticed.)
    """
    out: dict[str, str | None] = {}
    for path, group_key, ns in ((ISM_JSON, "backbones", "ism"),
                                (DECOMP_JSON, "scopes", "decomp")):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"warning: {path.name} is not valid JSON ({e}); "
                  f"treating its gauges as absent", file=sys.stderr)
            continue
        for key, val in (data.get(group_key) or {}).items():
            ds = val.get("dates") or []
            out[f"{ns}:{key}"] = fmt_month(parse_month(ds[-1])) if ds else None
    return out


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------

@dataclass
class Status:
    gauge: Gauge
    expected: str | None
    committed: str | None          # oldest across the gauge's targets
    targets_behind: dict[str, str | None]

    @property
    def due(self) -> bool:
        if self.expected is None:
            return False
        if not self.targets_behind:
            return False
        return any(c is None or c < self.expected for c in self.targets_behind.values())

    @property
    def months_behind(self) -> int | None:
        if self.expected is None or self.committed is None:
            return None
        return (parse_month(self.expected)[0] * 12 + parse_month(self.expected)[1]) - \
               (parse_month(self.committed)[0] * 12 + parse_month(self.committed)[1])


def evaluate(now: dt.datetime | None = None,
             calendar: dict[str, Gauge] | None = None,
             committed: dict[str, str | None] | None = None) -> dict[str, Status]:
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    calendar = calendar if calendar is not None else load_calendar()
    committed = committed if committed is not None else committed_vintages()

    out: dict[str, Status] = {}
    for name, g in calendar.items():
        expected = g.expected_vintage(now)
        keys = [f"ism:{t}" for t in g.ism_targets] + \
               [f"decomp:{t}" for t in g.decomp_targets]
        targets = {k: committed.get(k) for k in keys}
        present = [v for v in targets.values() if v]
        out[name] = Status(
            gauge=g,
            expected=expected,
            committed=min(present) if present else None,
            targets_behind=targets,
        )
    return out


def due_gauges(statuses: dict[str, Status], ci_only: bool = True) -> list[str]:
    return [n for n, s in statuses.items()
            if s.due and (s.gauge.ci or not ci_only)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _now(args) -> dt.datetime:
    if getattr(args, "now", None):
        s = args.now
        d = dt.datetime.fromisoformat(s) if "T" in s or " " in s else \
            dt.datetime.combine(dt.date.fromisoformat(s), dt.time(12))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    return dt.datetime.now(UTC)


def cmd_report(args) -> int:
    now = _now(args)
    st = evaluate(now)
    print(f"Release-calendar status @ {now:%Y-%m-%d %H:%M} UTC\n")
    hdr = f"{'gauge':8s} {'where':4s} {'committed':>10s} {'expected':>10s} {'status':>10s}  next release"
    print(hdr)
    print("-" * len(hdr))
    behind_ci = 0
    for name, s in st.items():
        nxt = s.gauge.next_release(now)
        nxt_s = f"{nxt[1]:%Y-%m-%d} ({nxt[0]})" if nxt else "-"
        if not s.gauge.is_published_date(parse_month(nxt[0])) if nxt else False:
            nxt_s += " est"
        where = "ci" if s.gauge.ci else "local"
        if s.due:
            flag = "BEHIND"
            if s.gauge.ci:
                behind_ci += 1
        else:
            flag = "ok"
        print(f"{name:8s} {where:4s} {str(s.committed or '-'):>10s} "
              f"{str(s.expected or '-'):>10s} {flag:>10s}  {nxt_s}")
        if s.due:
            for t, v in sorted(s.targets_behind.items()):
                if v is None or (s.expected and v < s.expected):
                    print(f"{'':8s}   -> {t}: {v or 'missing'}")
            if not s.gauge.ci and s.gauge.manual_command:
                print(f"{'':8s}   run locally: {s.gauge.manual_command}")
    notes = [(n, x) for n, s in st.items() for x in s.gauge.notes]
    if notes:
        print("\nUpcoming methodology events:")
        for n, x in notes:
            print(f"  [{n}] {x}")
    return 1 if behind_ci else 0


def cmd_due(args) -> int:
    now = _now(args)
    cal = load_calendar()

    if args.only:
        wanted = args.only.split()
        unknown = [g for g in wanted if g not in cal]
        if unknown:
            print(f"unknown gauge(s): {' '.join(unknown)}; "
                  f"known: {' '.join(cal)}", file=sys.stderr)
            return 2
        names = wanted
    elif args.all:
        names = [n for n, g in cal.items()
                 if g.ci or args.include_local]
    else:
        st = evaluate(now, calendar=cal)
        names = due_gauges(st, ci_only=not args.include_local)

    ism, decomp = [], []
    for n in names:
        ism += cal[n].ism_targets
        decomp += cal[n].decomp_targets
    # de-dupe, preserve the canonical order the exporters use
    ism = list(dict.fromkeys(ism))
    decomp = list(dict.fromkeys(decomp))

    if args.target == "ism":
        print(" ".join(ism))
    elif args.target == "decomp":
        print(" ".join(decomp))
    elif args.json:
        print(json.dumps({"gauges": names, "ism": ism, "decomp": decomp,
                          "any": bool(ism or decomp)}))
    else:
        print(" ".join(names))

    if args.github_output:
        path = os.environ.get("GITHUB_OUTPUT")
        payload = {
            "gauges": " ".join(names),
            "ism": " ".join(ism),
            "decomp": " ".join(decomp),
            "any": "true" if (ism or decomp) else "false",
        }
        if path:
            with open(path, "a", encoding="utf-8") as fh:
                for k, v in payload.items():
                    fh.write(f"{k}={v}\n")
        else:
            print("GITHUB_OUTPUT not set; would have written:", payload, file=sys.stderr)
    return 0


WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "refresh-data.yml"


def cmd_check(args) -> int:
    """Self-validate the calendar. Runs in CI on every poll.

    The repo gitignores tests/, so the invariants that keep this gate honest
    live here rather than in a test file. Five things are checked:

      1. every transcribed date matches the shape that gauge's `expect:` block
         declares (weekday, day-of-month window, lag) — catches a typo when the
         calendar is topped up from an agency site,
      2. the fallback is never EARLIER than a real release, so the gate can
         never ask for a vintage that does not exist yet,
      3. gauges that share a `dates` block share every other timing knob
         (France and Germany are one Eurostat release and drifted apart once),
      4. every backbone/scope in the committed web data belongs to some gauge,
         so nothing can silently stop being refreshed,
      5. the workflow's cron hours actually catch every gauge the same day its
         data becomes fetchable — 08:30 ET is 15:30 UTC in summer but 16:30 in
         winter, so a slot that works in July can miss every US release in
         January.
    """
    cal = load_calendar()
    errs: list[str] = []
    notes: list[str] = []

    # -- 1. shape ---------------------------------------------------------
    for name, g in cal.items():
        exp = g.expect
        if not exp:
            if g.dates:
                notes.append(f"{name}: no expect: block — dates are unchecked")
            continue
        allowed = set(exp.get("weekdays") or WEEKDAY_NAMES)
        lo, hi = exp.get("day_range", [1, 31])
        skip = set(exp.get("exceptions") or [])
        seq = []
        for ref in sorted(g.dates):
            d = g.release_date(parse_month(ref))
            if ref in skip:
                continue
            seq.append(d)
            wd = WEEKDAY_NAMES[d.weekday()]
            if wd not in allowed:
                errs.append(f"{name} {ref} -> {d} is a {wd}; expected {sorted(allowed)}")
            if not lo <= d.day <= hi:
                errs.append(f"{name} {ref} -> {d} outside the expected {lo}-{hi} window")
            want = shift_month(parse_month(ref), int(exp.get("lag_months", 1)))
            if (d.year, d.month) != want:
                errs.append(f"{name} {ref} -> {d} is not in {fmt_month(want)}")
        gaps = exp.get("gap_days")
        if gaps:
            for a, b in zip(seq, seq[1:]):
                if (b - a).days not in gaps:
                    errs.append(f"{name}: gap {a} -> {b} is {(b - a).days}d, expected {gaps}")

    # -- 2. conservative fallback ----------------------------------------
    for name, g in cal.items():
        skip = set((g.expect or {}).get("exceptions") or [])
        for ref in sorted(g.dates):
            if ref in skip:
                continue
            real, guess = g.release_date(parse_month(ref)), g.fallback_release_date(parse_month(ref))
            if guess < real:
                errs.append(
                    f"{name}: fallback for {ref} guesses {guess}, EARLIER than the "
                    f"real release {real} — the gate would ask for a vintage that "
                    f"does not exist yet")

    # -- 3. gauges sharing a calendar must share its timing ---------------
    by_dates: dict[str, list[str]] = {}
    for name, g in cal.items():
        if g.dates:
            by_dates.setdefault(json.dumps(g.dates, sort_keys=True), []).append(name)
    for names in by_dates.values():
        if len(names) < 2:
            continue
        ref = cal[names[0]]
        for other in names[1:]:
            o = cal[other]
            same = (ref.release_time == o.release_time and ref.timezone == o.timezone
                    and ref.fallback_day == o.fallback_day
                    and ref.fallback_lag_months == o.fallback_lag_months
                    and ref.fallback_month_overrides == o.fallback_month_overrides
                    and ref.fetch_delay_hours == o.fetch_delay_hours)
            if not same:
                errs.append(f"{names[0]} and {other} share a dates block but their "
                            f"release time / fallback differ")

    # -- 4. nothing in the committed data is unowned ----------------------
    owned_ism = {t for g in cal.values() for t in g.ism_targets}
    owned_decomp = {t for g in cal.values() for t in g.decomp_targets}
    for key in committed_vintages():
        ns, _, nm = key.partition(":")
        if nm not in (owned_ism if ns == "ism" else owned_decomp):
            errs.append(f"{key} is in the committed web data but no gauge refreshes it")

    # -- 5. the crons cover the calendar ----------------------------------
    polls = []
    if WORKFLOW_PATH.exists():
        try:
            wf = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
            on = wf.get("on") or wf.get(True)   # bare `on:` parses as True
            polls = sorted(int(c["cron"].split()[1]) for c in on["schedule"])
        except Exception as e:  # noqa: BLE001
            notes.append(f"could not read cron hours from the workflow ({e})")
    if polls:
        ci = [n for n, g in cal.items() if g.ci]
        committed = {}
        for n in ci:
            for t in cal[n].ism_targets:
                committed[f"ism:{t}"] = "2026-07"
            for t in cal[n].decomp_targets:
                committed[f"decomp:{t}"] = "2026-07"
        worst = {n: 0.0 for n in ci}
        seen = {n: 0 for n in ci}
        day, end = dt.date(2026, 9, 1), dt.date(2027, 7, 1)
        while day < end:
            for hh in polls:
                now = dt.datetime.combine(day, dt.time(hh), tzinfo=UTC)
                for n in due_gauges(evaluate(now, calendar=cal, committed=committed)):
                    e = evaluate(now, calendar=cal, committed=committed)[n].expected
                    worst[n] = max(worst[n], (now - cal[n].available_at_utc(
                        parse_month(e))).total_seconds() / 3600)
                    seen[n] += 1
                    for t in cal[n].ism_targets:
                        committed[f"ism:{t}"] = e
                    for t in cal[n].decomp_targets:
                        committed[f"decomp:{t}"] = e
            day += dt.timedelta(days=1)
        for n in ci:
            if seen[n] < 9:
                errs.append(f"{n}: only {seen[n]} refreshes simulated in 10 months")
            # 8h, not 12h: the point is same-day pickup. A 12h bound quietly
            # tolerates "caught by the 04:00 poll the next morning", which is
            # exactly the kind of drift this gate exists to prevent. With the
            # current slots every gauge lands within 1.5h.
            if worst[n] >= 8:
                errs.append(f"{n}: waits up to {worst[n]:.1f}h after its data is "
                            f"fetchable — cron hours {polls} UTC do not cover it")
        notes.append(f"cron hours {polls} UTC; worst detection lag "
                     f"{max(worst.values()):.1f}h")

    for n in notes:
        print(f"note: {n}")
    if errs:
        print(f"\nrelease_calendar check FAILED ({len(errs)} problem(s)):", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"\nrelease_calendar check OK — {len(cal)} gauges, "
          f"{sum(len(g.dates) for g in cal.values())} transcribed dates.")
    return 0


def cmd_horizon(args) -> int:
    now = _now(args)
    cal = load_calendar()
    print(f"{'gauge':8s} {'published through':>18s} {'last date':>12s}  coverage")
    warn = 0
    for name, g in cal.items():
        through = g.published_through()
        if not through:
            print(f"{name:8s} {'(no dates)':>18s} {'-':>12s}  using fallback rule only")
            continue
        last = g.release_date(parse_month(through))
        days = (last - now.date()).days
        note = f"{days}d of runway"
        if days < 90:
            note += "  <-- TOP UP from the agency calendar"
            warn += 1
        print(f"{name:8s} {through:>18s} {last.isoformat():>12s}  {note}")
    return 1 if warn else 0


def cmd_next(args) -> int:
    now = _now(args)
    cal = load_calendar()
    rows = []
    for name, g in cal.items():
        nxt = g.next_release(now)
        if nxt:
            rows.append((nxt[1], name, nxt[0], g.is_published_date(parse_month(nxt[0])), g))
    rows.sort()
    print(f"Upcoming releases after {now:%Y-%m-%d %H:%M} UTC\n")
    for date, name, ref, published, g in rows[: args.limit]:
        avail = g.available_at_utc(parse_month(ref))
        print(f"  {date:%Y-%m-%d} {name:8s} ref {ref}   "
              f"{g.release_time:%H:%M} {g.timezone}"
              f"  -> fetch after {avail:%Y-%m-%d %H:%M} UTC"
              f"{'' if published else '   (estimated)'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[3])
    ap.add_argument("--now", help="evaluate as of this UTC instant (testing)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("report", help="freshness table; exit 1 if a CI gauge is behind")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("due", help="which gauges need refreshing")
    p.add_argument("--target", choices=["gauge", "ism", "decomp"], default="gauge")
    p.add_argument("--json", action="store_true")
    p.add_argument("--github-output", action="store_true",
                   help="also append gauges/ism/decomp/any to $GITHUB_OUTPUT")
    p.add_argument("--include-local", action="store_true",
                   help="include gauges marked ci: false (Canada)")
    p.add_argument("--only", default="",
                   help="bypass the gate: use exactly these gauges (space-separated)")
    p.add_argument("--all", action="store_true",
                   help="bypass the gate: every CI gauge, due or not")
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("check", help="self-validate the calendar (runs in CI)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("horizon", help="how far the published dates run")
    p.set_defaults(func=cmd_horizon)

    p = sub.add_parser("next", help="upcoming releases")
    p.add_argument("--limit", type=int, default=12)
    p.set_defaults(func=cmd_next)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        args.func = cmd_report
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
