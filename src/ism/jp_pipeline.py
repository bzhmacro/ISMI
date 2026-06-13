"""
ism.jp_pipeline
===============

Japan port of the ISM index, built on the Statistics Bureau CPI via the e-Stat
API (2020-base table 0003427113). The momentum engine is unchanged
(`ism.engine.compute_ism`); this module only builds the (inflation_panel,
weights) pair and the Japan control block, per config/sources_japan.yaml.

  category prices  : 2020-base CPI by item (cat01), Japan, monthly, NSA
  category cut     : a cat01 LEVEL chosen from the table's CLASS_INF metadata
                     (default: the sub-group / chu-bunrui level — the
                     depth-vs-history trade-off, like class level for the UK)
  category weights : CPI weights (fixed per base revision; static broadcast,
                     same simplification as the US CPI backbone)
  headline         : cat01 0001 "Sogo" (all items)
  recession dummy  : Cabinet Office ESRI official reference dates
  controls         : FRED-based where possible (unemployment, Nikkei, JGB-call
                     spread, Brent) — Japan's equity series needs no S&P
                     fallback since NIKKEI225 is freely on FRED

NOTE: e-Stat requires a free application ID (ESTAT_API_ID in .env). All entry
points fail with a clear message without one; the web exporter skips the jp
backbone gracefully. Codes marked VALIDATE in the config (the weights tab id,
the exact level codes) are confirmed on the first authenticated run — this
module discovers them from metadata and prints what it chose.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .engine import ISMConfig, compute_ism
from .estat import CPI_2020_TABLE, EstatClient
from .transforms import monthly_inflation, threemonth_inflation, yoy_inflation

AREA_JAPAN = "00000"      # zenkoku (whole country)
ALL_ITEMS_CODE = "0001"   # Sogo (all items)


# ---------------------------------------------------------------------------
# Category cut: choose a cat01 level from metadata
# ---------------------------------------------------------------------------
def select_cat01_level(classes: pd.DataFrame, level: Optional[str] = None,
                       min_categories: int = 30) -> tuple[pd.DataFrame, str]:
    """Pick the cat01 classification level to use as the category set.

    `classes` is EstatClient.class_frame(...): code/name/level/unit/parent.
    If `level` is given, use it; otherwise pick the shallowest level with at
    least `min_categories` members (the chu-bunrui sub-group cut lands here).
    All-items (0001) is always excluded. Returns (subset, level_used).
    """
    cl = classes.dropna(subset=["code"]).copy()
    cl = cl[cl["code"] != ALL_ITEMS_CODE]
    if level is None:
        counts = cl.groupby("level")["code"].count().sort_index()
        eligible = [lv for lv, n in counts.items() if n >= min_categories]
        if not eligible:
            raise ValueError(f"no cat01 level has >= {min_categories} members: {dict(counts)}")
        level = eligible[0]
    sel = cl[cl["level"] == level]
    return sel, str(level)


def build_jp_cpi_panel(client: Optional[EstatClient] = None,
                       table_id: str = CPI_2020_TABLE,
                       level: Optional[str] = None,
                       tab_index: Optional[str] = None,
                       fill_interior_gaps: bool = True,
                       force: bool = False):
    """Build (inflation_panel, weights, labels) for Japan from the e-Stat CPI.

    * prices: monthly CPI index per selected cat01 category (Japan, NSA);
      the ``tab`` (presentation item) carrying the *index* is discovered from
      metadata unless given.
    * weights: per-base CPI weights if the table exposes a weights tab, else
      a uniform vector (engine renormalises; uniform = unweighted diffusion —
      printed loudly so it is never a silent fallback).

    Returns aligned (inflation, weights) [months x categories] + {code: name}.
    """
    client = client or EstatClient()

    # --- choose the category cut from metadata --------------------------------
    classes = client.class_frame(table_id, "cat01", force=force)
    sel, level_used = select_cat01_level(classes, level=level)
    labels = dict(zip(sel["code"], sel["name"].str.replace(r"^\d+\s*", "", regex=True)))
    print(f"[jp] cat01 level {level_used}: {len(sel)} categories")

    # --- find the index (and weights) presentation items ----------------------
    tabs = client.class_frame(table_id, "tab", force=force)
    def _find(substrings):
        for _, r in tabs.iterrows():
            nm = str(r["name"])
            if any(s in nm for s in substrings):
                return str(r["code"])
        return None
    tab_idx = tab_index or _find(["指数", "index", "Index"]) or str(tabs.iloc[0]["code"])
    tab_w = _find(["ウエイト", "ウェイト", "weight", "Weight"])
    print(f"[jp] tab: index={tab_idx}" + (f", weights={tab_w}" if tab_w else ", weights=NOT FOUND"))

    # --- fetch values ----------------------------------------------------------
    df = client.stats_data(table_id, {"cdArea": AREA_JAPAN, "cdTab": tab_idx,
                                      "cdCat01": ",".join(sel["code"])}, force=force)
    price = (df.dropna(subset=["date"])
               .pivot_table(index="date", columns="cat01", values="value", aggfunc="first")
               .sort_index())
    price = price.dropna(how="all").asfreq("MS")
    if fill_interior_gaps:
        price = price.interpolate(method="time", limit_area="inside")
    print(f"[jp] price panel: {price.shape[1]} categories x {price.shape[0]} months "
          f"({price.index.min():%Y-%m} -> {price.index.max():%Y-%m})")

    # --- weights ---------------------------------------------------------------
    if tab_w is not None:
        wdf = client.stats_data(table_id, {"cdArea": AREA_JAPAN, "cdTab": tab_w,
                                           "cdCat01": ",".join(sel["code"])}, force=force)
        w = (wdf.dropna(subset=["date"])
                .pivot_table(index="date", columns="cat01", values="value", aggfunc="first")
                .sort_index()
                .reindex(price.index).ffill().bfill())
    else:
        print("[jp] WARNING: no weights tab found -> UNIFORM weights "
              "(unweighted diffusion). Pin a weights table id in "
              "config/sources_japan.yaml after inspecting getMetaInfo.")
        w = pd.DataFrame(1.0, index=price.index, columns=price.columns)

    cols = [c for c in price.columns if c in w.columns]
    price, w = price[cols], w[cols]
    infl = monthly_inflation(price)
    weights = w.where(price.notna())
    weights = weights.div(weights.sum(axis=1).replace(0, np.nan), axis=0)
    common = infl.index.intersection(weights.index)
    return infl.loc[common], weights.loc[common], {c: labels.get(c, c) for c in cols}


def compute_jp_ism(client: Optional[EstatClient] = None, level: Optional[str] = None,
                   cfg: ISMConfig | None = None):
    """End-to-end Japan ISM: returns (ISMResult, inflation_panel, weights)."""
    infl, weights, _ = build_jp_cpi_panel(client, level=level)
    res = compute_ism(infl, weights, cfg or ISMConfig())
    return res, infl, weights


def headline_jp_cpi_yoy(client: Optional[EstatClient] = None,
                        table_id: str = CPI_2020_TABLE, force: bool = False) -> pd.Series:
    """12-month Japan CPI inflation (%) from the all-items (Sogo) index."""
    client = client or EstatClient()
    tabs = client.class_frame(table_id, "tab", force=force)
    tab_idx = next((str(r["code"]) for _, r in tabs.iterrows()
                    if "指数" in str(r["name"])), str(tabs.iloc[0]["code"]))
    df = client.stats_data(table_id, {"cdArea": AREA_JAPAN, "cdTab": tab_idx,
                                      "cdCat01": ALL_ITEMS_CODE}, force=force)
    s = (df.dropna(subset=["date"]).set_index("date")["value"]
           .sort_index().asfreq("MS").interpolate(method="time", limit_area="inside"))
    return yoy_inflation(s)


# ---------------------------------------------------------------------------
# ESRI official business-cycle reference dates (Japan HAS a dating committee)
# ---------------------------------------------------------------------------
# Cabinet Office ESRI peak -> trough, monthly. https://www.esri.cao.go.jp/
JP_RECESSIONS = [
    ("1973-11", "1975-03"),
    ("1977-01", "1977-10"),
    ("1980-02", "1983-02"),
    ("1985-06", "1986-11"),
    ("1991-02", "1993-10"),
    ("1997-05", "1999-01"),
    ("2000-11", "2002-01"),
    ("2008-02", "2009-03"),
    ("2012-03", "2012-11"),
    ("2018-10", "2020-05"),
]


def jp_recession_dummy(index: pd.DatetimeIndex) -> pd.Series:
    """0/1 monthly Japan recession dummy from the ESRI reference dates."""
    d = pd.Series(0.0, index=index, name="recession")
    for start, end in JP_RECESSIONS:
        d.loc[(index >= pd.Timestamp(start + "-01")) & (index <= pd.Timestamp(end + "-01"))] = 1.0
    return d


# ---------------------------------------------------------------------------
# Japan control block (defensive: reports what it could/could not fetch)
# ---------------------------------------------------------------------------
def build_jp_controls(client: Optional[EstatClient] = None, fred=None,
                      month_index: Optional[pd.DatetimeIndex] = None) -> pd.DataFrame:
    """Assemble the Japan control block per config/sources_japan.yaml.

    Each control is attempted independently; failures are reported, not fatal.
    Columns (subset that succeeded):
        cpi_yoy, cpi_3m, unemployment, equity, spread_10y_call, recession
    The openings-to-applicants ratio, inflation expectations and real
    disposable income are added by the notebook (VALIDATE items).
    """
    out = {}

    # Headline CPI -> yoy & 3m (needs e-Stat key)
    try:
        client = client or EstatClient()
        tabs = client.class_frame(CPI_2020_TABLE, "tab")
        tab_idx = next((str(r["code"]) for _, r in tabs.iterrows()
                        if "指数" in str(r["name"])), str(tabs.iloc[0]["code"]))
        df = client.stats_data(CPI_2020_TABLE, {"cdArea": AREA_JAPAN, "cdTab": tab_idx,
                                                "cdCat01": ALL_ITEMS_CODE})
        cpi = (df.dropna(subset=["date"]).set_index("date")["value"].sort_index().asfreq("MS"))
        out["cpi_yoy"] = yoy_inflation(cpi).rename("cpi_yoy")
        out["cpi_3m"] = threemonth_inflation(cpi).rename("cpi_3m")
    except Exception as e:
        print(f"[jp-controls] headline CPI failed: {e}")

    # FRED block: unemployment, Nikkei, 10y JGB - call rate, Brent
    try:
        from .datasources import FredClient
        fred = fred or FredClient()
        def _m(sid):
            s = fred.series(sid)
            s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
            return s.groupby(level=0).mean()
        try:
            out["unemployment"] = _m("LRUNTTTTJPM156S").rename("unemployment")
        except Exception as e:
            print(f"[jp-controls] unemployment failed: {e}")
        try:
            out["equity"] = _m("NIKKEI225").rename("equity")
        except Exception as e:
            print(f"[jp-controls] Nikkei failed: {e}")
        try:
            lt, st = _m("IRLTLT01JPM156N"), _m("IRSTCI01JPM156N")
            out["spread_10y_call"] = (lt - st.reindex(lt.index)).rename("spread_10y_call")
        except Exception as e:
            print(f"[jp-controls] yield spread failed: {e}")
    except Exception as e:
        print(f"[jp-controls] FRED block failed: {e}")

    frame = pd.concat(out.values(), axis=1) if out else pd.DataFrame()
    if month_index is not None and not frame.empty:
        frame = frame.reindex(month_index.union(frame.index)).sort_index().reindex(month_index)
    if not frame.empty:
        frame["recession"] = jp_recession_dummy(frame.index)
    return frame
