"""
ism.cpi_ri
==========

**Versioned CPI weights.**  Time-varying relative importances for the BLS CPI
item strata, replacing the single static Dec-2023 vector that
:mod:`ism.cpi_pipeline` shipped originally.

Why this exists
---------------
The PCE backbone gets a genuinely monthly weight panel for free: BEA publishes
nominal dollar spending per category every month (table 2.4.5U), so
``w_{i,t}`` in the ISM engine is a real monthly expenditure share.  The CPI has
no such series -- BLS publishes *relative importances*, and only once a year.
A single vector broadcast across seven decades is fine for a diffusion index
that renormalises anyway, but it is not fine for a **trimmed mean**, where the
weights decide where the trim points fall.  Using 2023 weights to locate the
trim point in 1975 puts a 2023-sized shelter weight and a 2023-sized (tiny)
food weight into a 1975 cross-section, which is simply the wrong distribution.

What a relative importance actually is
--------------------------------------
The CPI is a modified Laspeyres index.  Category i enters with a *cost weight*:
base-period expenditure carried forward by that category's own price change.
The relative importance published for December of year Y is exactly that cost
weight, normalised to 100:

    RI_{i,Dec Y} = 100 * ( E_{i,b} * (P_{i,Dec Y} / P_{i,b}) )
                       / sum_j ( E_{j,b} * (P_{j,Dec Y} / P_{j,b}) )

and it is the base from which the index is computed through the *following*
calendar year.  Two consequences that this module leans on:

1. **Within a weight regime the whole path is recoverable.**  Given the
   December-Y table and the item price indexes, the relative importance in any
   month t of year Y+1 is the December weight price-updated to t:

       RI_{i,t} = RI_{i,Dec Y} * (P_{i,t} / P_{i,Dec Y})   / (normalise)   (W1)

   No extra data is needed -- the price indexes are already in the repo.  This
   is not an approximation of BLS's method; it *is* BLS's method.

2. **The regime changes each January**, when a new expenditure base is
   introduced (biennial until 2022, annual since 2023).  Eq. (W1) therefore
   restarts from each published December anchor rather than compounding across
   the join.  The gap between the price-updated December-(Y+1) weight and the
   *published* December-(Y+1) weight is the pure **weight-update effect**, and
   :func:`weight_update_effect` reports it.

Coverage
--------
BLS publishes the December tables from 1987, but the CPI **item structure was
revised in January 1998** and the ``SE*`` item strata this repo pins belong to
the post-revision structure.  Anchors are therefore read from **December 1997
onward** (the ``USRINEW`` table, the first published on the new structure).
Before 1998 the weights are back-updated from the Dec-1997 anchor by Eq. (W1)
run in reverse -- a documented approximation: it holds the 1997 expenditure
basket fixed in real terms, so it captures relative *price* drift but not the
genuine basket changes of the 1970s and 1980s.  ``weights_source`` in the output
records which regime every month came from, and the website labels the
back-updated span.

Sources (all free, no key)
--------------------------
* December tables 2020- : ``.../cpi/tables/relative-importance/<year>.xlsx``
* December tables 1997-2019 : the archive zips ``ri-archive-1990-1999.zip``,
  ``ri-archive-2000-2009.zip``, ``ri-archive-2010-2019.zip`` (fixed-width text)
* current month : ``.../web/cpi/cpi-relative-importance.xlsx``

The parsed anchors are pinned into ``config/cpi_ri_by_year.csv`` by
``scripts/build_cpi_ri.py`` so the pipeline runs offline and the numbers are
reviewable in a diff.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, fetch_url_bytes

RI_CSV = REPO_ROOT / "config" / "cpi_ri_by_year.csv"

RI_BASE = "https://www.bls.gov/cpi/tables/relative-importance"

#: Archive zips holding the fixed-width December tables, keyed by the years
#: they cover.  1987-1989 is deliberately absent: those tables use the
#: pre-1998 item structure and cannot be mapped onto the ``SE*`` strata.
RI_ARCHIVES = {
    (1990, 1999): "ri-archive-1990-1999.zip",
    (2000, 2009): "ri-archive-2000-2009.zip",
    (2010, 2019): "ri-archive-2010-2019.zip",
}

#: First December whose published table uses the post-1998 item structure.
FIRST_NEW_STRUCTURE_YEAR = 1997

#: Labels BLS used for our strata before the 2009-10 table renamings, mapped
#: ``current label -> [historical labels to sum]``.  The ``SE*`` *series* are
#: continuous across these renamings -- only the wording in the printed table
#: moved -- with one real exception, noted below.  Matching is
#: case-insensitive and whitespace-normalised, so pure typography (the 1998
#: table's double space in "Tenants'  and household insurance", the capital I
#: in "Health Insurance") needs no entry here.
#:
#: * ``Owners' equivalent rent of residences`` -- called "…of primary
#:   residence" until the Dec-2009 table added the unsampled-secondary line and
#:   renamed the parent.  The stratum itself is unchanged.
#: * ``Energy services`` -- printed as "Gas (piped) and electricity" before
#:   Dec-2009.  Same two components (electricity + utility gas).
#: * ``Other recreation services`` -- printed as "Recreation services".
#: * ``Medicinal drugs`` / ``Medical equipment and supplies`` -- the **real**
#:   break.  Before Dec-2009 the medical-commodities branch split
#:   prescription vs non-prescription; from Dec-2009 it splits drugs vs
#:   equipment.  We re-cut the old lines onto the new boundary: drugs =
#:   prescription + over-the-counter drugs, equipment = non-prescription
#:   medical equipment.  Some "medical supplies" bundled into the old
#:   prescription line therefore sit in "drugs" before 2009; the affected
#:   weight is ~0.1% of the index.
HISTORICAL_LABEL_ALIASES: dict[str, list[str]] = {
    "Owners' equivalent rent of residences": [
        "Owners' equivalent rent of primary residence"],
    "Energy services": ["Gas (piped) and electricity"],
    "Other recreation services": ["Recreation services"],
    "Medicinal drugs": ["Prescription drugs and medical supplies",
                        "Internal and respiratory over-the-counter drugs"],
    "Medical equipment and supplies": [
        "Nonprescription medical equipment and supplies"],
}


# ----------------------------------------------------------------------------
# Parsing the published tables
# ----------------------------------------------------------------------------
_ROW_RE = re.compile(
    r"""^(?P<indent>\s*)                 # leading spaces encode the tree depth
         (?P<label>\S.*?)                # the item name
         [\s.]*?\.{2,}\s*                # the dot leader
         (?P<cpiu>-?[\d,]*\.?\d+)        # CPI-U relative importance
         \s+(?P<cpiw>-?[\d,]*\.?\d+)\s*$ # CPI-W (parsed, not used)
      """,
    re.VERBOSE,
)


def parse_ri_text(text: str) -> pd.DataFrame:
    """Parse a fixed-width December relative-importance table (1997-2019).

    The published layout is ``<indent><name><dot leader><CPI-U> <CPI-W>``.  The
    indent carries the hierarchy, which we keep so callers can tell an
    expenditure class from the aggregate above it, but the match is done on the
    label because that is what is stable across years.

    Returns ``[indent, label, ri]`` with ``ri`` the CPI-U relative importance in
    percent.  Rows whose label is a section header (no numbers) are dropped.
    """
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _ROW_RE.match(line.rstrip())
        if not m:
            continue
        label = m.group("label").strip().rstrip(".").strip()
        if not label:
            continue
        try:
            ri = float(m.group("cpiu").replace(",", ""))
        except ValueError:
            continue
        rows.append({"indent": len(m.group("indent")), "label": label, "ri": ri})
    return pd.DataFrame(rows)


def parse_ri_excel(path: Path | io.BytesIO, sheet: str = "Table 1") -> pd.DataFrame:
    """Parse a December relative-importance workbook (2020-).

    The modern sheet carries an explicit ``Indent Level`` column, so no layout
    sniffing is needed: take the indent, the item name and the CPI-U column.
    """
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    # Locate the header row ("Indent Level" / "Item and Group").
    head = None
    for i in range(min(20, len(raw))):
        vals = [str(v).strip().lower() for v in raw.iloc[i].tolist()]
        if any(v.startswith("indent") for v in vals):
            head = i
            break
    if head is None:
        raise ValueError("could not find the 'Indent Level' header row")

    body = raw.iloc[head + 1:, :4].copy()
    body.columns = ["indent", "label", "cpiu", "cpiw"]
    body = body.dropna(subset=["label"])
    body["label"] = body["label"].astype(str).str.strip()
    body["ri"] = pd.to_numeric(body["cpiu"], errors="coerce")
    body["indent"] = pd.to_numeric(body["indent"], errors="coerce")
    body = body.dropna(subset=["ri"])
    return body[["indent", "label", "ri"]].reset_index(drop=True)


# ----------------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------------
def _archive_for(year: int) -> Optional[str]:
    for (lo, hi), name in RI_ARCHIVES.items():
        if lo <= year <= hi:
            return name
    return None


def fetch_ri_year(year: int, force: bool = False) -> pd.DataFrame:
    """December relative-importance table for ``year`` as ``[indent, label, ri]``.

    2020 and later come from the per-year workbook; 1997-2019 from the archive
    zip covering that decade (downloaded once and cached like every other
    external file in the repo).
    """
    if year < FIRST_NEW_STRUCTURE_YEAR:
        raise ValueError(
            f"December {year} predates the 1998 CPI item-structure revision; "
            "the SE* strata have no counterpart in that table"
        )
    if year >= 2020:
        path = fetch_url_bytes(f"{RI_BASE}/{year}.xlsx", f"cpi_ri_{year}.xlsx",
                               force=force)
        return parse_ri_excel(path)

    name = _archive_for(year)
    if name is None:
        raise ValueError(f"no relative-importance archive covers {year}")
    zpath = fetch_url_bytes(f"{RI_BASE}/{name}", name, force=force)
    with zipfile.ZipFile(zpath) as zf:
        members = [n for n in zf.namelist() if n.endswith(f"{year}.txt")]
        if not members:
            raise ValueError(f"{name} has no {year}.txt")
        text = zf.read(members[0]).decode("latin-1")
    return parse_ri_text(text)


# ----------------------------------------------------------------------------
# Building the pinned anchor table
# ----------------------------------------------------------------------------
def build_ri_by_year(
    cats: pd.DataFrame,
    years: Iterable[int],
    force: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """December relative importances for the pinned strata, one column per year.

    Parameters
    ----------
    cats:
        ``config/cpi_categories.csv`` -- needs ``key`` and ``label``.  The join
        onto the published tables is by **exact label**, which is how the
        category file was cut in the first place; a label that fails to match is
        reported rather than silently dropped, because a missing stratum quietly
        reweights every other one.
    years:
        December years to pull (>= 1997).

    Returns
    -------
    DataFrame indexed by ``key`` with one float column per year, each column
    renormalised to sum to 100 over the pinned strata (the published table
    covers the whole tree, so the raw numbers sum to 100 over a *different* set
    of rows).
    """
    out: dict[int, pd.Series] = {}
    for year in years:
        tab = fetch_ri_year(year, force=force)
        lookup = _label_lookup(tab)
        values, missing = [], []
        for row in cats.itertuples():
            v = _lookup_label(lookup, str(row.label))
            if v is None:
                missing.append(str(row.label))
                v = np.nan
            values.append(v)
        s = pd.Series(values, index=cats["key"].to_numpy(), dtype=float)
        total = s.sum(skipna=True)
        out[year] = 100.0 * s / total if total else s
        if verbose:
            note = ""
            if missing:
                note = (f"  [unmatched: {missing[:4]}"
                        f"{'...' if len(missing) > 4 else ''}]")
            print(f"[cpi_ri] {year}: matched {int(s.notna().sum())}/{len(s)} "
                  f"strata, raw sum {total:.2f}%{note}")
    df = pd.DataFrame(out)
    df.index.name = "key"
    return df


def _norm_label(label: str) -> str:
    """Case-fold and collapse whitespace so typography never breaks a match."""
    return re.sub(r"\s+", " ", str(label)).strip().strip(".").lower()


def _label_lookup(table: pd.DataFrame) -> dict[str, float]:
    """``normalised label -> relative importance`` for one published table.

    The first occurrence wins: the tables repeat a few names at different depths
    (an expenditure class and its single child), and the shallower row comes
    first, which is the one our strata correspond to.
    """
    lookup: dict[str, float] = {}
    for row in table.itertuples():
        key = _norm_label(row.label)
        if key and key not in lookup:
            lookup[key] = float(row.ri)
    return lookup


def _lookup_label(lookup: dict[str, float], label: str) -> Optional[float]:
    """Find ``label`` in a published table, falling back to its aliases.

    Aliases that list several historical lines are **summed**: that is the
    medical-commodities re-cut described on
    :data:`HISTORICAL_LABEL_ALIASES`.
    """
    direct = lookup.get(_norm_label(label))
    if direct is not None:
        return direct
    aliases = HISTORICAL_LABEL_ALIASES.get(label)
    if not aliases:
        return None
    parts = [lookup.get(_norm_label(a)) for a in aliases]
    parts = [p for p in parts if p is not None]
    return float(sum(parts)) if parts else None


def load_ri_by_year(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the pinned ``config/cpi_ri_by_year.csv`` (keys x December years)."""
    path = path or RI_CSV
    df = pd.read_csv(path).set_index("key")
    df.columns = [int(c) for c in df.columns]
    return df.sort_index(axis=1)


