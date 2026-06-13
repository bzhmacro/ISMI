"""
ism.jp_pipeline
===============

Japan port of the ISM index, built on the Statistics Bureau CPI via the e-Stat
API (2020-base table 0003427113). The momentum engine is unchanged
(`ism.engine.compute_ism`); this module only builds the (inflation_panel,
weights) pair and the Japan control block, per config/sources_japan.yaml.

  category prices  : 2020-base CPI by item (cat01), Japan, monthly, NSA
  category cut     : the medium groups (中分類) = direct children of the 10 major
                     groups, walked from the cat01 parent tree (a true tiling;
                     the @level attribute is unreliable — see
                     select_cat01_partition)
  category weights : static 2020-base CPI weights (per 10000, Laspeyres) from the
                     e-Stat Annual Report item list (statInfId 000032177686);
                     broadcast + renormalised monthly, same fixed-base treatment
                     as the US CPI backbone
  headline         : cat01 0001 "Sogo" (all items)
  recession dummy  : Cabinet Office ESRI official reference dates
  controls         : FRED-based where possible (unemployment, Nikkei, JGB-call
                     spread, Brent) — Japan's equity series needs no S&P
                     fallback since NIKKEI225 is freely on FRED

NOTE: e-Stat requires a free application ID (ESTAT_API_ID in .env). All entry
points fail with a clear message without one; the web exporter skips the jp
backbone gracefully.
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


# The 10 CPI major groups (大分類) of the 2020-base table. The cat01 dimension
# packs THREE overlapping hierarchies into one flat code space — the major-group
# tree, a goods/services recut (財 / サービス) and supplementary 再掲 /
# seasonally-adjusted (季節調整済) aggregates — and its @level attribute is NOT
# consistent across them, so no single @level is a clean partition (a level cut
# double-counts and even mixes in seasonally-adjusted duplicates of the same
# series). We instead tile the index by the medium groups (中分類) = the direct
# children of these majors: mutually exclusive, exhaustive (every one of the
# ~580 items rolls up to exactly one), and the analogue of the UK COICOP-class /
# euro class-level cut used by the other country ports.
JP_MAJOR_GROUPS = ["0002", "0045", "0054", "0060", "0082",
                   "0107", "0111", "0118", "0122", "0145"]


# Static 2020-base CPI weights (per 10000, Laspeyres) for the 47 medium groups,
# transcribed from the e-Stat 2020-base CPI Item Information List (Annual Report
# Appendix 1, statInfId 000032177686, "総合/Japan" weight column). Japan's CPI is
# fixed-base, so these are constant between base revisions; the engine broadcasts
# them across months and renormalises over the categories with a live signal --
# the same static-weights treatment as the US CPI backbone's Dec-2023 relative
# importance. The 10 major groups sum to exactly 10000; the 47 medium groups sum
# to 10004, a few units off only through integer rounding of the published shares
# (immaterial, since weights are renormalised each month).
JP_CPI_WEIGHTS_2020 = {
    # 0002 食料
    "0003": 214, "0008": 199, "0013": 249, "0016": 126, "0021": 285, "0027": 105, "0030": 121, "0033": 236, "0034": 352, "0037": 163, "0041": 119, "0042": 460,
    # 0045 住居
    "0046": 1833, "0051": 316,
    # 0054 光熱・水道
    "0056": 341, "0057": 151, "0058": 38, "0059": 163,
    # 0060 家具・家事用品
    "0061": 132, "0066": 21, "0070": 27, "0073": 74, "0077": 105, "0081": 28,
    # 0082 被服及び履物
    "0083": 152, "0089": 105, "0098": 48, "0103": 29, "0106": 20,
    # 0107 保健医療
    "0108": 128, "0109": 91, "0110": 259,
    # 0111 交通・通信
    "0112": 167, "0113": 885, "0117": 441,
    # 0118 教育
    "0119": 213, "0120": 7, "0121": 84,
    # 0122 教養娯楽
    "0123": 77, "0128": 206, "0134": 110, "0138": 518,
    # 0145 諸雑費
    "0146": 110, "0147": 161, "0151": 63, "0155": 39, "0156": 233,
}


# Official English names for the 47 medium groups, transcribed from the same
# e-Stat 2020-base CPI Item Information List (Appendix 1, statInfId 000032177686,
# English "Items" column). Used for the web labels so the gauge reads in English
# like the other ports; build_jp_cpi_panel falls back to the Japanese e-Stat name
# for any code not present here.
JP_CPI_LABELS_EN = {
    # 0002 Food
    "0003": "Cereals",
    "0008": "Fish & seafood",
    "0013": "Meats",
    "0016": "Dairy products & eggs",
    "0021": "Vegetables & seaweeds",
    "0027": "Fruits",
    "0030": "Oils, fats & seasonings",
    "0033": "Cakes & candies",
    "0034": "Cooked food",
    "0037": "Beverages",
    "0041": "Alcoholic beverages",
    "0042": "Meals outside the home",
    # 0045 Housing
    "0046": "Rent",
    "0051": "Repairs & maintenance",
    # 0054 Fuel, light & water
    "0056": "Electricity",
    "0057": "Gas",
    "0058": "Other fuel & light",
    "0059": "Water & sewerage charges",
    # 0060 Furniture & household utensils
    "0061": "Household durable goods",
    "0066": "Interior furnishings",
    "0070": "Bedding",
    "0073": "Domestic utensils",
    "0077": "Domestic non-durable goods",
    "0081": "Domestic services",
    # 0082 Clothes & footwear
    "0083": "Clothes",
    "0089": "Shirts, sweaters & underwear",
    "0098": "Footwear",
    "0103": "Other clothing",
    "0106": "Services related to clothing",
    # 0107 Medical care
    "0108": "Medicines & health fortification",
    "0109": "Medical supplies & appliances",
    "0110": "Medical services",
    # 0111 Transportation & communication
    "0112": "Public transportation",
    "0113": "Private transportation",
    "0117": "Communication",
    # 0118 Education
    "0119": "School fees",
    "0120": "School textbooks & reference books for study",
    "0121": "Tutorial fees",
    # 0122 Culture & recreation
    "0123": "Recreational durable goods",
    "0128": "Recreational goods",
    "0134": "Books & other reading materials",
    "0138": "Recreational services",
    # 0145 Miscellaneous
    "0146": "Personal care services",
    "0147": "Toilet articles",
    "0151": "Personal effects",
    "0155": "Tobacco",
    "0156": "Other miscellaneous",
}


def select_cat01_partition(classes: pd.DataFrame,
                           majors: Optional[list] = None) -> tuple[pd.DataFrame, str]:
    """Tile the CPI by medium groups (中分類) = direct children of the majors.

    Walks the parent tree rather than trusting @level (which interleaves
    several overlapping hierarchies). Returns (subset, cut_name).
    """
    majors = majors or JP_MAJOR_GROUPS
    cl = classes.dropna(subset=["code"]).copy()
    sel = cl[cl["parent"].isin(majors)]
    if sel.empty:
        raise ValueError("no medium-group children found for the CPI major "
                         "groups — the e-Stat table schema may have changed")
    return sel, "medium-group(chu-bunrui)"


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
    if level is not None:
        sel, level_used = select_cat01_level(classes, level=level)
    else:
        sel, level_used = select_cat01_partition(classes)
    labels = dict(zip(sel["code"], sel["name"].str.replace(r"^\d+\s*", "", regex=True)))
    labels = {c: JP_CPI_LABELS_EN.get(c, labels[c]) for c in labels}
    print(f"[jp] cat01 cut = {level_used}: {len(sel)} categories")

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
    elif set(price.columns) <= set(JP_CPI_WEIGHTS_2020):
        wvec = pd.Series({c: float(JP_CPI_WEIGHTS_2020[c]) for c in price.columns})
        w = pd.DataFrame([wvec.values] * len(price.index),
                         index=price.index, columns=price.columns)
        print(f"[jp] weights: static 2020-base CPI medium-group weights "
              f"(per 10000; sum {int(wvec.sum())}), broadcast + renormalised monthly")
    else:
        missing = sorted(set(price.columns) - set(JP_CPI_WEIGHTS_2020))
        print(f"[jp] WARNING: static weight vector missing {len(missing)} codes "
              f"{missing[:6]} -> UNIFORM weights (unweighted diffusion)")
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
