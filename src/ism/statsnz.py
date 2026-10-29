"""
ism.statsnz
===========

Stats NZ (Tatauranga Aotearoa) client + parsers for the New Zealand port.

Stats NZ's API (Aotearoa Data Explorer) needs a subscription key, but every
quarterly release ships its full time series as plain CSV ("Infoshare data"),
which is what this module reads.  No key, no account.

* **CPI by class** -- the CPI release's ``*-index-numbers.csv``: every published
  CPI series since 1914, including the 108 level-3 *classes* (series
  ``CPIQ.SE9GGSCC``: GG group, S subgroup, CC class).  Quarterly.  About half
  the classes start in 1999-Q2 (the 1999 basket re-classification), the rest
  between 1974 and 1989.

* **CPI weights** -- Stats NZ publishes class weights only in the CPI *review*
  tables: June 2014, September 2017, June 2020 (review 2020) and
  December 2024 (review 2024).  Weights are matched to classes by name (the
  review tables carry no series reference), price-updated between reviews and
  back-updated before 2014-Q2.  Classes that are their own subgroup (code
  ending ``00``) appear in the tables at subgroup level, which is why both
  name columns are read.

* **HFCE by purpose** -- the GDP release CSV: household final consumption by
  COICOP division, seasonally adjusted, nominal and chain volume, quarterly
  from 1987-Q2.  Ten usable divisions: Stats NZ suppresses health (06) and
  education (10) as CONFIDENTIAL in the seasonally adjusted series, so they
  arrive empty and are dropped.  The thirteenth line, "imports of low value
  goods purchased directly by households", is a delivery channel rather than a
  purpose (it starts 2000) and is left out.

Release pages are found from the indicator pages, so a new quarter is picked up
without editing a URL.
"""

from __future__ import annotations

import io
import re
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, _request, _write_provenance

RAW_NZ = REPO_ROOT / "data" / "raw" / "statsnz"
SITE = "https://www.stats.govt.nz"
UA = {"User-Agent": "Mozilla/5.0 (ISM replication; +https://github.com/bzhmacro/ISMI)"}

CPI_INDICATOR = f"{SITE}/indicators/consumers-price-index-cpi/"
GDP_INDICATOR = f"{SITE}/indicators/gross-domestic-product-gdp/"
#: The two CPI-review workbooks that carry class-level expenditure weights.
REVIEW_TABLES = {
    "review2020": f"{SITE}/assets/Uploads/Reports/Consumers-price-index-review-2020/"
                  "Download-data/consumers-price-index-review-2020-tables.xlsx",
    "review2024": f"{SITE}/assets/Methods/Consumers-price-indexes-review-2024/"
                  "consumers-price-index-review-2024-tables.xlsx",
}
ALL_GROUPS = "CPIQ.SE9A"
#: review-table name -> CPI class title, where the two disagree
NAME_ALIASES = {
    "purchase of new housing": "purchase of housing",
    "pet-related products": "pets and pet-related products",
    "overseas accommodation costs prepaid in new zealand":
        "overseas accommodation prepaid in new zealand",
}
#: GDP release: SA household FCE by item (COICOP division 01..12)
HFCE_DIVISIONS = [f"{i:02d}" for i in range(1, 13)]

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
def _get(url: str, name: str, force: bool = False) -> bytes:
    RAW_NZ.mkdir(parents=True, exist_ok=True)
    path = RAW_NZ / name
    if path.exists() and not force:
        return path.read_bytes()
    resp = _request("GET", url, provider="statsnz", headers=UA, timeout=180)
    path.write_bytes(resp.content)
    _write_provenance(path, url, {})
    return resp.content


def _latest_release(indicator_url: str, stem: str, force: bool = False) -> str:
    """URL of the most recent '<stem>-<month>-<year>-quarter' release page."""
    html = _get(indicator_url, f"{stem}_indicator.html", force=force).decode("utf-8", "replace")
    html = html.replace("\\/", "/")
    slugs = set(re.findall(rf"/information-releases/({stem}-([a-z]+)-(\d{{4}})-quarter)/", html))
    if not slugs:
        raise RuntimeError(f"no {stem} release linked from {indicator_url}")
    slug = max(slugs, key=lambda s: (int(s[2]), _MONTHS.get(s[1], 0)))[0]
    return f"{SITE}/information-releases/{slug}/"


def _release_document(release_url: str, pattern: str, force: bool = False) -> str:
    slug = release_url.rstrip("/").rsplit("/", 1)[-1]
    html = _get(release_url, f"{slug}.html", force=force).decode("utf-8", "replace")
    html = html.replace("\\/", "/").replace("&quot;", '"')
    links = re.findall(r'"DocumentLink":"([^"]+)"', html)
    hit = [l for l in links if re.search(pattern, l)]
    if not hit:
        raise RuntimeError(f"no document matching {pattern!r} on {release_url}")
    return SITE + hit[0]


def _infoshare(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), dtype={"Period": str}, encoding="utf-8-sig")
    df["value"] = pd.to_numeric(df["Data_value"], errors="coerce")
    # Infoshare periods are YYYY.MM with MM the LAST month of the quarter
    y = df["Period"].str.slice(0, 4).astype(int)
    m = df["Period"].str.slice(5, 7).astype(int)
    df["date"] = pd.to_datetime(dict(year=y, month=m - 2, day=1))
    return df


