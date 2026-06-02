"""
ism.pipeline
============

Turn raw provider data into the two objects the engine needs:

    inflation_panel : DataFrame [months x categories]  (pi_{i,t}, Eq. 3 input)
    weights         : DataFrame [months x categories]  (w_{i,t}, Eqs. 6-7 input)

plus a tidy `controls` frame for the forecasting / local-projection stages.

The category panel is built from the BEA "Underlying Detail" tables:
    * 2.4.4U (U20404): price indexes  -> monthly category inflation
    * 2.4.5U (U20405): nominal PCE ($)-> expenditure weights

Selecting the "fourth level of disaggregation" (the 129 categories of the paper)
-------------------------------------------------------------------------------
BEA tables are hierarchical. The depth of a row is encoded by the leading
whitespace of its LineDescription (BEA's indentation convention). We expose
`select_leaf_categories(..., level=4)` which selects rows at the requested depth.
Because the exact tree must be confirmed against the live table (the count
should equal 129), the function logs the count and you can either (a) trust the
auto-detected level, or (b) pin an explicit SeriesCode list in
config/categories.yaml. The engine is robust to N != 129; it just changes the
basket, so the guardrail is informational.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import BeaClient, REPO_ROOT
from .transforms import monthly_inflation


# ----------------------------------------------------------------------------
# BEA table -> wide panel
# ----------------------------------------------------------------------------
def _bea_long_to_wide(df: pd.DataFrame, value_col: str = "DataValue") -> pd.DataFrame:
    """Pivot a BEA 'Data' frame into [month x category] using SeriesCode columns.

    The BEA monthly TimePeriod looks like '1959M02'. We convert to a month-start
    Timestamp. Categories are keyed by SeriesCode (stable) but we keep a
    code->description map as an attribute for readability.
    """
    df = df.copy()
    # Parse '1959M02' -> Timestamp('1959-02-01').
    tp = df["TimePeriod"].astype(str)
    df["date"] = pd.to_datetime(
        tp.str.replace("M", "-", regex=False) + "-01", format="%Y-%m-%d", errors="coerce"
    )
    wide = df.pivot_table(index="date", columns="SeriesCode", values=value_col, aggfunc="first")
    wide = wide.sort_index()

    # Attach a human-readable code -> description map for inspection.
    desc = (
        df.dropna(subset=["SeriesCode"])
        .groupby("SeriesCode")["LineDescription"]
        .first()
        .to_dict()
    )
    wide.attrs["descriptions"] = desc
    # Preserve table row order (depth detection needs the original indentation).
    order = df.drop_duplicates("SeriesCode")[["SeriesCode", "LineDescription"]]
    wide.attrs["row_order"] = list(order["SeriesCode"])
    wide.attrs["indent"] = {
        r.SeriesCode: len(str(r.LineDescription)) - len(str(r.LineDescription).lstrip())
        for r in order.itertuples()
    }
    return wide


def select_leaf_categories(
    price_wide: pd.DataFrame,
    level: int = 4,
    explicit_series: Optional[list[str]] = None,
    verbose: bool = True,
) -> list[str]:
    """Return the SeriesCodes at the requested hierarchy depth.

    Depth is inferred from LineDescription indentation captured in
    `price_wide.attrs['indent']`. BEA uses a consistent indent step; we map the
    sorted distinct indents to levels 1,2,3,4,...

    If `explicit_series` is given it is returned as-is (after intersection with
    available columns) -- this is the escape hatch for pinning the exact paper
    category set from config/categories.yaml.
    """
    if explicit_series:
        cats = [c for c in explicit_series if c in price_wide.columns]
        if verbose:
            print(f"[pipeline] using {len(cats)} explicit categories from config")
        return cats

    indent = price_wide.attrs.get("indent", {})
    if not indent:
        raise ValueError("No indentation metadata; cannot infer hierarchy level.")
    distinct = sorted(set(indent.values()))
    indent_to_level = {ind: lvl + 1 for lvl, ind in enumerate(distinct)}
    cats = [code for code, ind in indent.items() if indent_to_level[ind] == level]
    if verbose:
        print(
            f"[pipeline] level={level}: selected {len(cats)} categories "
            f"(expected 129 per paper). distinct indents -> levels: {indent_to_level}"
        )
    return cats


# ----------------------------------------------------------------------------
# Build the engine inputs
# ----------------------------------------------------------------------------
def build_category_panel(
    bea: Optional[BeaClient] = None,
    price_table: str = "U20404",
    nominal_table: str = "U20405",
    level: int = 4,
    inflation_method: str = "log",
    explicit_series: Optional[list[str]] = None,
    force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch BEA tables and build (inflation_panel, weights).

    weights w_{i,t} = nominal_{i,t} / sum_j nominal_{j,t}  over selected categories.

    Returns
    -------
    inflation_panel, weights : aligned DataFrames [months x categories].
    """
    bea = bea or BeaClient()
    price_raw = bea.table(price_table, force=force)
    nominal_raw = bea.table(nominal_table, force=force)

    price_wide = _bea_long_to_wide(price_raw)
    nominal_wide = _bea_long_to_wide(nominal_raw)

    cats = select_leaf_categories(price_wide, level=level, explicit_series=explicit_series)
    # Keep only categories present in BOTH price and nominal tables.
    cats = [c for c in cats if c in nominal_wide.columns]

    price = price_wide[cats]
    nominal = nominal_wide.reindex(columns=cats)

    inflation_panel = monthly_inflation(price, method=inflation_method)

    # Expenditure weights, renormalised each month over available categories.
    row_tot = nominal.sum(axis=1)
    weights = nominal.div(row_tot.replace(0, np.nan), axis=0)

    # Align indexes.
    common = inflation_panel.index.intersection(weights.index)
    return inflation_panel.loc[common], weights.loc[common]


def save_panel(inflation_panel: pd.DataFrame, weights: pd.DataFrame, out_dir: Optional[Path] = None):
    """Persist the engine inputs to data/processed for reuse / audit."""
    out_dir = out_dir or (REPO_ROOT / "data" / "processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    inflation_panel.to_parquet(out_dir / "category_inflation.parquet")
    weights.to_parquet(out_dir / "category_weights.parquet")
    print(f"[pipeline] saved panels to {out_dir}")
