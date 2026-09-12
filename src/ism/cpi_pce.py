"""
ism.cpi_pce
===========

**How CPI feeds PCE, and why the two never print the same number.**

Two questions, one concordance:

1. *Where does the gap come from?*  :func:`gap_decomposition` splits the
   CPI-minus-PCE inflation wedge into the four differences that generate it --
   **formula**, **weight**, **price-measure** and **scope** -- plus an explicit
   residual, as an exact identity rather than a regression.
2. *What does today's CPI imply for PCE?*  :func:`bridge_nowcast` maps a CPI
   print into an implied PCE print category group by category group, and scores
   itself against what PCE actually did.

The concordance
---------------
``config/cpi_pce_concordance.csv`` assigns every one of the 70 CPI item strata
and every one of the 130 PCE categories to a **common group** -- 28 of them,
from ``food_home`` to ``personal_other``.  Grouping rather than matching
one-to-one is deliberate: the two classifications are not nested (CPI's
"Public transportation" spans PCE's ground, air and water transportation; PCE's
"Household furnishings" swallows CPI's housekeeping supplies *and* household
operations), and a group cut coarse enough to be honest is more useful than a
line-by-line map that is quietly wrong in a dozen places.

Four groups carry ``role = scope`` rather than ``common``, because the two
gauges measure genuinely different things there and averaging them would hide
the single largest source of the wedge:

* **health insurance** -- PCE counts what employers and government pay on
  households' behalf and values insurance at the insurers' margin; CPI counts
  the household premium net of benefits.
* **household and motor-vehicle insurance** -- same net-versus-premium split.
* **financial services** -- PCE imputes the services banks provide without
  charging for them (FISIM); the CPI has no such line.

Plus a residual ``out_of_scope`` group: employer-furnished meals, military
clothing, farm output eaten on the farm, nonprofit social services, spending
abroad.  Together these are most of the reason PCE weights sum to more than
household out-of-pocket spending -- and most of the reason PCE inflation runs
below CPI inflation on average.

The decomposition (exact, telescoping)
--------------------------------------
Write pi_CPI and pi_PCE for the two **published** 12-month rates, and build four
aggregates of our own from the category panels, each differing from the next by
exactly one substitution:

    A_all    CPI prices, CPI weights, every group
    A_CPI    CPI prices, CPI weights, common groups only
    A_PCEw   CPI prices, PCE weights, common groups only   <- weights changed
    B_PCE    PCE prices, PCE weights, common groups only   <- prices changed
    B_all    PCE prices, PCE weights, every group

Then

    pi_CPI - pi_PCE =  (pi_CPI - A_all )   rebuild residual    (C1)
                     + (A_all  - A_CPI )   coverage effect     (C2)
                     + (A_CPI  - A_PCEw)   weight effect       (C3)
                     + (A_PCEw - B_PCE )   price-measure effect(C4)
                     + (B_PCE  - B_all )   scope effect        (C5)
                     + (B_all  - pi_PCE)   formula effect      (C6)

Six lines, each one substitution, summing to the gap by construction -- no
fitting, nothing to tune.  What they mean:

* **(C1) rebuild residual.**  Our 28-group aggregate of CPI strata against the
  published CPI-U: lower-level formula differences and whatever the group cut
  costs.  It is reported, not hidden -- a residual that starts drifting means
  the concordance needs attention.  In practice it runs a few hundredths of a
  point.
* **(C2) coverage.**  The CPI strata that have no comparable PCE counterpart --
  the insurance premiums whose PCE analogue is a net margin.
* **(C3) weight.**  Identical price changes, PCE's expenditure shares instead of
  CPI's.  This is the shelter story: shelter is roughly a third of the CPI and
  about a sixth of PCE, so any shelter move hits CPI about twice as hard.  It is
  also why a static weight vector will not do -- use the versioned CPI weights
  from :mod:`ism.cpi_ri`, or this line is measuring 2023 in every year.
* **(C4) price-measure.**  Same weights, different price data for the same
  group -- PCE takes medical services from the PPI rather than the CPI, prices
  air travel differently, and so on.  Historically the largest single term.
* **(C5) scope.**  What the PCE-only groups above (employer-paid health
  insurance, imputed financial services, the rest) do to the PCE total.
* **(C6) formula.**  A fixed-weight aggregate of the PCE categories against the
  published Fisher-chained PCE index: the cost of the aggregation formula
  itself, measured rather than assumed.

The usual textbook proxy for the formula effect -- published CPI-U minus the
chained C-CPI-U -- is reported alongside as ``ccpi_proxy`` but deliberately kept
**out** of the identity.  Chaining a published index between two aggregates of
our own makes the formula and residual lines cancel each other, which looks
tidy and means nothing.

The bridge
----------
:func:`bridge_nowcast` regresses each common group's PCE inflation on the same
group's CPI inflation over a rolling window, applies the fit to the current CPI
print, aggregates with PCE weights, and projects the scope groups from their own
recent average (they have no CPI input by definition).  The result is an implied
PCE month, with the historical distribution of its own errors attached -- which
is the only honest way to publish a nowcast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, BlsFlatFileClient
from .transforms import monthly_inflation

CONCORDANCE_CSV = REPO_ROOT / "config" / "cpi_pce_concordance.csv"

#: Chained CPI for all items (C-CPI-U, NSA), the formula-effect diagnostic.
CCPI_SERIES = "SUUR0000SA0"
#: Published CPI-U, all items, US city average, NSA.
CPI_SERIES = "CUUR0000SA0"


# ----------------------------------------------------------------------------
# Concordance
# ----------------------------------------------------------------------------
def load_concordance(path: Optional[Path] = None) -> pd.DataFrame:
    """Load ``config/cpi_pce_concordance.csv``.

    Columns: ``gauge`` (``cpi``/``pce``), ``key``, ``label``, ``group``,
    ``role`` (``common``/``scope``), ``note``.
    """
    path = path or CONCORDANCE_CSV
    return pd.read_csv(path)


def common_groups(conc: pd.DataFrame) -> list[str]:
    """Groups present on **both** sides and flagged ``common``."""
    cpi = set(conc[(conc.gauge == "cpi") & (conc.role == "common")]["group"])
    pce = set(conc[(conc.gauge == "pce") & (conc.role == "common")]["group"])
    return sorted(cpi & pce)


def scope_groups(conc: pd.DataFrame) -> list[str]:
    """PCE-side groups that have no comparable CPI counterpart."""
    common = set(common_groups(conc))
    pce = set(conc[conc.gauge == "pce"]["group"])
    return sorted(pce - common)


# ----------------------------------------------------------------------------
# Group aggregates
# ----------------------------------------------------------------------------
def group_panel(
    inflation: pd.DataFrame,
    weights: pd.DataFrame,
    mapping: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate a category panel into groups.

    ``mapping`` is ``key -> group``.  Group inflation is the weight-weighted
    mean of its members' inflation (so the group behaves like a sub-index), and
    the group weight is the sum of its members' weights.  Members missing in a
    month drop out and the group renormalises over what is there -- the same
    convention :mod:`ism.engine` uses.

    Returns ``(group_inflation, group_weights)``, both [months x groups].
    """
    keys = [k for k in inflation.columns if k in mapping.index]
    infl = inflation[keys]
    w = weights.reindex(columns=keys)
    w = w.where(infl.notna())

    groups = sorted(set(mapping.loc[keys]))
    gi, gw = {}, {}
    for g in groups:
        cols = [k for k in keys if mapping[k] == g]
        wg = w[cols]
        tot = wg.sum(axis=1, min_count=1)
        gi[g] = (wg * infl[cols]).sum(axis=1, min_count=1) / tot.replace(0, np.nan)
        gw[g] = tot
    return pd.DataFrame(gi), pd.DataFrame(gw)