# ---------------------------------------------------------------------------
# CPI
# ---------------------------------------------------------------------------
def cpi_frame(force: bool = False) -> pd.DataFrame:
    rel = _latest_release(CPI_INDICATOR, "consumers-price-index", force=force)
    url = _release_document(rel, r"-index-numbers\.csv$", force=force)
    return _infoshare(_get(url, "cpi_index_numbers.csv", force=force))


def _norm(name) -> str:
    s = re.sub(r"\(\d+\)", "", str(name)).strip().lower()
    s = NAME_ALIASES.get(s, s)
    return re.sub(r"[^a-z]", "", re.sub(r"\band\b", "", s))


def review_weights(force: bool = False) -> pd.DataFrame:
    """[review quarter x normalised name] class weights (percent), all reviews."""
    out = {}
    for tag, url in REVIEW_TABLES.items():
        raw = _get(url, f"cpi_{tag}_tables.xlsx", force=force)
        t = pd.read_excel(io.BytesIO(raw), sheet_name="Table 1", header=None)
        hdr_row = t.index[t.iloc[:, 4].astype(str).str.match(r"^[A-Z][a-z]+ \d{4}$")][0]
        cols = [c for c in (4, 6, 8) if isinstance(t.iloc[hdr_row, c], str)]
        for _, r in t.iloc[hdr_row + 1:].iterrows():
            name = r[2] if isinstance(r[2], str) else r[1] if isinstance(r[1], str) else None
            if name is None:
                continue
            for c in cols:
                v = pd.to_numeric(r[c], errors="coerce")
                if np.isfinite(v):
                    q = pd.Period(pd.Timestamp(t.iloc[hdr_row, c]), "Q").to_timestamp()
                    out.setdefault(q, {})[_norm(name)] = float(v)
    return pd.DataFrame(out).T.sort_index()


def build_nz_cpi_panel(force: bool = False):
    """(inflation q/q %, weights, labels, groups, headline 4-quarter %, first anchor)."""
    df = cpi_frame(force=force)
    cls = df[df["Group"] == "CPI Level 3 Classes for New Zealand"]
    titles = cls.drop_duplicates("Series_reference").set_index("Series_reference")["Series_title_1"]
    price = cls.pivot_table(index="date", columns="Series_reference", values="value",
                            aggfunc="first").sort_index()
    price = price.where(price > 0)                       # 0 = not published
    grp_frame = df[df["Group"] == "CPI Level 1 Groups for New Zealand"]
    group_names = (grp_frame.drop_duplicates("Series_reference")
                   .set_index("Series_reference")["Series_title_1"].to_dict())

    rw = review_weights(force=force)
    keys = [k for k in price.columns if _norm(titles[k]) in rw.columns]
    dropped = sorted(set(price.columns) - set(keys))
    # a class must still be in the latest basket to be carried
    latest = rw.iloc[-1]
    keys = [k for k in keys if np.isfinite(latest.get(_norm(titles[k]), np.nan))]
    price = price[keys].dropna(how="all", axis=0)
    anchors = {}
    for q, row in rw.iterrows():
        s = pd.Series({k: row.get(_norm(titles[k]), np.nan) for k in keys})
        if s.notna().sum() >= 0.9 * len(keys):
            anchors[q] = s / s.sum()
    from .abs_au import price_updated_weights
    weights = price_updated_weights(price, anchors).where(price.notna())
    weights = weights.div(weights.sum(axis=1).replace(0, np.nan), axis=0)
    infl = 100.0 * np.log(price).diff()

    head = df[df["Series_reference"] == ALL_GROUPS].set_index("date")["value"].sort_index()
    head = head.where(head > 0)
    headline = 100.0 * (head / head.shift(4) - 1.0)
    labels = {k: str(titles[k]) for k in keys}
    groups = {k: group_names.get(k[:10], k[:10]) for k in keys}   # CPIQ.SE9GG
    first = min(anchors)
    print(f"[nz] Stats NZ CPI: {len(keys)} classes ({len(dropped)} without a review "
          f"weight dropped), {price.index[0]:%Y-%m}..{price.index[-1]:%Y-%m}; "
          f"{len(anchors)} weight anchors from {first:%Y-%m}")
    return infl, weights, labels, groups, headline, first


# ---------------------------------------------------------------------------
# HFCE (GDP release)
# ---------------------------------------------------------------------------
def nz_hce_panels(force: bool = False):
    """(nominal, volume, labels): 12 SA HFCE divisions, quarterly, NZ$m."""
    rel = _latest_release(GDP_INDICATOR, "gross-domestic-product", force=force)
    url = _release_document(rel, r"gross-domestic-product-[a-z]+-\d{4}-quarter\.csv$",
                            force=force)
    df = _infoshare(_get(url, "gdp.csv", force=force))
    out, labels = {}, {}
    for kind, code in (("nominal", "N"), ("volume", "R")):
        frame = {}
        for div in HFCE_DIVISIONS:
            ref = f"SNEQ.SG02{code}SC14P30A{div}E"
            s = df[df["Series_reference"] == ref]
            if s.empty:
                raise RuntimeError(f"GDP release: series {ref} missing")
            frame[f"CP{div}"] = s.set_index("date")["value"]
            labels[f"CP{div}"] = str(s["Series_title_2"].iloc[0])
        out[kind] = pd.DataFrame(frame).sort_index()
    return out["nominal"], out["volume"], labels