# ----------------------------------------------------------------------------
# (W1) Price-updating: December anchors -> a monthly weight panel
# ----------------------------------------------------------------------------
def price_updated_weights(
    price_index: pd.DataFrame,
    ri_by_year: pd.DataFrame,
    normalise: bool = True,
) -> pd.DataFrame:
    """Monthly relative importances from December anchors and prices (Eq. W1).

    For every month t, find the governing anchor -- the most recent December
    whose table has been published on or before t-1 -- and carry that anchor
    forward by each category's own price change:

        w_{i,t} proportional to RI_{i,anchor} * P_{i,t} / P_{i,anchor}

    Months **before the first anchor** are back-updated from that first anchor
    by the same formula run backwards.  That is an approximation (it freezes the
    real basket at its 1997 composition) and is flagged by
    :func:`weights_source`.

    Parameters
    ----------
    price_index:
        [months x keys] of item price **levels**.  Only ratios to the anchor
        month are used, so any base period works -- a panel reconstructed by
        cumulating monthly log changes is a valid input.
    ri_by_year:
        Output of :func:`build_ri_by_year` / :func:`load_ri_by_year`: keys x
        December years, in percent.

    Returns
    -------
    DataFrame [months x keys], rows summing to 1 over the categories with a
    finite price that month (``normalise=False`` returns the unnormalised cost
    weights, which is what :func:`weight_update_effect` compares).
    """
    price = price_index.sort_index()
    keys = [k for k in price.columns if k in ri_by_year.index]
    price = price[keys]
    anchors = ri_by_year.loc[keys].sort_index(axis=1)

    years = list(anchors.columns)
    if not years:
        raise ValueError("ri_by_year has no December anchors")

    anchor_dates = {y: pd.Timestamp(year=y, month=12, day=1) for y in years}
    months = price.index
    out = pd.DataFrame(np.nan, index=months, columns=keys, dtype=float)

    for key in keys:
        # A stratum is usable as an anchor only where BOTH its published weight
        # and its anchor-month price exist.  "Information technology, hardware
        # and services" first appears in the Dec-2003 table, so its earlier
        # months are back-updated from 2003 rather than dropped -- which is
        # what reindexing on the whole-table anchor would have done silently.
        usable = [y for y in years
                  if np.isfinite(anchors.at[key, y])
                  and anchor_dates[y] in price.index
                  and np.isfinite(price.at[anchor_dates[y], key])]
        if not usable:
            continue
        col = price[key]
        for i, y in enumerate(usable):
            lo = anchor_dates[y]
            hi = anchor_dates[usable[i + 1]] if i + 1 < len(usable) else None
            # The December table for year Y governs every month until the next
            # published anchor; months before the first anchor are back-updated
            # from it (the `i == 0` branch opens the window at -infinity).
            sel = months < hi if hi is not None else np.ones(len(months), bool)
            if i > 0:
                sel &= months >= lo
            out.loc[sel, key] = (anchors.at[key, y]
                                 * (col[sel] / col.at[lo]).to_numpy())

    if normalise:
        out = out.div(out.sum(axis=1).replace(0, np.nan), axis=0)
    return out


