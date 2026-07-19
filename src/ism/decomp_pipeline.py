"""
ism.decomp_pipeline
====================

Turn raw BEA "Underlying Detail" data into the four objects the supply/demand
decomposition engine (`ism.decomp_engine`) needs:

    log_price     : DataFrame [months x categories]   ln(price index)   (Eq. 13)
    log_quantity  : DataFrame [months x categories]   ln(quantity index) (Eq. 12)
    inflation     : DataFrame [months x categories]   MoM % change of price (Eq. 15)
    weights       : DataFrame [months x categories]   nominal expenditure shares ω

The momentum index (`ism.pipeline`) needs only price + nominal; this model also
needs the **real quantity** index, so we add BEA table 2.4.3U (U20403):

    * 2.4.3U (U20403): real PCE quantity indexes -> q_{i,t}
    * 2.4.4U (U20404): price indexes            -> p_{i,t} and π_{i,t}
    * 2.4.5U (U20405): nominal PCE ($)          -> ω_{i,t}

Headline vs core
----------------
`scope="headline"` uses the full pinned 4th-level category set
(config/pce_categories.csv). `scope="core"` drops the food-off-premises and
energy categories listed in config/pce_core_exclusions.csv, mirroring BEA's
"PCE excluding food and energy". Weights are renormalised over whichever set is
used, so the contributions sum to the corresponding (headline or core)
aggregate.

Robustness specs (Section 3.2)
------------------------------
`spec="levels"` (baseline) returns log levels; `spec="diff"` returns log first
differences for Eqs. (19)-(20); `spec="filter"` returns the Hamilton-(2018)
2-year filtered cyclical component of the logs. In every case `inflation`
remains the MoM % change of the *price index* so the contribution units stay in
percentage points.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import BeaClient, REPO_ROOT
from .transforms import monthly_inflation


CONFIG_DIR = REPO_ROOT / "config"


# ----------------------------------------------------------------------------
# BEA table -> wide [month x root-key] panel  (shared convention with the
# web exporter's _norm_key: strip a leading IA/LA tag or the trailing
# table-suffix letter so price (…G), quantity (…M/…Q) and nominal (…C) series
# collapse onto the same category key).
# ----------------------------------------------------------------------------
def _norm_key(code: str) -> str:
    c = str(code)
    return c[1:] if c[:2] in ("IA", "LA") else c[:-1]


def bea_wide(bea: BeaClient, table: str, force: bool = False) -> pd.DataFrame:
    """Fetch a BEA monthly table (cached) and pivot to [date x category key]."""
    df = bea.table(table, force=force)
    df = df.copy()
    df["date"] = pd.to_datetime(
        df["TimePeriod"].astype(str).str.replace("M", "-", regex=False) + "-01",
        errors="coerce",
    )
    df["key"] = df["SeriesCode"].map(_norm_key)
    wide = df.pivot_table(index="date", columns="key", values="DataValue",
                          aggfunc="first").sort_index()
    # human-readable labels for inspection / the web UI
    wide.attrs["labels"] = (
        df.dropna(subset=["key"]).groupby("key")["LineDescription"].first().to_dict()
    )
    return wide


# ----------------------------------------------------------------------------
# Category sets
# ----------------------------------------------------------------------------
def load_categories() -> pd.DataFrame:
    """The pinned 4th-level PCE category set (config/pce_categories.csv)."""
    return pd.read_csv(CONFIG_DIR / "pce_categories.csv", dtype={"key": str})


def core_exclusions() -> set[str]:
    """Food-off-premises and energy keys excluded from core (config file)."""
    path = CONFIG_DIR / "pce_core_exclusions.csv"
    if path.exists():
        return set(pd.read_csv(path, dtype={"key": str})["key"])
    # built-in fallback (documented in config/pce_core_exclusions.csv)
    return {"DFOFR", "DNBVR", "DFFDR", "DGASR", "DOILR", "DLPFR", "DELGR"}


def goods_services_keys(tag: str) -> list[str]:
    """Keys tagged Goods ('G') or Services ('S') in config/pce_categories.csv.

    The tag is BEA's own PCE aggregate split: every pinned leaf under the table
    2.4.5U "Goods" header (line < 150) is a good, everything under "Services"
    (line >= 150) is a service. Mirrors Canada's `gs` column in
    config/ca_hce_categories.csv, so the US gets the same total/goods/services
    scopes as the Bank-of-Canada port (Shapiro Figs. 3-4). All-PCE, no core cut.
    """
    cats = load_categories()
    if "gs" not in cats.columns:  # legacy config without the tag
        raise ValueError(
            "config/pce_categories.csv has no 'gs' column; regenerate it "
            "(G = line < 150, S = line >= 150 in BEA table 2.4.5U)."
        )
    want = {"goods": "G", "services": "S"}[tag]
    return [k for k in cats["key"].astype(str) if
            cats.loc[cats["key"].astype(str) == k, "gs"].iloc[0] == want]


# ----------------------------------------------------------------------------
# Robustness transforms applied to the log levels before estimation
# ----------------------------------------------------------------------------
def _hamilton_filter_cycle(log_level: pd.DataFrame, h: int = 24, p: int = 12) -> pd.DataFrame:
    """Hamilton (2018) filter: cyclical = y_{t} - E[y_{t} | y_{t-h}..y_{t-h-p+1}].

    Regress y_{t} on a constant and p lags starting at horizon h (Hamilton's
    preferred h=24, p=12 monthly), per category, and return the residual (the
    filtered cyclical component). Applied column-by-column; categories with too
    few observations are returned as NaN.
    """
    out = pd.DataFrame(np.nan, index=log_level.index, columns=log_level.columns)
    Y = log_level.to_numpy(dtype=float)
    n = len(log_level)
    for c in range(Y.shape[1]):
        y = Y[:, c]
        rows = []
        idx = []
        for t in range(h + p - 1, n):
            if not np.isfinite(y[t]):
                continue
            xs = y[t - h: t - h - p: -1] if (t - h - p) >= -1 else None
            xs = y[t - h - p + 1: t - h + 1][::-1]
            if len(xs) != p or not np.all(np.isfinite(xs)):
                continue
            rows.append((t, xs))
            idx.append(t)
        if len(rows) < p + 2:
            continue
        X = np.column_stack([np.ones(len(rows))] + [np.array([r[1][j] for r in rows]) for j in range(p)])
        yv = np.array([y[t] for t, _ in rows])
        beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
        resid = yv - X @ beta
        for (t, _), e in zip(rows, resid):
            out.iat[t, c] = e
    return out


# ----------------------------------------------------------------------------
# Build the engine inputs
# ----------------------------------------------------------------------------
@dataclass
class DecompPanels:
    log_price: pd.DataFrame
    log_quantity: pd.DataFrame
    inflation: pd.DataFrame
    weights: pd.DataFrame
    categories: list[tuple[str, str]]   # (key, label)
    scope: str


def build_decomp_panels(
    bea: Optional[BeaClient] = None,
    scope: str = "headline",
    spec: str = "levels",
    price_table: str = "U20404",
    quantity_table: str = "U20403",
    nominal_table: str = "U20405",
    explicit_series: Optional[list[str]] = None,
    inflation_method: str = "pct",
    force: bool = False,
) -> DecompPanels:
    """Fetch BEA tables and build the decomposition engine inputs.

    Parameters
    ----------
    scope : "headline" (all pinned categories), "core" (drop food & energy),
            "goods" or "services" (BEA's PCE goods/services split, all-PCE;
            the US analogue of the Canada total/goods/services scopes).
    spec  : "levels" | "diff" | "filter" (Section 3.2 robustness).
    inflation_method : "pct" (Laspeyres-additive, default) or "log" for π_{i,t}.
    """
    bea = bea or BeaClient()
    price = bea_wide(bea, price_table, force=force)
    quantity = bea_wide(bea, quantity_table, force=force)
    nominal = bea_wide(bea, nominal_table, force=force)

    cats = load_categories()
    label_by_key = dict(zip(cats["key"].astype(str), cats["label"].astype(str)))
    keys = explicit_series or list(cats["key"].astype(str))
    if scope == "core":
        excl = core_exclusions()
        keys = [k for k in keys if k not in excl]
    elif scope in ("goods", "services"):
        gs = set(goods_services_keys(scope))
        keys = [k for k in keys if k in gs]
    elif scope != "headline":
        raise ValueError("scope must be 'headline', 'core', 'goods' or 'services'")

    # keep keys present in ALL three tables
    keys = [k for k in keys if k in price.columns and k in quantity.columns and k in nominal.columns]

    p = price[keys].astype(float)
    q = quantity[keys].astype(float)
    nom = nominal[keys].astype(float)

    # π_{i,t} for the contributions (always from the price index)
    inflation = monthly_inflation(p, method=inflation_method)

    # log levels for the regressions, with the requested robustness transform
    log_p = np.log(p)
    log_q = np.log(q)
    if spec == "diff":
        log_p = log_p.diff()
        log_q = log_q.diff()
    elif spec == "filter":
        log_p = _hamilton_filter_cycle(log_p)
        log_q = _hamilton_filter_cycle(log_q)
    elif spec != "levels":
        raise ValueError("spec must be 'levels', 'diff', or 'filter'")

    # expenditure shares ω_{i,t} over the selected set, renormalised each month
    row = nom.sum(axis=1).replace(0, np.nan)
    weights = nom.div(row, axis=0)

    # align all panels on a common monthly index
    common = log_p.index
    for df in (log_q, inflation, weights):
        common = common.intersection(df.index)
    out = lambda d: d.loc[common, keys]
    categories = [(k, label_by_key.get(k, k)) for k in keys]
    return DecompPanels(
        log_price=out(log_p),
        log_quantity=out(log_q),
        inflation=out(inflation),
        weights=out(weights),
        categories=categories,
        scope=scope,
    )