def aggregate(group_inflation: pd.DataFrame, group_weights: pd.DataFrame,
              groups: Optional[list[str]] = None) -> pd.Series:
    """Weighted mean of selected groups, renormalised each month (monthly %)."""
    cols = [g for g in (groups or group_inflation.columns)
            if g in group_inflation.columns and g in group_weights.columns]
    infl = group_inflation[cols]
    w = group_weights[cols].where(infl.notna())
    tot = w.sum(axis=1, min_count=1)
    return (w * infl).sum(axis=1, min_count=1) / tot.replace(0, np.nan)


def yoy_from_monthly(monthly_pct: pd.Series, periods: int = 12) -> pd.Series:
    """12-month inflation implied by chaining a monthly log-change series."""
    return monthly_pct.rolling(periods, min_periods=periods).sum()


# ----------------------------------------------------------------------------
# (C1)-(C5) the gap decomposition
# ----------------------------------------------------------------------------
@dataclass
class GapResult:
    """Output of :func:`gap_decomposition`.

    ``table`` holds the 12-month series: ``cpi``, ``pce``, ``gap``, the six
    components of :data:`COMPONENTS`, the ``ccpi_proxy`` diagnostic, and the
    five intermediate aggregates, so any month can be re-derived by hand.
    """

    table: pd.DataFrame
    group_cpi: pd.DataFrame
    group_pce: pd.DataFrame
    weights_cpi: pd.DataFrame
    weights_pce: pd.DataFrame
    common: list[str]
    scope: list[str]
    notes: list[str] = field(default_factory=list)

    #: The six terms that sum to the gap, in the order of Eqs. C1-C6.
    COMPONENTS = ("residual", "coverage", "weight", "price", "scope", "formula")

    def check(self) -> float:
        """Largest violation of the telescoping identity (should be ~0)."""
        parts = self.table[list(self.COMPONENTS)]
        return float((parts.sum(axis=1, min_count=1) - self.table["gap"]).abs().max())