def weights_source(index: pd.Index, ri_by_year: pd.DataFrame) -> pd.Series:
    """Label each month ``"anchored"`` or ``"back-updated"``.

    Anything before the first published December anchor is extrapolated
    backwards and should be presented as such -- the website greys that span and
    ``docs/trim_methodology.md`` explains what it does and does not capture.
    """
    first = pd.Timestamp(year=int(min(ri_by_year.columns)), month=12, day=1)
    return pd.Series(
        np.where(pd.DatetimeIndex(index) >= first, "anchored", "back-updated"),
        index=index, name="weights_source",
    )


def weight_update_effect(
    price_index: pd.DataFrame,
    ri_by_year: pd.DataFrame,
) -> pd.DataFrame:
    """How much each January's new expenditure base moved the weights.

    Compares the December weight implied by price-updating the *previous*
    anchor against the December weight BLS actually published.  Under a pure
    price-update the two would agree; the difference is what the new
    expenditure survey brought in -- the shelter weight climbing through the
    2010s, the 2023 switch from biennial to annual weights, the COVID-era
    basket shifts.

    Returns ``[year, key, price_updated, published, diff]`` in percentage
    points, one row per stratum per December for which both exist.
    """
    anchors = ri_by_year.sort_index(axis=1)
    years = list(anchors.columns)
    rows = []
    for prev, cur in zip(years, years[1:]):
        d_prev = pd.Timestamp(year=prev, month=12, day=1)
        d_cur = pd.Timestamp(year=cur, month=12, day=1)
        if d_prev not in price_index.index or d_cur not in price_index.index:
            continue
        ratio = price_index.loc[d_cur] / price_index.loc[d_prev]
        pu = anchors[prev] * ratio.reindex(anchors.index)
        pu = 100.0 * pu / pu.sum()
        pub = anchors[cur]
        for key in anchors.index:
            if not (np.isfinite(pu.get(key, np.nan)) and np.isfinite(pub.get(key, np.nan))):
                continue
            rows.append({"year": cur, "key": key,
                         "price_updated": float(pu[key]),
                         "published": float(pub[key]),
                         "diff": float(pub[key] - pu[key])})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Helper: price levels from an inflation panel
# ----------------------------------------------------------------------------
def levels_from_inflation(inflation_panel: pd.DataFrame,
                          base: float = 100.0) -> pd.DataFrame:
    """Rebuild relative price levels by cumulating ``100 * dln P``.

    Eq. (W1) only ever uses the ratio of a category's price to its own price in
    the anchor month, so the arbitrary base cancels.  This lets the weight
    machinery run off the panels the website already ships, without a second
    trip to BLS for the levels.  Each column starts at ``base`` in its own first
    month with a finite change; interior gaps carry the level forward.
    """
    lg = (inflation_panel / 100.0).copy()
    out = {}
    for col in lg.columns:
        s = lg[col]
        first = s.first_valid_index()
        if first is None:
            out[col] = pd.Series(np.nan, index=lg.index)
            continue
        cum = s.fillna(0.0).cumsum()
        lvl = base * np.exp(cum - cum.loc[first])
        lvl[s.index < first] = np.nan
        out[col] = lvl
    return pd.DataFrame(out, index=lg.index)
