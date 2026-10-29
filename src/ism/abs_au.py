"""
ism.abs_au
==========

Australian Bureau of Statistics (ABS) client + parsers for the Australia port.

Three inputs, all keyless:

* **CPI by expenditure class** -- ABS Data API (SDMX), dataflow ``CPI`` v2.0.0,
  index numbers (MEASURE 1), original (TSEST 10), weighted average of the eight
  capital cities (REGION 50), quarterly.  The 87 expenditure classes are the
  leaves of the codelist tree under ``10001`` (All groups CPI); every one has
  an index back to between 1972-Q3 and 1989-Q3.  Quarterly, not monthly: the
  ABS complete monthly CPI only starts in 2024 (some classes 2017), far short of
  a 10-year rolling window, so the long quarterly series is the backbone.

* **CPI weights** -- the expenditure-class weights are published at each
  re-weight (annual since 2018) in dataflow ``CPI_WEIGHTS`` (MEASURE 1 =
  percentage contribution to the All groups CPI at the link quarter), and, from
  2025-Q4, as a contribution to the index number every quarter (``CPI``
  v2.0.0, MEASURE 4).  Earlier re-weights come from 6431.0 *Historical
  Weighting Patterns* (Excel): the 16th (2011) and 17th (2017) series match all
  87 of today's classes by name; the 13th-15th (1998, 2000, 2005) match 31-48,
  and for those the published weights set the *relative* weights of the
  matched classes while the unmatched ones keep their back-updated share (see
  `historical_anchors`).  Between anchors the shares are *price-updated*
  (w_{i,t} ∝ w_{i,a} P_{i,t}/P_{i,a}) -- the ABS's own Lowe-index arithmetic --
  and before the first anchor (1998-Q2) they are back-updated from it.
  Validation: with these anchors the 15% trimmed mean tracks the ABS's own
  at 0.985 correlation (4-quarter rate, 1998-, excluding the four GST
  quarters, which the ABS series strips out); with the 2018+ anchors alone it
  was 0.82.

* **Household final consumption expenditure** -- ABS 5206.0 Table 8 (Excel),
  seventeen categories, seasonally adjusted, current prices and chain volume
  measures, quarterly from 1959-Q3.  The ABS Data API carries no
  consumption-by-purpose dataflow, so the workbook is located on the latest
  release page and parsed by series ID.  Input to the supply/demand
  decomposition port (`ism.decomp_ports.build_au_panels`).

Also: the ABS-published trimmed mean and weighted median (dataflow ``CPI_Q``,
codes 999902 / 999903, seasonally adjusted, quarterly from 1982), which validate the trimmed
mean page -- the RBA's preferred underlying measures.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, _request, _write_provenance

RAW_ABS = REPO_ROOT / "data" / "raw" / "abs"
API = "https://data.api.abs.gov.au/rest"
CPI_FLOW = "ABS,CPI,2.0.0"
CPI_WEIGHTS_FLOW = "ABS,CPI_WEIGHTS,1.0.0"
CPI_Q_FLOW = "ABS,CPI_Q,1.0.0"     # seasonally adjusted + underlying measures
ALL_GROUPS = "10001"
TRIMMED_MEAN, WEIGHTED_MEDIAN = "999902", "999903"
NA_RELEASE = ("https://www.abs.gov.au/statistics/economy/national-accounts/"
              "australian-national-accounts-national-income-expenditure-and-product/"
              "latest-release")
ABS_SITE = "https://www.abs.gov.au"
#: 6431.0 Consumer Price Index: Historical Weighting Patterns, 1948-2017 (Excel).
HIST_WEIGHTS_URL = ("https://www.abs.gov.au/AUSSTATS/SUBSCRIBER.NSF/log?openagent&"
                    "64310.xls&6431.0&Data%20Cubes&CC62C29F81127515CA258225000D7DF9&0&"
                    "1948%20-%202017&31.01.2018&Latest")
#: Link quarter (quarter start) of each CPI series whose expenditure classes can
#: be matched to today's by name: 13th-15th partly (31-48 of 87 classes), 16th
#: and 17th fully.  Earlier series (10th-12th) match fewer than 20 classes and add
#: nothing measurable, so they are not used.
HIST_SERIES = {"13th series": "1998-04", "14th series": "2000-04",
               "15th series": "2005-04", "16th series": "2011-04",
               "17th series": "2017-07"}

#: 5206.0 Table 8: the seventeen seasonally adjusted HFCE categories.
#: key -> (label, current-price series ID, chain-volume series ID).  IDs read off
#: the workbook (row 9 of Data1); pinned so a re-ordered workbook cannot swap
#: two categories silently.
HFCE_SA = {
    "food":      ("Food", "A2302219R", "A2303246R"),
    "tobacco":   ("Cigarettes and tobacco", "A2302220X", "A2303248V"),
    "alcohol":   ("Alcoholic beverages", "A2302221A", "A2303250F"),
    "clothing":  ("Clothing and footwear", "A2302222C", "A2303252K"),
    "rent":      ("Rent and other dwelling services", "A2302223F", "A2303254R"),
    "energy":    ("Electricity, gas and other fuel", "A2302224J", "A2303256V"),
    "furnish":   ("Furnishings and household equipment", "A2302225K", "A2303258X"),
    "health":    ("Health", "A2302226L", "A2303260K"),
    "vehicles":  ("Purchase of vehicles", "A2302227R", "A2303262R"),
    "vehops":    ("Operation of vehicles", "A2302228T", "A2303264V"),
    "transport": ("Transport services", "A2302229V", "A2303266X"),
    "comms":     ("Communications", "A2302230C", "A2303268C"),
    "recreation": ("Recreation and culture", "A2302231F", "A2303270R"),
    "education": ("Education services", "A2302232J", "A2303272V"),
    "hotels":    ("Hotels, cafes and restaurants", "A2302233K", "A2303274X"),
    "finance":   ("Insurance and other financial services", "A2302234L", "A2303276C"),
    "other":     ("Other goods and services", "A2302235R", "A2303278J"),
}


# ---------------------------------------------------------------------------
# transport (cached, with provenance sidecars)
# ---------------------------------------------------------------------------
def _cache(name: str) -> Path:
    RAW_ABS.mkdir(parents=True, exist_ok=True)
    return RAW_ABS / name


def _get_bytes(url: str, name: str, headers: Optional[dict] = None,
               force: bool = False) -> bytes:
    path = _cache(name)
    if path.exists() and not force:
        return path.read_bytes()
    resp = _request("GET", url, provider="abs", headers=headers, timeout=180)
    path.write_bytes(resp.content)
    _write_provenance(path, url, {})
    return resp.content


def sdmx_csv(flow: str, key: str = "all", name: Optional[str] = None,
             force: bool = False) -> pd.DataFrame:
    """One ABS Data API query as a tidy frame (SDMX-CSV)."""
    name = name or re.sub(r"[^A-Za-z0-9]+", "_", f"{flow}_{key}") + ".csv"
    raw = _get_bytes(f"{API}/data/{flow}/{key}?format=csv", name,
                     headers={"Accept": "application/vnd.sdmx.data+csv"}, force=force)
    df = pd.read_csv(io.BytesIO(raw), dtype={"INDEX": str}, low_memory=False)
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    return df


def _quarter(code) -> pd.Timestamp:
    y, q = str(code).split("-Q")
    return pd.Timestamp(int(y), 3 * int(q) - 2, 1)


def cpi_codelist(force: bool = False) -> pd.DataFrame:
    """The CPI index codelist: id, name, parent (the ABS tree, in ABS order)."""
    raw = _get_bytes(f"{API}/dataflow/ABS/CPI/2.0.0?references=all&detail=full",
                     "cpi_structure.json",
                     headers={"Accept": "application/vnd.sdmx.structure+json"},
                     force=force)
    data = json.loads(raw)["data"]
    cl = next(c for c in data["codelists"] if c["id"] == "CL_CPI_INDEX")
    return pd.DataFrame([{"id": c["id"], "name": c["name"], "parent": c.get("parent")}
                         for c in cl["codes"]])


def cpi_tree(force: bool = False):
    """(leaves in tree order, labels, group-of-leaf) for the All groups tree."""
    cl = cpi_codelist(force=force)
    par = dict(zip(cl["id"], cl["parent"]))
    name = dict(zip(cl["id"], cl["name"]))

    def chain(c):
        out = [c]
        while par.get(out[-1]):
            out.append(par[out[-1]])
        return out

    in_tree = [c for c in cl["id"] if chain(c)[-1] == ALL_GROUPS and c != ALL_GROUPS]
    parents = {par[c] for c in in_tree}
    leaves = [c for c in in_tree if c not in parents]
    # the group is the ancestor directly under All groups
    group = {c: name[chain(c)[-2]] for c in leaves}
    return leaves, {c: name[c] for c in leaves}, group


# ---------------------------------------------------------------------------
# CPI panel
# ---------------------------------------------------------------------------
def _wide(df: pd.DataFrame, measure: int) -> pd.DataFrame:
    sel = df[(df["MEASURE"] == measure) & (df["REGION"] == 50) & (df["FREQ"] == "Q")]
    if "TSEST" in sel.columns:
        sel = sel[sel["TSEST"] == 10]
    w = sel.pivot_table(index="TIME_PERIOD", columns="INDEX", values="OBS_VALUE",
                        aggfunc="first")
    w.index = [_quarter(t) for t in w.index]
    return w.sort_index()


def cpi_index_panel(force: bool = False) -> pd.DataFrame:
    """Quarterly index numbers, every CPI code (original, eight capitals)."""
    df = sdmx_csv(CPI_FLOW, "1+4..10.50.Q", name="cpi_v2_q.csv", force=force)
    return _wide(df, 1)


def weight_anchors(leaves: list[str], force: bool = False) -> dict:
    """{quarter: share Series over `leaves`} from every published weight."""
    anchors = {}
    w = sdmx_csv(CPI_WEIGHTS_FLOW, "all", name="cpi_weights.csv", force=force)
    w = w[(w["MEASURE"] == 1) & (w["REGION"] == 50)]
    for t, g in w.groupby("TIME_PERIOD"):
        s = g.set_index("INDEX")["OBS_VALUE"].reindex(leaves)
        if s.notna().sum() >= 0.9 * len(leaves):
            anchors[_quarter(t)] = s / s.sum()
    # quarterly contributions to the index number from the v2 series (2025-Q4+)
    df = sdmx_csv(CPI_FLOW, "1+4..10.50.Q", name="cpi_v2_q.csv", force=force)
    contrib = _wide(df, 4).reindex(columns=leaves)
    for t, row in contrib.iterrows():
        if row.notna().sum() >= 0.9 * len(leaves):
            anchors[t] = row / row.sum()
    return dict(sorted(anchors.items()))


def _norm(name) -> str:
    s = re.sub(r"\band\b|\(.*?\)", "", str(name).lower())
    return re.sub(r"[^a-z]", "", s)


def historical_anchors(price: pd.DataFrame, labels: dict, anchors: dict,
                       force: bool = False) -> dict:
    """Add the 13th-17th series re-weights (6431.0) to `anchors`, newest first.

    For a series whose classes match today's only in part, the anchor is the
    back-updated vector b (from the next later anchor) with the matched classes'
    *combined* share kept and *split* in the published proportions:

        w_i = (Σ_{j∈M} b_j) · p_i / Σ_{j∈M} p_j   (i ∈ M),     w_i = b_i  (i ∉ M)

    so the published pattern decides relative weights where it can be read,
    and nothing is inferred from classes that no longer exist (mortgage interest
    charges left the CPI in 1998; their weight is not reassigned).
    """
    raw = _get_bytes(HIST_WEIGHTS_URL, "6431_historical_weights.xls", force=force)
    book = pd.ExcelFile(io.BytesIO(raw))
    by_name = {_norm(v): k for k, v in labels.items()}
    out = dict(anchors)
    for sheet, link in sorted(HIST_SERIES.items(), key=lambda kv: kv[1], reverse=True):
        t = pd.Timestamp(link + "-01")
        if t not in price.index:
            continue
        d = pd.read_excel(book, sheet_name=sheet, header=None)
        vals = pd.to_numeric(d[5], errors="coerce")
        rows = d[vals.notna()]
        pub = {}
        for name, v in zip(rows[2], pd.to_numeric(rows[5])):
            k = by_name.get(_norm(name))
            if k is not None:
                pub[k] = float(v)
        later = min(a for a in out if a > t)
        b = out[later] * price.loc[t] / price.loc[later]
        b = b / b.sum()
        m = [k for k in pub if pd.notna(b.get(k))]
        if not m:
            continue
        p = pd.Series(pub)[m]
        w = b.copy()
        w[m] = b[m].sum() * p / p.sum()
        out[t] = w / w.sum()
    return dict(sorted(out.items()))


def price_updated_weights(price: pd.DataFrame, anchors: dict) -> pd.DataFrame:
    """Shares at every quarter from the last anchor at or before it (Lowe).

    w_{i,t} ∝ w_{i,a} · P_{i,t}/P_{i,a},  a = latest anchor ≤ t; quarters before
    the first anchor are back-updated from it.  Renormalised over the classes
    priced at t.
    """
    keys = sorted(anchors)
    out = pd.DataFrame(np.nan, index=price.index, columns=price.columns)
    for t in price.index:
        prior = [a for a in keys if a <= t]
        a = prior[-1] if prior else keys[0]
        if a not in price.index:
            continue
        w = anchors[a].reindex(price.columns) * price.loc[t] / price.loc[a]
        out.loc[t] = w / w.sum()
    return out


def build_au_cpi_panel(force: bool = False):
    """(inflation q/q %, weights, labels, groups, headline 4-quarter %)."""
    leaves, labels, groups = cpi_tree(force=force)
    idx = cpi_index_panel(force=force)
    price = idx.reindex(columns=leaves).dropna(how="all", axis=1)
    price = price.dropna(how="all", axis=0)   # All groups runs from 1948; classes from 1972
    leaves = list(price.columns)
    anchors = weight_anchors(leaves, force=force)
    try:
        anchors = historical_anchors(price, {k: labels[k] for k in leaves}, anchors,
                                     force=force)
    except Exception as exc:                          # noqa: BLE001
        print(f"[au] historical weighting patterns unavailable ({exc}); "
              "back-updating from 2018")
    weights = price_updated_weights(price, anchors)
    weights = weights.where(price.notna())
    weights = weights.div(weights.sum(axis=1).replace(0, np.nan), axis=0)
    infl = 100.0 * np.log(price).diff()
    headline = 100.0 * (idx[ALL_GROUPS] / idx[ALL_GROUPS].shift(4) - 1.0)
    first = min(anchors)
    print(f"[au] ABS CPI: {len(leaves)} expenditure classes, "
          f"{price.index[0]:%Y-%m}..{price.index[-1]:%Y-%m}; "
          f"{len(anchors)} weight anchors from {first:%Y-%m}")
    return infl, weights, labels, groups, headline, first


def official_underlying(force: bool = False) -> pd.DataFrame:
    """ABS trimmed mean + weighted median, SA: q/q annualised and 4-quarter %."""
    df = sdmx_csv(CPI_Q_FLOW, f"1+2+3.{TRIMMED_MEAN}+{WEIGHTED_MEDIAN}.20.50.Q",
                  name="cpi_v2_underlying.csv", force=force)
    out = {}
    for code, tag in ((TRIMMED_MEAN, "trim"), (WEIGHTED_MEDIAN, "median")):
        g = df[df["INDEX"] == code]
        for m, suffix in ((2, "qoq"), (3, "yoy")):
            s = g[g["MEASURE"] == m].set_index("TIME_PERIOD")["OBS_VALUE"]
            s.index = [_quarter(t) for t in s.index]
            out[f"{tag}_{suffix}"] = s.sort_index()
    frame = pd.DataFrame(out)
    for tag in ("trim", "median"):
        frame[f"{tag}_saar"] = 100.0 * ((1 + frame[f"{tag}_qoq"] / 100.0) ** 4 - 1.0)
    return frame


# ---------------------------------------------------------------------------
# HFCE (5206.0 Table 8)
# ---------------------------------------------------------------------------
def _table8_url(force: bool = False) -> str:
    html = _get_bytes(NA_RELEASE, "5206_latest_release.html", force=force).decode(
        "utf-8", "replace")
    m = re.search(r'href="([^"]*5206008[^"]*\.xlsx)"', html, flags=re.I)
    if not m:
        raise RuntimeError("5206.0 Table 8 link not found on the ABS release page")
    href = m.group(1)
    return href if href.startswith("http") else ABS_SITE + href


def au_hce_panels(force: bool = False):
    """(nominal, volume, labels): 17 SA HFCE categories, quarterly, A$m."""
    url = _table8_url(force=force)
    raw = _get_bytes(url, "5206008_hfce.xlsx", force=force)
    data = pd.read_excel(io.BytesIO(raw), sheet_name="Data1", header=None)
    ids = data.iloc[9, 1:].astype(str).tolist()
    body = data.iloc[10:, :].copy()
    dates = pd.to_datetime(body.iloc[:, 0], errors="coerce")
    col = {sid: j + 1 for j, sid in enumerate(ids)}
    # ABS stamps a quarter with its LAST month (Sep-1959); move to quarter start
    qidx = dates.dt.to_period("Q").dt.to_timestamp()
    nominal, volume = {}, {}
    for key, (_, cp, cvm) in HFCE_SA.items():
        if cp not in col or cvm not in col:
            raise RuntimeError(f"5206.0 Table 8: series {cp}/{cvm} not found")
        nominal[key] = pd.to_numeric(body.iloc[:, col[cp]], errors="coerce").to_numpy()
        volume[key] = pd.to_numeric(body.iloc[:, col[cvm]], errors="coerce").to_numpy()
    nominal = pd.DataFrame(nominal, index=qidx).dropna(how="all")
    volume = pd.DataFrame(volume, index=qidx).dropna(how="all")
    labels = {k: v[0] for k, v in HFCE_SA.items()}
    return nominal, volume, labels