def gap_decomposition(
    cpi_inflation: pd.DataFrame,
    cpi_weights: pd.DataFrame,
    pce_inflation: pd.DataFrame,
    pce_weights: pd.DataFrame,
    conc: Optional[pd.DataFrame] = None,
    cpi_published: Optional[pd.Series] = None,
    pce_published: Optional[pd.Series] = None,
    ccpi: Optional[pd.Series] = None,
    periods: int = 12,
    fetch_missing: bool = True,
) -> GapResult:
    """Split the 12-month CPI-PCE gap into its six sources (Eqs. C1-C6).

    Parameters
    ----------
    cpi_inflation, cpi_weights:
        Category panel and weights for the CPI gauge (monthly %, ``100*dln P``).
        Use the **versioned** CPI weights -- a static weight vector puts the
        wrong shelter share into every year but one, and shelter is exactly what
        the weight effect is about.
    pce_inflation, pce_weights:
        The same for PCE (BEA 2.4.4U / 2.4.5U).
    cpi_published, pce_published:
        The two published 12-month rates in %.  CPI-U is fetched from the BLS
        flat files when omitted.  If ``pce_published`` is omitted the formula
        effect cannot be measured and is reported as zero, with a note --
        the exporter passes the site's own headline PCE series.
    ccpi:
        C-CPI-U price index level, used only for the ``ccpi_proxy`` diagnostic.
    fetch_missing:
        Whether to download a published series that was not supplied.  Set it
        to ``False`` to keep the function offline: the missing series then falls
        back to our own aggregate, which makes the corresponding term
        identically zero -- useful in tests, and the right behaviour in a
        sandbox where a silent network call would be the surprise.
    """
    conc = conc if conc is not None else load_concordance()
    common = common_groups(conc)
    scope = scope_groups(conc)

    map_cpi = conc[conc.gauge == "cpi"].set_index("key")["group"]
    map_pce = conc[conc.gauge == "pce"].set_index("key")["group"]

    gi_cpi, gw_cpi = group_panel(cpi_inflation, cpi_weights, map_cpi)
    gi_pce, gw_pce = group_panel(pce_inflation, pce_weights, map_pce)

    idx = gi_cpi.index.union(gi_pce.index)
    gi_cpi, gw_cpi = gi_cpi.reindex(idx), gw_cpi.reindex(idx)
    gi_pce, gw_pce = gi_pce.reindex(idx), gw_pce.reindex(idx)

    a_all = yoy_from_monthly(aggregate(gi_cpi, gw_cpi), periods)
    a_cpi = yoy_from_monthly(aggregate(gi_cpi, gw_cpi, common), periods)
    a_pcew = yoy_from_monthly(
        aggregate(gi_cpi, gw_pce.reindex(columns=gi_cpi.columns), common), periods)
    b_pce = yoy_from_monthly(aggregate(gi_pce, gw_pce, common), periods)
    b_all = yoy_from_monthly(aggregate(gi_pce, gw_pce), periods)

    notes: list[str] = []

    if cpi_published is None and not fetch_missing:
        notes.append("no published CPI supplied and fetching disabled; the "
                     "rebuild residual is identically zero")
        cpi_published = a_all
    if cpi_published is None:
        try:
            level = BlsFlatFileClient().series(CPI_SERIES)
            level = level.reindex(idx).interpolate(method="time", limit_area="inside")
            cpi_published = yoy_from_monthly(monthly_inflation(level), periods)
        except Exception as exc:                      # offline / blocked
            notes.append(f"published CPI-U unavailable ({exc}); using our own "
                         "aggregate, so the rebuild residual is identically zero")
            cpi_published = a_all
    cpi_published = cpi_published.reindex(idx)

    if pce_published is None:
        notes.append("no published PCE series supplied; the formula effect "
                     "(fixed-weight vs Fisher chain) cannot be measured and is "
                     "reported as zero")
        pce_published = b_all
    pce_published = pce_published.reindex(idx)

    ccpi_proxy = pd.Series(np.nan, index=idx)
    if ccpi is None and not fetch_missing:
        ccpi = pd.Series(np.nan, index=idx)
    if ccpi is None:
        try:
            ccpi = BlsFlatFileClient(database="su").series(CCPI_SERIES)
        except Exception as exc:
            notes.append(f"C-CPI-U unavailable ({exc}); the ccpi_proxy "
                         "diagnostic is empty")
            ccpi = None
    if ccpi is not None and ccpi.notna().any():
        ccpi = ccpi.reindex(idx).interpolate(method="time", limit_area="inside")
        ccpi_proxy = cpi_published - yoy_from_monthly(monthly_inflation(ccpi), periods)
        notes.append("ccpi_proxy = published CPI-U minus C-CPI-U (the textbook "
                     "formula-effect proxy, from December 1999); shown as a "
                     "diagnostic, not as part of the identity")

    table = pd.DataFrame({
        "cpi": cpi_published, "pce": pce_published,
        "gap": cpi_published - pce_published,
        "residual": cpi_published - a_all,
        "coverage": a_all - a_cpi,
        "weight": a_cpi - a_pcew,
        "price": a_pcew - b_pce,
        "scope": b_pce - b_all,
        "formula": b_all - pce_published,
        "ccpi_proxy": ccpi_proxy,
        "A_all": a_all, "A_cpi": a_cpi, "A_pce_weights": a_pcew,
        "B_pce": b_pce, "B_all": b_all,
    })

    return GapResult(table=table, group_cpi=gi_cpi, group_pce=gi_pce,
                     weights_cpi=gw_cpi, weights_pce=gw_pce,
                     common=common, scope=scope, notes=notes)


