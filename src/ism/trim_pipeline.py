"""
ism.trim_pipeline
=================

Build the ``(inflation_panel, weights)`` pairs that :mod:`ism.trim_engine`
trims, for each **scope** the trimmed-mean model offers.

A scope is a (price gauge, cross-section cut, weight vintage) triple.  Four
ship:

============  ==========================================================
``cpi45``     The **Cleveland Fed cut**: 45 components, owners' equivalent
              rent split into its four census regions, BLS-published
              seasonally adjusted indexes, weights = December relative
              importances price-updated month by month.  This is the
              cross-section behind the published median CPI and 16%
              trimmed-mean CPI, and reproduces them to corr ~0.997.
``cpi70``     The repo's own 70 item strata (``config/cpi_categories.csv``,
              already used by the ISM momentum model), now with versioned
              weights.  Finer than the Cleveland cut, so the median sits a
              little differently -- which is the point of offering both.
``pce``       BEA PCE underlying detail, the Dallas Fed's gauge.  130
              fourth-level categories, monthly nominal expenditure weights.
``other``     Any gauge already shipped in ``web/data/ism.json`` (UK, FR, DE,
              JP, CA), loaded straight from the panels the site carries.
============  ==========================================================

Two things that took measuring rather than assuming
---------------------------------------------------
**BEA's underlying-detail price indexes are already seasonally adjusted.**
Running our own adjustment over them *degrades* the fit to the Dallas Fed
series (12-month corr 0.9970 raw vs 0.9951 re-adjusted), so the ``pce`` scope
declares ``sa="none"``.  The ISM momentum model differences these panels again
and is insensitive to this, but a trimmed mean is not: seasonality decides who
lands in the tails.

**BLS does not seasonally adjust every stratum.**  It publishes a ``CUSR``
series only where the seasonal is statistically significant; for the rest the
NSA index *is* the adjusted index by BLS's own test.  Three of the 45 Cleveland
components and seven of the 70 strata are in that position, and
:meth:`~ism.datasources.BlsFlatFileClient.seasonally_adjusted` handles the
fallback, reporting which ones it used.

Weights
-------
PCE gets true monthly expenditure shares from BEA 2.4.5U.  CPI weights come
from :mod:`ism.cpi_ri`: December relative importances, price-updated within
each weight regime.  That is what makes a *historical* trimmed mean meaningful
-- see the module docstring there for why a single static vector is not enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .cpi_pipeline import load_cpi_categories
from .cpi_ri import (levels_from_inflation, load_ri_by_year,
                     price_updated_weights, weights_source)
from .datasources import REPO_ROOT, BlsFlatFileClient
from .transforms import monthly_inflation

CLEVELAND_CSV = REPO_ROOT / "config" / "cleveland_components.csv"
CLEVELAND_RI_CSV = REPO_ROOT / "config" / "cleveland_ri_by_year.csv"

#: Month of the Cleveland Fed component table whose regional owners'-equivalent
#: -rent relative importances anchor the four-way OER split
#: (``oer_anchor_ri`` in ``config/cleveland_components.csv``).  BLS publishes
#: regional OER *indexes* but not the regional share of the **national** index,
#: so one observed split is needed; it is then carried to every other month by
#: the same price-updating identity used for every other weight.  Refresh it
#: with ``scripts/build_cpi_ri.py --cut cleveland``.
OER_SPLIT_ANCHOR = "2026-08"


@dataclass
class TrimPanel:
    """A scope's engine inputs plus the provenance needed to caption a chart."""

    key: str
    label: str
    inflation: pd.DataFrame
    weights: pd.DataFrame
    labels: dict[str, str]
    sa: str                       # the trim_engine sa= setting this panel wants
    periods_per_year: int = 12
    source_note: str = ""
    weight_note: str = ""
    notes: list[str] = field(default_factory=list)
    weights_source: Optional[pd.Series] = None

    @property
    def n_categories(self) -> int:
        return self.inflation.shape[1]


# ----------------------------------------------------------------------------
# The Cleveland Fed cut (45 components)
# ----------------------------------------------------------------------------
def load_cleveland_components(path: Optional[Path] = None) -> pd.DataFrame:
    """Load ``config/cleveland_components.csv`` (45 rows).

    Columns: ``key`` (unique, item code plus area for the regional OER lines),
    ``item_code``, ``area_code``, ``region``, ``ri_label`` (the name to match in
    the BLS relative-importance table), ``label``, ``group`` and
    ``oer_anchor_ri``.
    """
    path = path or CLEVELAND_CSV
    df = pd.read_csv(path, dtype={"area_code": str})
    df["area_code"] = df["area_code"].str.zfill(4)
    return df


