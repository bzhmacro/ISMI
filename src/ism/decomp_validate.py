"""
ism.decomp_validate
===================

Ground-truth validation for the supply/demand decomposition against the FRBSF
*published* series, "Supply- and Demand-Driven PCE Inflation":

    https://www.frbsf.org/research-and-insights/data-and-indicators/
        supply-and-demand-driven-pce-inflation/

The page publishes four chart CSVs (the cleanest machine-readable form) plus a
workbook. We use the CSVs:

    supply-demand-pce-headline-monthly-chart-1.csv   (annualised monthly, headline)
    supply-demand-pce-core-monthly-chart-2.csv       (annualised monthly, core)
    supply-demand-pce-headline-yoy-chart-3.csv       (year-over-year, headline)
    supply-demand-pce-core-yoy-chart-4.csv           (year-over-year, core)

Each splits inflation into supply-driven, demand-driven and ambiguous
contributions. Note the published series uses the **precision (ambiguous)**
labeling (cut = 0.1 SD), so compare against the engine run with
`DecompConfig(precision_cut=0.1)` for the closest match; the working-paper
baseline (Fig. 3) is binary (`precision_cut=0.0`).

Files are cached under data/raw/external/frbsf/. If a file is absent the loader
tries to download it (no-op in network-restricted sandboxes; run where frbsf.org
is reachable). Everything degrades gracefully to None.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT

FRBSF_DIR = REPO_ROOT / "data" / "raw" / "external" / "frbsf"
BASE = "https://www.frbsf.org/wp-content/uploads/"
FILES = {
    ("headline", "monthly"): "supply-demand-pce-headline-monthly-chart-1.csv",
    ("core", "monthly"): "supply-demand-pce-core-monthly-chart-2.csv",
    ("headline", "yoy"): "supply-demand-pce-headline-yoy-chart-3.csv",
    ("core", "yoy"): "supply-demand-pce-core-yoy-chart-4.csv",
}
WORKBOOK = "supply-demand-pce-inflation.xlsx"


def _maybe_download(fname: str) -> Optional[Path]:
    FRBSF_DIR.mkdir(parents=True, exist_ok=True)
    target = FRBSF_DIR / fname
    if target.exists():
        return target
    try:
        import requests
        r = requests.get(BASE + fname, timeout=60,
                         headers={"User-Agent": "ism-decomp-replication/1.0"})
        r.raise_for_status()
        target.write_bytes(r.content)
        print(f"[decomp_validate] downloaded {fname}")
        return target
    except Exception as exc:  # network blocked / offline -> caller handles None
        print(f"[decomp_validate] could not fetch {fname}: {type(exc).__name__}: {exc}")
        return None


def _find_col(cols, *needles):
    for c in cols:
        cl = str(c).strip().lower()
        if all(n in cl for n in needles):
            return c
    return None


def _parse_chart_csv(path: Path) -> Optional[pd.DataFrame]:
    """Parse one FRBSF chart CSV into [date x {supply,demand,ambiguous}] (in pp)."""
    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    date_col = _find_col(df.columns, "date") or df.columns[0]
    idx = pd.to_datetime(df[date_col].astype(str), errors="coerce")
    sup = _find_col(df.columns, "supply")
    dem = _find_col(df.columns, "demand")
    amb = _find_col(df.columns, "ambig")
    if sup is None or dem is None:
        return None
    out = pd.DataFrame(index=idx.dt.to_period("M").dt.to_timestamp())
    out["supply"] = pd.to_numeric(df[sup], errors="coerce").to_numpy()
    out["demand"] = pd.to_numeric(df[dem], errors="coerce").to_numpy()
    out["ambiguous"] = (pd.to_numeric(df[amb], errors="coerce").to_numpy()
                        if amb is not None else np.nan)
    return out[~out.index.isna()].sort_index()


def load_frbsf_author(scope: str = "headline",
                      index: Optional[pd.DatetimeIndex] = None) -> Optional[dict]:
    """Author overlay for `scope` as {"monthly": {...}, "yoy": {...}}.

    Each inner dict has lists aligned to `index` (if given) for supply / demand /
    ambiguous. Returns None if neither CSV is available.
    """
    res = {}
    for kind in ("monthly", "yoy"):
        path = _maybe_download(FILES[(scope, kind)])
        if path is None or not path.exists():
            continue
        df = _parse_chart_csv(path)
        if df is None:
            continue
        if index is not None:
            df = df.reindex(index)
        res[kind] = {c: [None if pd.isna(v) else round(float(v), 5) for v in df[c]]
                     for c in ["supply", "demand", "ambiguous"]}
    return res or None


def validate_decomp(computed: pd.DataFrame, scope: str = "headline",
                    kind: str = "yoy") -> Optional[pd.DataFrame]:
    """Correlation / RMSE / MAE of computed vs FRBSF author contributions.

    `computed` must have columns supply / demand (and optionally ambiguous),
    indexed by month, in percentage points. Returns a small report DataFrame, or
    None if the author file is unavailable.
    """
    path = _maybe_download(FILES[(scope, kind)])
    if path is None or not path.exists():
        print("[decomp_validate] author file unavailable -> cannot validate")
        return None
    author = _parse_chart_csv(path)
    if author is None:
        return None
    rows = []
    for col in ("supply", "demand", "ambiguous"):
        if col not in computed.columns or col not in author.columns:
            continue
        a, b = computed[col].align(author[col], join="inner")
        m = a.notna() & b.notna()
        a, b = a[m], b[m]
        if len(a) < 12:
            continue
        corr = float(np.corrcoef(a, b)[0, 1])
        rmse = float(np.sqrt(np.mean((a - b) ** 2)))
        mae = float(np.mean(np.abs(a - b)))
        rows.append({"series": col, "n": int(len(a)), "corr": round(corr, 4),
                     "rmse": round(rmse, 4), "mae": round(mae, 4)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Canada (Bank of Canada SAP 2026-33) — qualitative validation
# ---------------------------------------------------------------------------
# The BoC paper ships no machine-readable series, so we validate the Canadian
# decomposition against the stated facts of Kang–Sekkel–Taskin–Yang (2026):
#   * post-pandemic total PCE inflation peaked "near 6 percent in 2022";
#   * "Both supply- and demand-side forces contributed to the increase,
#      although supply-driven inflation accounted for the larger share";
#   * "Demand-driven inflation turned negative during the pandemic";
#   * inflation returned "toward the 2 percent target by early 2025".
def validate_ca_decomp(contrib_yoy: pd.DataFrame) -> pd.DataFrame:
    """Check the Canada y/y contributions against the BoC paper's stated facts.

    `contrib_yoy` has columns supply / demand / total (percentage points),
    indexed by quarter (quarter-start timestamps). Returns a report DataFrame
    with one row per check: metric, value, expected range, and pass/fail.
    """
    df = contrib_yoy.dropna(subset=["total"])
    rows = []

    def _add(check, value, lo, hi):
        ok = (value is not None) and (lo <= value <= hi)
        rows.append({"check": check,
                     "value": None if value is None else round(float(value), 2),
                     "expected": f"[{lo}, {hi}]", "pass": bool(ok)})

    # 1) post-pandemic peak total inflation, 2021-2023, near 6%
    post = df.loc[(df.index >= "2021-01-01") & (df.index <= "2023-12-31"), "total"]
    peak = float(post.max()) if len(post) else None
    _add("post-pandemic peak total y/y (~6%)", peak, 4.5, 8.0)

    # 2) at the peak quarter, supply contribution exceeds demand
    if len(post):
        pk = post.idxmax()
        sup_pk = float(df.loc[pk, "supply"]); dem_pk = float(df.loc[pk, "demand"])
        _add("supply − demand at peak (>0, supply larger)", sup_pk - dem_pk, 0.0, 10.0)

    # 3) demand-driven inflation went negative during the pandemic (2020-2021)
    pan = df.loc[(df.index >= "2020-01-01") & (df.index <= "2021-06-30"), "demand"]
    dmin = float(pan.min()) if len(pan) else None
    _add("min demand y/y in pandemic (<0)", dmin, -10.0, 0.0)

    # 4) most recent total inflation eased toward target (<= ~3.5%)
    latest = float(df["total"].iloc[-1]) if len(df) else None
    _add("latest total y/y (eased toward target)", latest, -1.0, 3.5)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Generic sanity checks for the quarterly country ports (UK / France / Germany)
# ---------------------------------------------------------------------------
# No published supply/demand series exists for these countries, so instead of a
# ground-truth comparison we assert the decomposition is internally coherent and
# lands in a plausible range: the supply+demand+ambiguous split reconstructs the
# total, and the post-pandemic peak of aggregate y/y inflation is elevated but
# not absurd.
def sanity_quarterly_decomp(contrib, contrib_yoy) -> pd.DataFrame:
    """Internal-coherence sanity checks for a country port's decomposition.

    `contrib` is the per-quarter contribution frame (supply/demand/ambiguous/
    total), `contrib_yoy` its running-4-quarter version. Returns a report
    DataFrame with metric / value / expected / pass columns.
    """
    rows = []

    def _add(check, value, lo, hi):
        ok = (value is not None) and (lo <= value <= hi)
        rows.append({"check": check,
                     "value": None if value is None else round(float(value), 3),
                     "expected": f"[{lo}, {hi}]", "pass": bool(ok)})

    c = contrib.dropna(subset=["total"])
    # 1) split reconstructs the total (max abs residual over the sample ~ 0)
    if len(c):
        resid = (c[["supply", "demand", "ambiguous"]].sum(axis=1) - c["total"]).abs().max()
        _add("max |supply+demand+ambiguous − total|", float(resid), 0.0, 1e-6)

    y = contrib_yoy.dropna(subset=["total"])
    # 2) post-pandemic peak y/y inflation is elevated but plausible
    post = y.loc[(y.index >= "2021-01-01") & (y.index <= "2023-12-31"), "total"]
    if len(post):
        _add("post-pandemic peak total y/y", float(post.max()), 3.0, 20.0)
    # 3) some quarters are supply- and some demand-led (not a degenerate split)
    if len(y):
        share_sup = float((y["supply"] > y["demand"]).mean())
        _add("share of quarters supply>demand", share_sup, 0.05, 0.95)

    return pd.DataFrame(rows)