# ----------------------------------------------------------------------------
# The CPI -> PCE bridge
# ----------------------------------------------------------------------------
@dataclass
class BridgeResult:
    """Output of :func:`bridge_nowcast`.

    Attributes
    ----------
    monthly:
        ``[implied, actual, error]`` monthly PCE inflation in %, one row per
        month.  ``implied`` extends **past** the last published PCE month --
        that extension is the forecast.
    yoy:
        The same as 12-month rates.  The forecast months chain the implied
        monthly rates onto the published history, so a 12-month forecast is
        eleven actual months plus one estimate, not a guess about all twelve.
    forecast:
        The months with an implied value and no published PCE: what this page
        exists for.  Columns ``mom``, ``yoy``, ``se`` (the standard deviation of
        the estimator's own past one-month errors) and ``basis``.
    coefficients:
        Rolling slope on the first regressor of the fitted (possibly
        multivariate) model.  Diagnostic only.
    cpi_slope:
        The **univariate** rolling slope of the group's PCE inflation on its own
        CPI inflation -- "how much of a 1pp CPI move turns up in PCE".  Kept
        separate from ``coefficients`` deliberately: once PPI enters the model
        the CPI coefficient becomes a partial slope holding producer prices
        fixed, which is a different quantity, and for a group with no CPI
        counterpart at all it would not be a CPI slope in any sense.  This is
        the column the website labels "pass-through", and it is NaN where the
        group has no CPI side.
    contributions:
        The forecast month's implied contribution per group (pp), so the number
        can be read as a bar chart rather than taken on trust.
    rmse:
        Root mean squared one-month error over the whole fitted history, in pp.
    se:
        The same over the last ``se_window`` months -- the band the forecast is
        actually quoted with, because the estimator's accuracy is
        regime-dependent.
    """

    monthly: pd.DataFrame
    yoy: pd.DataFrame
    forecast: pd.DataFrame
    coefficients: pd.DataFrame
    cpi_slope: pd.DataFrame
    contributions: pd.DataFrame
    rmse: float
    se: float
    se_window: int
    window: int
    scope: str = "headline"
    inputs: list[str] = field(default_factory=list)