def build_cleveland_panel(
    bls: Optional[BlsFlatFileClient] = None,
    components: Optional[pd.DataFrame] = None,
    ri_by_year: Optional[pd.DataFrame] = None,
    force: bool = False,
) -> TrimPanel:
    """The 45-component Cleveland cross-section, SA, with versioned weights.

    Prices come from the BLS flat files (no key, no daily cap) -- ``CUSR`` where
    published, ``CUUR`` where BLS finds no significant seasonal.  The four
    regional owners'-equivalent-rent lines have no published SA variant at all,
    so they enter NSA; OER's seasonal is negligible, which is why the Cleveland
    replication still lands at 12-month corr ~0.997.
    """
    bls = bls or BlsFlatFileClient()
    comp = components if components is not None else load_cleveland_components()
    ri = ri_by_year if ri_by_year is not None else load_cleveland_ri()

    prices: dict[str, pd.Series] = {}
    nsa_prices: dict[str, pd.Series] = {}
    fell_back: list[str] = []

    for area, block in comp.groupby("area_code"):
        codes = block["item_code"].tolist()
        sa, fb = bls.seasonally_adjusted(codes, area=area, force=force)
        nsa = bls.fetch_many([f"CUUR{area}{c}" for c in codes], force=force)
        for row in block.itertuples():
            s = sa.get(row.item_code)
            if s is not None:
                prices[row.key] = s
            n = nsa.get(f"CUUR{area}{row.item_code}")
            if n is not None:
                nsa_prices[row.key] = n
        fell_back += [f"{c}@{area}" for c in fb]

    price = _as_monthly(pd.DataFrame(prices))
    price_nsa = _as_monthly(pd.DataFrame(nsa_prices))
    keys = [k for k in comp["key"] if k in price.columns]
    price, price_nsa = price[keys], price_nsa.reindex(columns=keys)

    # Relative importances are nominal cost weights, so they are price-updated
    # with the NSA index -- the seasonally adjusted one would make the weights
    # wobble with the seasonal instead of with real relative prices.
    weights = price_updated_weights(price_nsa, ri)
    inflation = monthly_inflation(price)
    common = inflation.index.intersection(weights.index)

    return TrimPanel(
        key="cpi45",
        label="US CPI - Cleveland Fed cut (45 components)",
        inflation=inflation.loc[common],
        weights=weights.loc[common],
        labels=dict(zip(comp["key"], comp["label"])),
        sa="none",
        source_note=("BLS CPI-U, seasonally adjusted where published "
                     "(CUSR*, else CUUR*); owners' equivalent rent split by "
                     "census region"),
        weight_note=("December relative importances, price-updated monthly "
                     "(BLS RI tables 1997-); regional OER split anchored on the "
                     f"Cleveland Fed component table, {OER_SPLIT_ANCHOR}"),
        notes=([f"{len(fell_back)} components have no published SA series and "
                f"enter NSA: {', '.join(fell_back)}"] if fell_back else []),
        weights_source=weights_source(common, ri),
    )


