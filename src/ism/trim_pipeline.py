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
#: What the reader needs to know about each gauge the ISM site already ships,
#: over and above its source note.  Chiefly: is there a published measure to
#: check this against, and if so, is it built the same way ours is?
WEB_SCOPE_NOTES = {
    None: ["no published limited-influence measure is available for this "
           "gauge; the overlay is the headline rate only"],
    "uk": ["the ONS publishes no trimmed-mean or median CPI, so the overlay is "
           "headline CPI only",
           "85 COICOP classes, none heavier than 11% of the basket -- the "
           "widest cross-section here after the euro-area members, and "
           "markedly better conditioned for an 8% trim than US CPI, where "
           "owners' equivalent rent alone is a quarter of the basket"],
    "fr": ["no published trimmed mean exists for France: the ECB's trimmed "
           "means (ICP, item codes TRIM05-TRIM50) are computed for the euro "
           "area as a whole, not for member states, and their last observation "
           "is 2025-12 -- the month Eurostat froze the ECOICOP v1 datasets "
           "these panels used to come from"],
    "de": ["no published trimmed mean exists for Germany; see the note on the "
           "France scope for the euro-area series and why it stops in 2025-12"],
    "jp": ["the Bank of Japan publishes a 10% trimmed mean, a weighted median "
           "and a mode, and they are overlaid here -- but the Bank trims the "
           "cross-section of *twelve-month* changes while this engine trims "
           "the monthly one, so the two are the same measure in spirit and "
           "not the same calculation",
           "the narrowest cross-section on the site: 47 medium groups with "
           "rent at 18% of the basket, so an 8% tail is on average barely five "
           "components and half of it is whichever single component leads it"],
    "ca": ["the Bank of Canada's CPI-trim (20% each tail) and CPI-median are "
           "overlaid, and they are built the way this engine builds them -- "
           "monthly cross-section, chained -- so they are a genuine check",
           "two differences remain: the Bank's inputs are adjusted for changes "
           "in indirect taxes and seasonally adjusted with StatCan's own "
           "per-series specifications, while ours are the published NSA index "
           "with this engine's seasonal estimate"],
}


def panel_from_web_data(payload: dict, backbone: str, sa: str = "rolling",
                        periods_per_year: int = 12) -> TrimPanel:
    """Build a :class:`TrimPanel` from a backbone block of ``web/data/ism.json``.

    The ISM site already ships every gauge's raw category panel and weights, so
    the trimmed-mean model gets the UK, France, Germany, Japan and Canada for
    free.  Two of them have a published limited-influence measure to be scored
    against -- the Bank of Canada's CPI-trim and CPI-median, and the Bank of
    Japan's 10% trimmed mean and weighted median -- and are wired up in
    :data:`ism.trim_validate.OFFICIAL`.  The other three are exploratory, the
    same posture the decomposition ports take.  :data:`WEB_SCOPE_NOTES` records
    which is which, and why.
    """
    block = payload["backbones"][backbone]
    notes = list(WEB_SCOPE_NOTES.get(backbone, WEB_SCOPE_NOTES[None]))
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
        notes=notes,
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