def _ols_predict(y: np.ndarray, X: list[np.ndarray], t: int,
                 window: int, min_obs: int) -> tuple[float, float]:
    """Fit on the trailing window EXCLUDING ``t``, then predict ``t``.

    Excluding ``t`` is the whole discipline of a nowcast: on CPI day the PCE for
    that month does not exist, so no fit may use it.  Returns
    ``(prediction, slope on the first regressor)``, both NaN when the window is
    too thin or the month's inputs are incomplete.
    """
    n = len(y)
    design = np.column_stack([np.ones(n)] + X)
    lo = max(0, t - window)
    rows = slice(lo, t)
    ok = np.isfinite(y[rows]) & np.isfinite(design[rows]).all(axis=1)
    if ok.sum() < min_obs or not np.isfinite(design[t]).all():
        return np.nan, np.nan
    A, b = design[rows][ok], y[rows][ok]
    if np.linalg.matrix_rank(A) < A.shape[1]:
        return np.nan, np.nan
    try:
        beta, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return np.nan, np.nan
    return float(design[t] @ beta), float(beta[1]) if len(beta) > 1 else np.nan


def bridge_nowcast(
    cpi_inflation: pd.DataFrame,
    cpi_weights: pd.DataFrame,
    pce_inflation: pd.DataFrame,
    pce_weights: pd.DataFrame,
    conc: Optional[pd.DataFrame] = None,
    ppi: Optional[pd.DataFrame] = None,
    ppi_groups: Optional[dict[str, list[str]]] = None,
    exclude: Optional[set[str]] = None,
    scope: str = "headline",
    window: int = 120,
    min_obs: int = 60,
    periods: int = 12,
    se_window: int = 60,
) -> BridgeResult:
    """Map the published CPI (and PPI) into an implied PCE print, group by group.

    For each group and each month t, fit

        pi^PCE_{g,s} = a + b * pi^CPI_{g,s} + c' * pi^PPI_{g,s}

    on the trailing ``window`` months **excluding t**, and apply it to month t's
    inputs.  Because CPI and PPI for month t are published about two weeks
    before the PCE, the fit can be applied to months where PCE does not exist
    yet -- and those months are the forecast.

    Parameters
    ----------
    ppi:
        Seasonally adjusted monthly PPI inflation, one column per series
        (:func:`ism.ppi.ppi_inflation`).  Optional, and worth a lot: it cuts the
        medical-services error by more than half, and it is the only monthly
        input to the PCE-only groups.
    ppi_groups:
        ``{group: [ppi column]}`` from :func:`ism.ppi.group_regressors`.
    exclude:
        PCE category keys to drop -- pass
        ``ism.decomp_pipeline.core_exclusions()`` for **core** PCE.
    scope:
        A label carried through to the result (``"headline"`` / ``"core"``).
    se_window:
        Months of recent error used for the forecast's standard error.  The
        estimator's accuracy is strongly regime-dependent -- one-month RMSE runs
        about 0.17pp through the high-inflation 1970s and 1980s and about
        0.04pp through the calm 2010s -- so a full-sample band is wrong for
        today in one direction and a 2010s band is wrong in the other.  Sixty
        months is a compromise that still contains the 2021-22 surge, and the
        full-sample figure is reported alongside as ``rmse``.

    A group with neither a CPI counterpart nor a PPI series is carried at its
    own trailing 12-month average.  That is deliberately dumb and is labelled as
    such; the alternative is pretending to forecast an imputation.
    """
    conc = conc if conc is not None else load_concordance()
    common = common_groups(conc)
    scope_groups_ = scope_groups(conc)
    ppi_groups = ppi_groups or {}

    map_cpi = conc[conc.gauge == "cpi"].set_index("key")["group"]
    map_pce = conc[conc.gauge == "pce"].set_index("key")["group"]

    if exclude:
        keep = [c for c in pce_inflation.columns if c not in exclude]
        pce_inflation = pce_inflation[keep]
        pce_weights = pce_weights.reindex(columns=keep)

    gi_cpi, _ = group_panel(cpi_inflation, cpi_weights, map_cpi)
    gi_pce, gw_pce = group_panel(pce_inflation, pce_weights, map_pce)

    # The index runs to the end of the CPI, not to the end of the PCE: the
    # months in between are precisely the ones worth forecasting.
    idx = gi_cpi.index.union(gi_pce.index)
    if ppi is not None and not ppi.empty:
        idx = idx.union(ppi.index)
    idx = idx.sort_values()
    last_cpi = gi_cpi.dropna(how="all").index.max()
    idx = idx[idx <= last_cpi]

    gi_cpi = gi_cpi.reindex(idx)
    gi_pce, gw_pce = gi_pce.reindex(idx), gw_pce.reindex(idx)
    ppi = ppi.reindex(idx) if ppi is not None and not ppi.empty else None

    implied = pd.DataFrame(np.nan, index=idx, columns=list(gi_pce.columns))
    slopes = pd.DataFrame(np.nan, index=idx, columns=list(gi_pce.columns))
    cpi_slope = pd.DataFrame(np.nan, index=idx, columns=list(gi_pce.columns))
    used: dict[str, list[str]] = {}

    for g in gi_pce.columns:
        regs, names = [], []
        if g in common and g in gi_cpi.columns:
            regs.append(gi_cpi[g].to_numpy(float)); names.append("CPI")
        for col in ppi_groups.get(g, []):
            if ppi is not None and col in ppi.columns:
                regs.append(ppi[col].to_numpy(float)); names.append(col)
        if not regs:
            continue
        used[g] = names
        y = gi_pce[g].to_numpy(float)
        col_i = implied.columns.get_loc(g)
        has_cpi = names and names[0] == "CPI"
        for t in range(len(idx)):
            pred, slope = _ols_predict(y, regs, t, window, min_obs)
            implied.iat[t, col_i] = pred
            slopes.iat[t, col_i] = slope
            if has_cpi:
                # the plain CPI pass-through, fitted on CPI alone, so the number
                # the site labels "pass-through" keeps meaning that
                _, b_uni = _ols_predict(y, [regs[0]], t, window, min_obs)
                cpi_slope.iat[t, col_i] = b_uni

    # Groups with no monthly input at all: carry their own trailing average.
    for g in gi_pce.columns:
        if g in used:
            continue
        implied[g] = gi_pce[g].shift(1).rolling(periods, min_periods=6).mean()

    # Weights for a forecast month are not published either -- BEA releases the
    # expenditure shares WITH the PCE, so on CPI day month t's weights do not
    # exist any more than its prices do. Every month therefore aggregates on the
    # last shares known BEFORE it. Using month t's own shares where they happen
    # to exist would make the historical error bands flatter than the live
    # forecast can ever be; measured, that shortcut moved a print by 0.004pp.
    w = (gw_pce.shift(1).ffill().reindex(columns=implied.columns)
         .where(implied.notna()))
    tot = w.sum(axis=1, min_count=1)
    implied_agg = (w * implied).sum(axis=1, min_count=1) / tot.replace(0, np.nan)
    actual_agg = aggregate(gi_pce, gw_pce)

    monthly = pd.DataFrame({"implied": implied_agg, "actual": actual_agg})
    monthly["error"] = monthly["implied"] - monthly["actual"]
    resid = monthly["error"].dropna()
    rmse = float(np.sqrt((resid ** 2).mean())) if len(resid) else float("nan")
    recent = resid.tail(se_window)
    se = float(np.sqrt((recent ** 2).mean())) if len(recent) else rmse

    # 12-month rates. For a forecast month the published months are used as
    # published and only the missing ones are filled with the estimate, so a
    # one-month-ahead 12-month forecast carries one month of model error, not
    # twelve.
    spliced = monthly["actual"].copy()
    spliced[spliced.isna()] = monthly["implied"][spliced.isna()]
    yoy = pd.DataFrame({
        "implied": yoy_from_monthly(spliced, periods),
        "actual": yoy_from_monthly(monthly["actual"], periods),
    })
    yoy["error"] = yoy["implied"] - yoy["actual"]

    # The forecast: months with an estimate and no published PCE.
    pending = monthly.index[monthly["implied"].notna() & monthly["actual"].isna()]
    forecast = pd.DataFrame({
        "mom": monthly.loc[pending, "implied"],
        "yoy": yoy.loc[pending, "implied"],
        "se": se,
        "basis": ["CPI" + (" + PPI" if ppi is not None else "")] * len(pending),
    })

    contributions = pd.DataFrame()
    target = pending[-1] if len(pending) else (
        monthly["implied"].dropna().index[-1] if monthly["implied"].notna().any() else None)
    if target is not None:
        wn = w.loc[target] / tot.loc[target] if np.isfinite(tot.loc[target]) else w.loc[target]
        contributions = pd.DataFrame({
            "group": implied.columns,
            "implied_rate": implied.loc[target].to_numpy(),
            "weight": wn.to_numpy(),
            "contribution": (wn * implied.loc[target]).to_numpy(),
            "role": ["scope" if g in scope_groups_ else "common" for g in implied.columns],
            "inputs": [", ".join(used.get(g, [])) or "own trailing mean"
                       for g in implied.columns],
        }).dropna(subset=["contribution"]).sort_values(
            "contribution", ascending=False).reset_index(drop=True)
        contributions.attrs["month"] = str(target.date())
        contributions.attrs["is_forecast"] = bool(len(pending))

    return BridgeResult(monthly=monthly, yoy=yoy, forecast=forecast,
                        coefficients=slopes, cpi_slope=cpi_slope,
                        contributions=contributions,
                        rmse=rmse, se=se, se_window=se_window,
                        window=window, scope=scope,
                        inputs=sorted({n for v in used.values() for n in v}))