def build_cleveland_ri(
    components: Optional[pd.DataFrame] = None,
    years: Optional[list[int]] = None,
    bls: Optional[BlsFlatFileClient] = None,
    force: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """December relative importances for the 45 Cleveland components.

    Forty-one of them are named lines in the BLS table and are read straight
    off it.  The four regional owners'-equivalent-rent lines are not: BLS
    publishes each region's OER relative importance *within that region's own
    index*, never its share of the national index.  We therefore take the
    national OER relative importance -- which is published -- and split it with
    the one observed split (the Cleveland component table, see
    :data:`OER_SPLIT_ANCHOR`), carried to every December by the regional OER
    price indexes.  Regions whose OER has risen faster than the national
    average therefore get a larger share the closer you get to the anchor, and
    a smaller one going back, which is the right direction and roughly the
    right size.
    """
    from .cpi_ri import FIRST_NEW_STRUCTURE_YEAR, _label_lookup, _lookup_label, fetch_ri_year

    comp = components if components is not None else load_cleveland_components()
    bls = bls or BlsFlatFileClient()
    years = years or list(range(FIRST_NEW_STRUCTURE_YEAR, _last_ri_year() + 1))

    national = comp[comp["area_code"] == "0000"]
    oer = comp[comp["area_code"] != "0000"]

    cols: dict[int, pd.Series] = {}
    oer_total: dict[int, float] = {}
    for year in years:
        lookup = _label_lookup(fetch_ri_year(year, force=force))
        vals = {row.key: _lookup_label(lookup, row.ri_label)
                for row in national.itertuples()}
        cols[year] = pd.Series(vals, dtype=float)
        oer_total[year] = _lookup_label(
            lookup, "Owners' equivalent rent of residences") or np.nan
        if verbose:
            n = int(cols[year].notna().sum())
            print(f"[cleveland_ri] {year}: {n}/{len(national)} named components")

    table = pd.DataFrame(cols)

    # Regional OER: one observed split, price-updated to each December.
    reg = bls.fetch_many([f"CUUR{a}{c}" for a, c in
                          zip(oer["area_code"], oer["item_code"])], force=force)
    reg_px = _as_monthly(pd.DataFrame(
        {f"{c}_{a}": reg[f"CUUR{a}{c}"]
         for a, c in zip(oer["area_code"], oer["item_code"])
         if f"CUUR{a}{c}" in reg}))
    anchor = pd.Timestamp(OER_SPLIT_ANCHOR + "-01")
    if anchor not in reg_px.index:
        anchor = reg_px.dropna(how="any").index[-1]
    base = pd.Series(oer["oer_anchor_ri"].to_numpy(float),
                     index=oer["key"].to_numpy())

    shares = pd.DataFrame({k: base[k] * (reg_px[k] / reg_px.at[anchor, k])
                           for k in base.index if k in reg_px.columns})
    shares = shares.div(shares.sum(axis=1), axis=0)
    for year in years:
        dec = pd.Timestamp(year=year, month=12, day=1)
        row = shares.reindex([dec]).iloc[0] if dec in shares.index else shares.iloc[0] * np.nan
        for key in base.index:
            table.loc[key, year] = oer_total[year] * row.get(key, np.nan)

    table = table[years]
    table = 100.0 * table / table.sum()
    table.index.name = "key"
    return table


def load_cleveland_ri(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the pinned ``config/cleveland_ri_by_year.csv``."""
    path = path or CLEVELAND_RI_CSV
    df = pd.read_csv(path).set_index("key")
    df.columns = [int(c) for c in df.columns]
    return df.sort_index(axis=1)


def _last_ri_year() -> int:
    import datetime as dt
    return dt.date.today().year - 1


# ----------------------------------------------------------------------------
# The repo's own 70 CPI item strata, with versioned weights
# ----------------------------------------------------------------------------
def build_cpi70_panel(
    bls: Optional[BlsFlatFileClient] = None,
    cats: Optional[pd.DataFrame] = None,
    ri_by_year: Optional[pd.DataFrame] = None,
    force: bool = False,
) -> TrimPanel:
    """The 70 pinned item strata, BLS-seasonally-adjusted, versioned weights.

    Same machinery as the Cleveland cut on a finer cross-section: every stratum
    is an expenditure class in its own right, and owners' equivalent rent stays
    whole.  That single ~25%-weight line dominates the middle of the
    distribution, which is why this cut's *median* tracks the published median
    less closely than ``cpi45`` does while its *trimmed mean* is nearly as good
    -- the trim is robust to how the mass in the middle is cut up, the median is
    not.
    """
    bls = bls or BlsFlatFileClient()
    cats = cats if cats is not None else load_cpi_categories()
    ri = ri_by_year if ri_by_year is not None else load_ri_by_year()

    codes = cats["key"].tolist()
    sa, fell_back = bls.seasonally_adjusted(codes, force=force)
    nsa = bls.fetch_many([f"CUUR0000{c}" for c in codes], force=force)

    price = _as_monthly(pd.DataFrame(sa))
    price_nsa = _as_monthly(pd.DataFrame({k[8:]: v for k, v in nsa.items()}))
    keys = [k for k in codes if k in price.columns]
    price, price_nsa = price[keys], price_nsa.reindex(columns=keys)

    weights = price_updated_weights(price_nsa, ri)
    inflation = monthly_inflation(price)
    common = inflation.index.intersection(weights.index)

    return TrimPanel(
        key="cpi70",
        label="US CPI - 70 item strata",
        inflation=inflation.loc[common],
        weights=weights.loc[common],
        labels=dict(zip(cats["key"], cats["label"])),
        sa="none",
        source_note="BLS CPI-U item strata, SA where published (CUSR*, else CUUR*)",
        weight_note=("December relative importances, price-updated monthly "
                     "(BLS RI tables 1997-)"),
        notes=([f"{len(fell_back)} strata have no published SA series and enter "
                f"NSA: {', '.join(fell_back)}"] if fell_back else []),
        weights_source=weights_source(common, ri),
    )


# ----------------------------------------------------------------------------
# PCE (the Dallas Fed's gauge)
# ----------------------------------------------------------------------------
def build_pce_panel(
    inflation_panel: Optional[pd.DataFrame] = None,
    weights: Optional[pd.DataFrame] = None,
    labels: Optional[dict[str, str]] = None,
    bea=None,
    force: bool = False,
) -> TrimPanel:
    """BEA PCE underlying detail: 130 categories, monthly expenditure weights.

    Pass ``inflation_panel``/``weights`` to reuse panels already built (the
    exporter hands it the ones shipped in ``web/data/ism.json``); otherwise the
    BEA tables are fetched through :func:`ism.pipeline.build_category_panel`.

    ``sa="none"``: BEA's 2.4.4U price indexes arrive seasonally adjusted.  This
    was verified against the Dallas Fed series rather than assumed -- adding an
    adjustment lowers the 12-month correlation from 0.997 to 0.995.
    """
    if inflation_panel is None or weights is None:
        from .pipeline import build_category_panel
        cats = pd.read_csv(REPO_ROOT / "config" / "pce_categories.csv")
        explicit = cats["SeriesCode"].tolist() if "SeriesCode" in cats else None
        inflation_panel, weights = build_category_panel(
            bea=bea, explicit_series=explicit, force=force)
        labels = labels or dict(zip(cats.get("key", cats.iloc[:, 0]),
                                    cats.get("label", cats.iloc[:, 0])))

    common = inflation_panel.index.intersection(weights.index)
    return TrimPanel(
        key="pce",
        label="US PCE - BEA underlying detail",
        inflation=inflation_panel.loc[common],
        weights=weights.loc[common],
        labels=labels or {c: c for c in inflation_panel.columns},
        sa="none",
        source_note="BEA Underlying Detail tables 2.4.4U (prices) / 2.4.5U (nominal)",
        weight_note="monthly nominal PCE shares (BEA 2.4.5U)",
        notes=["BEA publishes these price indexes seasonally adjusted; no "
               "further adjustment is applied."],
    )


# ----------------------------------------------------------------------------
# Any gauge already shipped to the website
# ----------------------------------------------------------------------------
def panel_from_web_data(payload: dict, backbone: str, sa: str = "rolling",
                        periods_per_year: int = 12) -> TrimPanel:
    """Build a :class:`TrimPanel` from a backbone block of ``web/data/ism.json``.

    The ISM site already ships every gauge's raw category panel and weights, so
    the trimmed-mean model gets the UK, France, Germany, Japan and Canada for
    free.  None of those has a published limited-influence measure to validate
    against, so they are offered as exploratory scopes -- the same posture the
    decomposition ports take.
    """
    block = payload["backbones"][backbone]
    idx = pd.to_datetime([d + "-01" for d in block["dates"]])
    keys = [c["key"] for c in block["categories"]]
    inflation = pd.DataFrame(
        {k: block["panel"]["inflation"][i] for i, k in enumerate(keys)}, index=idx)
    weights = pd.DataFrame(
        {k: block["panel"]["weights"][i] for i, k in enumerate(keys)}, index=idx)
    return TrimPanel(
        key=backbone,
        label=block.get("label", backbone),
        inflation=inflation.astype(float),
        weights=weights.astype(float),
        labels={c["key"]: c["label"] for c in block["categories"]},
        sa=sa,
        periods_per_year=periods_per_year,
        source_note=block.get("source_note", ""),
        weight_note=block.get("weight_note", ""),
        notes=["no published trimmed-mean or median series exists for this "
               "gauge; the overlay is the headline rate only"],
    )


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _as_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    """Month-start index, gaps bridged, no leading/trailing values invented.

    BLS occasionally does not publish a month -- the October 2025 CPI release
    was never produced -- and one hole would otherwise break the
    month-over-month chain for every later month.  ``limit_area="inside"``
    bridges only genuine interior holes between two real prints.
    """
    if frame.empty:
        return frame
    out = frame.sort_index()
    out.index = pd.to_datetime(out.index).to_period("M").to_timestamp()
    out = out[~out.index.duplicated(keep="last")].asfreq("MS")
    return out.interpolate(method="time", limit_area="inside")