# ----------------------------------------------------------------------------
# Is this cross-section wide enough to trim?
# ----------------------------------------------------------------------------
def cross_section_conditioning(
    panel: TrimPanel,
    lower: float = 0.08,
    upper: float = 0.08,
    years: int = 10,
    sa: str | None = None,
) -> dict:
    """How much of a trimmed tail rests on a single component.

    A trim is only as informative as the cross-section it cuts.  If one
    component carries more weight than the whole tail fraction, that tail is
    that component's price -- the estimator has not averaged anything away, it
    has just relabelled one series.  US CPI at the 70-stratum cut is the extreme
    case in this repo: owners' equivalent rent alone is about a quarter of the
    basket, three times an 8% tail.

    Four numbers, because concentration alone does not settle it.  A very heavy
    component that habitually sits in the *middle* of the distribution (OER,
    usually) never touches a tail, while a modest one that is always at an
    extreme does.  So we measure both the weight vector and what actually
    happens at the cut:

    ``effective_n``
        ``1 / sum(w^2)`` on the latest weights -- the number of equally sized
        components that would be as concentrated as this basket.
    ``over_trim``
        How many components weigh more than the trim fraction, i.e. could fill
        an entire tail on their own.
    ``tail_components``
        Mean number of distinct components the lower and upper tails cut
        through, over the last ``years`` years.
    ``tail_max_share``
        Mean share of a tail (%) supplied by that tail's single largest
        contributor.  100 means the tail was one component.

    ``sa`` overrides the panel's own seasonal treatment; the default follows it,
    because the ordering of the cross-section -- and therefore which components
    land in a tail -- depends on it.
    """
    from .trim_engine import TrimConfig, compute_trim

    cfg = TrimConfig(lower=lower, upper=upper, sa=sa or panel.sa,
                     periods_per_year=panel.periods_per_year)
    res = compute_trim(panel.inflation, panel.weights, cfg)
    rates, wts = res.sa_panel, res.weights

    usable = res.n_categories[res.n_categories > 0]
    if usable.empty:
        return {}
    end = usable.index[-1]
    window = rates.index[(rates.index >= end - pd.DateOffset(years=years))
                         & (rates.index <= end)]

    n_lo, n_hi, max_share = [], [], []
    for d in window:
        got = _tail_shape(rates.loc[d].to_numpy(), wts.loc[d].to_numpy(),
                          lower, upper)
        if got is None:
            continue
        a, b, c = got
        n_lo.append(a); n_hi.append(b); max_share.append(c)

    last = wts.loc[end].dropna()
    if last.empty or last.sum() <= 0:
        return {}
    last = last / last.sum()
    biggest = last.idxmax()

    return {
        "lower": lower, "upper": upper,
        "n": int(last.size),
        "effective_n": float(1.0 / float((last ** 2).sum())),
        "top1": float(100.0 * last.max()),
        "top3": float(100.0 * last.nlargest(3).sum()),
        "over_trim": int((last > max(lower, upper)).sum()),
        "tail_components": {
            "lower": float(np.mean(n_lo)) if n_lo else None,
            "upper": float(np.mean(n_hi)) if n_hi else None,
        },
        "tail_max_share": float(100.0 * np.mean(max_share)) if max_share else None,
        "biggest": {"key": str(biggest),
                    "label": panel.labels.get(biggest, str(biggest)),
                    "weight": float(100.0 * last.max())},
        "window": [window[0].strftime("%Y-%m"), end.strftime("%Y-%m")] if len(window) else None,
        "months": int(len(n_lo)),
    }


def _tail_shape(values: np.ndarray, weights: np.ndarray,
                lower: float, upper: float):
    """(components in the lower tail, in the upper tail, largest tail share).

    Boundary components count as being in the tail for whatever part of their
    weight falls inside it -- the same partial accounting the estimator itself
    uses, so a tail made of "two components and a sliver of a third" reads as
    three, not two.
    """
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not ok.any():
        return None
    vv, ww = v[ok], w[ok]
    order = np.argsort(vv, kind="mergesort")
    ww = ww[order]
    ww = ww / ww.sum()
    cum_hi = np.cumsum(ww)
    cum_lo = cum_hi - ww

    tol = 1e-12
    below = np.clip(np.minimum(cum_hi, lower) - cum_lo, 0.0, None)
    above = np.clip(cum_hi - np.maximum(cum_lo, 1.0 - upper), 0.0, None)

    shares = []
    if lower > tol and below.sum() > tol:
        shares.append(below.max() / lower)
    if upper > tol and above.sum() > tol:
        shares.append(above.max() / upper)
    return (int((below > tol).sum()), int((above > tol).sum()),
            float(max(shares)) if shares else float("nan"))
