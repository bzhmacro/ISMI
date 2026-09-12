"""
ism.trim_engine
===============

Trimmed-mean and weighted-median inflation from a cross-section of category
price changes -- the "limited-influence estimator" family behind the Cleveland
Fed's **median CPI** and **16% trimmed-mean CPI** and the Dallas Fed's
**trimmed mean PCE**.

The module is written to the same contract as :mod:`ism.engine`: it consumes an
``inflation_panel`` [periods x categories] and a ``weights`` frame of the same
shape and knows nothing about which country or price gauge produced them.  That
is what lets the same code run on BEA PCE, BLS CPI item strata, ONS COICOP
classes, and so on.

The maths, in order
-------------------
Write pi_{i,t} for the month-over-month log price change of category i (the
panel this module is handed) and w_{i,t} for its expenditure weight.

**(T1) Seasonal adjustment.**  The published measures are built from
*seasonally adjusted* monthly changes -- a January price reset is a seasonal
event, not an inflation shock, and leaving it in puts the same categories in the
tails every year.  Our category panels are NSA (the right input for the ISM
momentum model, which differences them again), so the seasonal is removed here:

    pi^sa_{i,t} = pi_{i,t} - s_{i,m(t)}                                    (T1)

where ``s_{i,m}`` are month effects estimated per category and constrained to
average zero over the twelve calendar months, so annual inflation is untouched.
Three estimators are offered (``sa="none" | "dummy" | "rolling"``); see
:func:`seasonal_factors`.

**(T2) Annualisation.**  Agencies publish the cross-section at an annual rate:

    a_{i,t} = 100 * ( (1 + pi^sa_{i,t}/100)^P - 1 )     ("compound")       (T2)
    a_{i,t} = P * pi^sa_{i,t}                           ("log")

with P periods per year (12 monthly, 4 quarterly).  "compound" reproduces the
agencies' convention; "log" is the linear approximation and is exposed because
it keeps the aggregation exactly additive.

**(T3) The cross-sectional trim.**  Sort the categories present in month t by
a_{i,t}, form the cumulative normalised weight, discard the lowest ``lower``
and highest ``upper`` fractions *of weight* (not of categories), and take the
weighted mean of what is left:

    m_t = ( sum_{i in R_t} w~_{i,t} a_{i,t} ) / ( sum_{i in R_t} w~_{i,t} )  (T3)

where R_t is the retained set and ``w~`` is the retained weight -- the two
categories straddling each trim point enter *partially*, with only the slice of
their weight that falls inside the retained interval.  Partial inclusion is what
makes the estimator continuous in the trim fractions (and is what both Reserve
Banks do).  ``lower = upper = 0.5`` collapses to the **weighted median**: the
value of the category holding the 50th percentile of the weight.

**(T4) Chaining.**  The published series are index levels.  De-annualise the
retained mean back to a period rate and compound:

    I_t = I_{t-1} * (1 + m_t / (100 * P))            ("log" convention)
    I_t = I_{t-1} * (1 + m_t / 100)^(1/P)            ("compound" convention)   (T4)

12-month inflation is then the 12-month change of I, which is how the Cleveland
Fed's "Median CPI, % change year to year" is defined -- *not* a trim of the
cross-section of 12-month changes, which is a different (and noisier) object.

Why trim at all
---------------
Cross-sectional price-change distributions are fat-tailed and skewed, so the
mean of the cross-section (= headline inflation) is a high-variance estimator of
its own central tendency.  Trimming buys a large variance reduction for a small
bias, and the bias can be removed by choosing the trim fractions to track a
smooth reference path -- which is exactly how the Dallas Fed arrived at its
asymmetric 24% / 31% cut.  :func:`optimal_trim` reproduces that exercise.

Presets
-------
``MEDIAN_CPI``  Cleveland Fed median CPI (lower = upper = 0.5).
``TRIM16_CPI``  Cleveland Fed 16% trimmed-mean CPI (8% each tail).
``TRIM_PCE``    Dallas Fed trimmed mean PCE (24% lower, 31% upper).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class TrimConfig:
    """Parameters that define a particular limited-influence estimator.

    Attributes
    ----------
    lower, upper:
        Fractions of the *weight* discarded from the bottom and top of the
        sorted cross-section.  ``0.08 / 0.08`` is the Cleveland 16% trim;
        ``0.24 / 0.31`` the Dallas trimmed mean PCE; ``0.5 / 0.5`` the weighted
        median.  Must satisfy ``lower + upper <= 1``.
    sa:
        Seasonal-adjustment estimator applied to the panel before trimming:
        ``"none"``, ``"dummy"`` (full-sample month effects) or ``"rolling"``
        (trailing-window month effects; uses no future data).
    sa_window:
        Window in periods for ``sa="rolling"``.  120 = ten years of monthly data.
    annualize:
        ``"compound"`` (agency convention, Eq. T2) or ``"log"`` (linear).
    periods_per_year:
        12 for monthly panels, 4 for quarterly.  Sets both the annualisation
        factor and the horizon of the year-over-year series.
    weight_lag:
        Periods by which the weight vector lags the price change.  0 = use the
        weights of month t (Cleveland / Dallas convention, the weights being
        price-updated expenditure shares); 1 = strict Laspeyres.
    min_categories:
        Months with fewer than this many usable categories produce NaN rather
        than a trimmed mean estimated off a handful of series.
    """

    lower: float = 0.08
    upper: float = 0.08
    sa: str = "rolling"
    sa_window: int = 120
    annualize: str = "compound"
    periods_per_year: int = 12
    weight_lag: int = 0
    min_categories: int = 10

    def __post_init__(self):
        if not (0.0 <= self.lower <= 1.0) or not (0.0 <= self.upper <= 1.0):
            raise ValueError("lower/upper must lie in [0, 1]")
        if self.lower + self.upper > 1.0 + 1e-12:
            raise ValueError("lower + upper must not exceed 1")
        if self.sa not in ("none", "dummy", "rolling"):
            raise ValueError("sa must be 'none', 'dummy' or 'rolling'")
        if self.annualize not in ("compound", "log"):
            raise ValueError("annualize must be 'compound' or 'log'")

    @property
    def is_median(self) -> bool:
        """True when the configuration collapses to the weighted median."""
        return abs(self.lower + self.upper - 1.0) < 1e-9


#: Cleveland Fed median CPI.
MEDIAN_CPI = TrimConfig(lower=0.5, upper=0.5)
#: Cleveland Fed 16% trimmed-mean CPI (8% trimmed from each tail).
TRIM16_CPI = TrimConfig(lower=0.08, upper=0.08)
#: Dallas Fed trimmed mean PCE (asymmetric: 24% lower tail, 31% upper tail).
TRIM_PCE = TrimConfig(lower=0.24, upper=0.31)

PRESETS = {"median": MEDIAN_CPI, "trim16": TRIM16_CPI, "trim_pce": TRIM_PCE}


# ----------------------------------------------------------------------------
# (T1) Seasonal adjustment
# ----------------------------------------------------------------------------
def seasonal_factors(
    panel: pd.DataFrame,
    method: str = "rolling",
    window: int = 120,
    periods_per_year: int = 12,
) -> pd.DataFrame:
    """Month effects ``s_{i,m(t)}`` to subtract from each category (Eq. T1).

    Both estimators regress a category's period-over-period change on calendar
    dummies and then re-centre the twelve coefficients to sum to zero, so
    removing them leaves the average annual change unchanged -- only the
    *within-year* pattern moves.  This is a deliberately transparent stand-in
    for the X-13 adjustment the agencies apply; it captures the stable part of
    the seasonal (which is what matters for keeping January resets out of the
    tails) without the moving-average filters, outlier detection and trading-day
    corrections of a full seasonal program.  See ``docs/trim_methodology.md``
    for what this costs in fidelity.

    Parameters
    ----------
    panel:
        [periods x categories] of period-over-period changes, NSA.
    method:
        ``"none"`` -> all-zero factors (pass the panel through unchanged).

        ``"dummy"`` -> one set of month effects per category estimated on the
        **whole sample**.  Simple and stable, but it uses future data at every
        date, so it is a revised/final-vintage adjustment.

        ``"rolling"`` -> month effects re-estimated at every date from the
        trailing ``window`` periods only.  Uses no future information, so the
        resulting series is the one you could have computed in real time; it
        also lets the seasonal pattern drift (grocery and apparel seasonals in
        particular have moved a lot since the 1990s).
    window:
        Trailing window for ``method="rolling"``.
    periods_per_year:
        12 (monthly) or 4 (quarterly).

    Returns
    -------
    DataFrame of the same shape as ``panel``: the factor to subtract at each
    (period, category).  NaN where no factor could be estimated.
    """
    P = periods_per_year
    if method == "none":
        return pd.DataFrame(0.0, index=panel.index, columns=panel.columns)

    season = _season_of(panel.index, P)
    values = panel.to_numpy(dtype=float)
    n, k = values.shape
    out = np.full((n, k), np.nan)

    if method == "dummy":
        for j in range(k):
            col = values[:, j]
            fac = _centred_season_means(col, season, P)
            if fac is None:
                continue
            out[:, j] = fac[season]
        return pd.DataFrame(out, index=panel.index, columns=panel.columns)

    if method == "rolling":
        # A trailing window needs at least two observations per calendar period
        # before a month effect means anything; with 12 months that is 24 rows.
        min_rows = 2 * P
        for j in range(k):
            col = values[:, j]
            for t in range(n):
                start = max(0, t - window + 1)
                sl = slice(start, t + 1)
                if (t - start + 1) < min_rows:
                    continue
                fac = _centred_season_means(col[sl], season[sl], P)
                if fac is None:
                    continue
                out[t, j] = fac[season[t]]
        return pd.DataFrame(out, index=panel.index, columns=panel.columns)

    raise ValueError(f"unknown seasonal method {method!r}")


def _season_of(index: pd.Index, periods_per_year: int) -> np.ndarray:
    """0-based calendar position (month 0..11, or quarter 0..3) of each row."""
    idx = pd.DatetimeIndex(index)
    if periods_per_year == 12:
        return idx.month.to_numpy() - 1
    if periods_per_year == 4:
        return idx.quarter.to_numpy() - 1
    # Fall back to position within the year for exotic frequencies.
    return np.arange(len(idx)) % periods_per_year


def _centred_season_means(
    y: np.ndarray, season: np.ndarray, periods_per_year: int
) -> Optional[np.ndarray]:
    """Mean of ``y`` within each calendar slot, re-centred to sum to zero.

    Returns ``None`` when any calendar slot has no finite observation -- a
    partial factor vector would shift the annual average, which is exactly what
    the centring is there to prevent.
    """
    fac = np.full(periods_per_year, np.nan)
    for m in range(periods_per_year):
        sel = (season == m) & np.isfinite(y)
        if not sel.any():
            return None
        fac[m] = y[sel].mean()
    return fac - fac.mean()


def deseasonalise(
    panel: pd.DataFrame,
    method: str = "rolling",
    window: int = 120,
    periods_per_year: int = 12,
) -> pd.DataFrame:
    """``panel`` minus its seasonal factors (Eq. T1).

    Where no factor could be estimated the raw (NSA) value is kept rather than
    dropped: early sample months then behave exactly as they do in the
    unadjusted series instead of silently vanishing from the cross-section.
    """
    fac = seasonal_factors(panel, method=method, window=window,
                           periods_per_year=periods_per_year)
    return panel - fac.fillna(0.0)


# ----------------------------------------------------------------------------
# (T2) Annualisation
# ----------------------------------------------------------------------------
def annualise(panel: pd.DataFrame | pd.Series, method: str = "compound",
              periods_per_year: int = 12):
    """Period rate (%, log or simple) at an annual rate (Eq. T2)."""
    if method == "log":
        return panel * float(periods_per_year)
    return 100.0 * ((1.0 + panel / 100.0) ** periods_per_year - 1.0)


def deannualise(rate: pd.Series | float, method: str = "compound",
                periods_per_year: int = 12):
    """Inverse of :func:`annualise` -- back to a per-period rate in %."""
    if method == "log":
        return rate / float(periods_per_year)
    return 100.0 * ((1.0 + rate / 100.0) ** (1.0 / periods_per_year) - 1.0)


# ----------------------------------------------------------------------------
# (T3) The cross-sectional estimator
# ----------------------------------------------------------------------------
def trimmed_mean(
    values: np.ndarray,
    weights: np.ndarray,
    lower: float = 0.08,
    upper: float = 0.08,
) -> float:
    """Weighted trimmed mean of one cross-section (Eq. T3).

    ``lower`` and ``upper`` are fractions of total weight removed from the
    bottom and top of the *sorted-by-value* distribution.  Categories that
    straddle a trim point are included **partially**: only the slice of their
    weight lying inside the retained interval counts, which keeps the estimator
    continuous in ``lower``/``upper`` and matches both Reserve Banks' published
    implementations.

    ``lower + upper == 1`` degenerates to the weighted median (the value at the
    ``lower`` quantile of weight), and is handled as that limit.

    NaN values (and non-positive or NaN weights) are dropped before the weight
    is renormalised, so a category that is simply absent this month does not
    shift the trim points.
    """
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not ok.any():
        return np.nan
    v, w = v[ok], w[ok]

    order = np.argsort(v, kind="mergesort")   # stable: ties keep panel order
    v, w = v[order], w[order]
    w = w / w.sum()

    if lower + upper >= 1.0 - 1e-12:
        return weighted_percentile(v, w, lower, presorted=True)

    cum_lo = np.cumsum(w)          # weight at or below each category
    cum_hi = cum_lo - w            # weight strictly below each category
    lo, hi = lower, 1.0 - upper

    # Weight of each category that falls inside the retained interval (lo, hi).
    keep = np.clip(np.minimum(cum_lo, hi) - np.maximum(cum_hi, lo), 0.0, None)
    total = keep.sum()
    if total <= 0:
        return np.nan
    return float(np.dot(keep, v) / total)


def weighted_percentile(
    values: np.ndarray,
    weights: np.ndarray,
    q: float = 0.5,
    presorted: bool = False,
) -> float:
    """Value of the category holding the ``q`` quantile of the weight.

    The Cleveland Fed's median CPI is ``q = 0.5``: the *component's own*
    inflation rate, not an interpolation between neighbours -- which is why the
    published median is always some real category's price change and why the
    Cleveland Fed can name it each month.
    """
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    if not presorted:
        ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
        if not ok.any():
            return np.nan
        v, w = v[ok], w[ok]
        order = np.argsort(v, kind="mergesort")
        v, w = v[order], w[order]
        w = w / w.sum()
    cum = np.cumsum(w)
    idx = int(np.searchsorted(cum, q, side="left"))
    idx = min(idx, len(v) - 1)
    return float(v[idx])


def trim_membership(
    values: np.ndarray,
    weights: np.ndarray,
    lower: float = 0.08,
    upper: float = 0.08,
) -> np.ndarray:
    """Per-category label for one cross-section, for the drivers panel.

    Returns an integer array aligned with ``values``:
    ``-1`` cut from the bottom, ``0`` retained, ``+1`` cut from the top,
    ``-2`` unusable (NaN value or weight).  A category straddling a trim point
    is labelled by where the *majority* of its weight fell, so the label answers
    "was this month's print driven by things in the middle or in the tail?".
    """
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    out = np.full(len(v), -2, dtype=int)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not ok.any():
        return out

    idx = np.where(ok)[0]
    vv, ww = v[ok], w[ok]
    order = np.argsort(vv, kind="mergesort")
    idx, vv, ww = idx[order], vv[order], ww[order]
    ww = ww / ww.sum()

    cum_lo = np.cumsum(ww)
    cum_hi = cum_lo - ww
    lo, hi = lower, max(lower, 1.0 - upper)

    below = np.clip(np.minimum(cum_lo, lo) - cum_hi, 0.0, None)
    above = np.clip(cum_lo - np.maximum(cum_hi, hi), 0.0, None)
    inside = np.clip(np.minimum(cum_lo, hi) - np.maximum(cum_hi, lo), 0.0, None)

    stacked = np.vstack([below, inside, above])          # rows -> -1, 0, +1
    out[idx] = np.argmax(stacked, axis=0) - 1
    return out


# ----------------------------------------------------------------------------
# Panel-level driver
# ----------------------------------------------------------------------------
@dataclass
class TrimResult:
    """Everything :func:`compute_trim` produces, for charts and audit.

    Attributes
    ----------
    rate:
        The trimmed/median statistic, at an annual rate, one value per period
        (Eq. T3).  This is the "1-month annualised" number the Reserve Banks
        headline.
    index:
        The chained price index implied by ``rate`` (Eq. T4), rebased to 100 at
        the first period with a value.
    yoy:
        12-month (``periods_per_year``-period) change of ``index``, in %.
    sa_panel:
        The seasonally adjusted, annualised cross-section actually trimmed --
        keep it to reproduce any month by hand.
    weights:
        The normalised weights used, after lagging and after dropping
        categories with no usable value.
    membership:
        Integer panel from :func:`trim_membership` (-1 bottom cut, 0 retained,
        +1 top cut, -2 unusable).
    n_categories:
        Usable categories per period.
    config:
        The :class:`TrimConfig` used.
    """

    rate: pd.Series
    index: pd.Series
    yoy: pd.Series
    sa_panel: pd.DataFrame
    weights: pd.DataFrame
    membership: pd.DataFrame
    n_categories: pd.Series
    config: TrimConfig

    def to_frame(self) -> pd.DataFrame:
        """Headline series as a tidy frame (rate, index, yoy, n)."""
        return pd.concat(
            [self.rate.rename("rate_ann"), self.index.rename("index"),
             self.yoy.rename("yoy"), self.n_categories.rename("n_categories")],
            axis=1,
        )


def compute_trim(
    inflation_panel: pd.DataFrame,
    weights: pd.DataFrame,
    cfg: TrimConfig | None = None,
) -> TrimResult:
    """End-to-end limited-influence estimator (Eqs. T1-T4).

    Parameters
    ----------
    inflation_panel:
        Period-over-period category inflation in % (``100 * dln P``), rows =
        periods (sorted DatetimeIndex), columns = categories.  **NSA** -- the
        seasonal is removed here according to ``cfg.sa``.
    weights:
        Expenditure weights, same rows/columns.  Rows are renormalised over the
        categories that actually have a value in that period, so a static or a
        time-varying weight vector both work.
    cfg:
        :class:`TrimConfig`; defaults to the Cleveland 16% trim.

    Returns
    -------
    :class:`TrimResult`
    """
    cfg = cfg or TrimConfig()
    P = cfg.periods_per_year

    panel = inflation_panel.sort_index()
    w = weights.reindex(index=panel.index, columns=panel.columns)
    if cfg.weight_lag:
        w = w.shift(cfg.weight_lag)

    sa = deseasonalise(panel, method=cfg.sa, window=cfg.sa_window,
                       periods_per_year=P)
    ann = annualise(sa, method=cfg.annualize, periods_per_year=P)

    values = ann.to_numpy(dtype=float)
    wm = w.to_numpy(dtype=float)
    n_rows = len(panel.index)

    rates = np.full(n_rows, np.nan)
    counts = np.zeros(n_rows, dtype=int)
    member = np.full(values.shape, -2, dtype=int)
    wnorm = np.full(values.shape, np.nan)

    for t in range(n_rows):
        v_t, w_t = values[t], wm[t]
        ok = np.isfinite(v_t) & np.isfinite(w_t) & (w_t > 0)
        counts[t] = int(ok.sum())
        if counts[t] < cfg.min_categories:
            continue
        wn = np.where(ok, w_t, np.nan)
        wn = wn / np.nansum(wn)
        wnorm[t] = wn
        rates[t] = trimmed_mean(v_t, w_t, cfg.lower, cfg.upper)
        member[t] = trim_membership(v_t, w_t, cfg.lower, cfg.upper)

    idx = panel.index
    rate = pd.Series(rates, index=idx, name="rate_ann")
    index = chain_index(rate, method=cfg.annualize, periods_per_year=P)
    yoy = 100.0 * (index / index.shift(P) - 1.0)
    yoy.name = "yoy"

    return TrimResult(
        rate=rate,
        index=index,
        yoy=yoy,
        sa_panel=ann,
        weights=pd.DataFrame(wnorm, index=idx, columns=panel.columns),
        membership=pd.DataFrame(member, index=idx, columns=panel.columns),
        n_categories=pd.Series(counts, index=idx, name="n_categories"),
        config=cfg,
    )


# ----------------------------------------------------------------------------
# (T4) Chaining and horizon aggregation
# ----------------------------------------------------------------------------
def chain_index(rate_ann: pd.Series, method: str = "compound",
                periods_per_year: int = 12, base: float = 100.0) -> pd.Series:
    """Chain an annualised period rate into a price index (Eq. T4).

    Leading NaNs are skipped; an interior NaN carries the index forward
    unchanged (the level is not knowable, but breaking the chain would discard
    every later observation).
    """
    per = deannualise(rate_ann, method=method, periods_per_year=periods_per_year)
    out = pd.Series(np.nan, index=rate_ann.index, dtype=float)
    level = None
    for i, v in enumerate(per.to_numpy()):
        if level is None:
            if not np.isfinite(v):
                continue
            level = base            # first usable period anchors the index
            out.iloc[i] = level
            continue
        if np.isfinite(v):
            level = level * (1.0 + v / 100.0)
        out.iloc[i] = level
    out.name = "index"
    return out


def horizon_rate(index: pd.Series, horizon: int = 12,
                 periods_per_year: int = 12) -> pd.Series:
    """Annualised inflation over ``horizon`` periods of a chained index.

    ``horizon = periods_per_year`` gives the year-over-year rate; the Dallas Fed
    also publishes ``horizon = 6``.
    """
    g = index / index.shift(horizon)
    return 100.0 * (g ** (periods_per_year / horizon) - 1.0)


# ----------------------------------------------------------------------------
# Choosing the trim: the Dallas Fed's criterion
# ----------------------------------------------------------------------------
def optimal_trim(
    inflation_panel: pd.DataFrame,
    weights: pd.DataFrame,
    reference: pd.Series,
    lower_grid: Iterable[float] = tuple(np.arange(0.0, 0.51, 0.01)),
    upper_grid: Iterable[float] = tuple(np.arange(0.0, 0.51, 0.01)),
    cfg: TrimConfig | None = None,
    criterion: str = "rmse",
) -> pd.DataFrame:
    """Grid-search the trim fractions that best track a smooth reference path.

    This is the exercise behind the Dallas Fed's asymmetric 24% / 31% cut and
    the Cleveland Fed's 8% / 8%: the trim is not a free aesthetic choice but the
    minimiser of distance to a *centred* moving average of headline inflation,
    which stands in for the unobservable trend.  Asymmetry falls out of the data
    rather than being imposed -- the PCE cross-section is right-skewed, so an
    estimator that trims equally from both tails inherits a downward bias, and
    the fix is to cut more from the top.

    Parameters
    ----------
    reference:
        The trend proxy, at an annual rate and on the panel's own index -- e.g.
        a centred 36-month moving average of headline inflation.
    criterion:
        ``"rmse"`` (root mean squared deviation from ``reference``) or ``"mad"``
        (mean absolute deviation).

    Returns
    -------
    Tidy frame ``[lower, upper, score, n]`` sorted best-first.  Because the
    reference is centred it uses future data by construction: this is an
    in-sample calibration exercise, not a real-time rule.
    """
    cfg = cfg or TrimConfig()
    rows = []
    for lo in lower_grid:
        for up in upper_grid:
            if lo + up >= 1.0:
                continue
            c = TrimConfig(
                lower=float(lo), upper=float(up), sa=cfg.sa,
                sa_window=cfg.sa_window, annualize=cfg.annualize,
                periods_per_year=cfg.periods_per_year,
                weight_lag=cfg.weight_lag, min_categories=cfg.min_categories,
            )
            res = compute_trim(inflation_panel, weights, c)
            both = pd.concat([res.rate, reference], axis=1).dropna()
            if both.empty:
                continue
            err = both.iloc[:, 0] - both.iloc[:, 1]
            score = float(np.sqrt((err ** 2).mean())) if criterion == "rmse" \
                else float(err.abs().mean())
            rows.append({"lower": float(lo), "upper": float(up),
                         "score": score, "n": int(len(both))})
    out = pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
    return out


def centred_moving_average(series: pd.Series, window: int = 36) -> pd.Series:
    """Centred moving average used as the trend proxy in :func:`optimal_trim`."""
    return series.rolling(window=window, center=True,
                          min_periods=window).mean()
