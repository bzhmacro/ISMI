"""
ism.wage_engine
===============

The maths of the **wage model** (Model 5). Every function maps onto a numbered
equation in ``docs/wage_methodology.md``; read the two side by side.

    Eq. (W1)  pi*_t = pi*_{t-1} + k(q) (pi_t - pi*_{t-1})      trend_inflation()
    Eq. (W2)  catchup_t = pi^4q_t - pi*_{t-4}                  catchup()
    Eq. (W3)  lambda_t = sum_j c_{j,t} e_j                     indexation_intensity()
    Eq. (W4)  wage equation (indexation-interacted catch-up)   fit_wage_equation()
    Eq. (W5)  price equation (with a fiscal-transfer term)     fit_price_equation()
    Eq. (W6)  Lambda_t : 4q wage response to a price surprise  price_to_wage_gain()
    Eq. (W7)  M       : 4q price response to a wage impulse    wage_to_price_gain()
    Eq. (W8)  G_t = Lambda_t * M                               spiral_gain()
    Eq. (W9)  fiscal reaction function                         fit_fiscal_rule()
    Eq. (W10) EWI_t : effective wage index by income group     effective_wage_index()
    Eq. (W11) subsidy-neutral real EWI                         real_effective_wage()
    Eq. (W12) simulate the loop after an energy shock          simulate_loop()

Design notes
------------
* **Quarterly.** The 1970s indexation episodes and the 2021-24 one are both
  quarterly-resolvable, the national-accounts transfer data are quarterly, and
  a quarterly system is what Bernanke & Blanchard (2025) estimate -- so parity
  with a published, replicated specification is available at this frequency
  and not at monthly.
* **Growth rates are annualised log differences, 400*dlog.** One convention
  everywhere, including the y/y "catch-up" term, which is the 4-quarter log
  change annualised (i.e. 100*[log x_t - log x_{t-4}]).
* **No statsmodels.** Estimation is plain least squares with a linear
  restriction, implemented in numpy, because the browser twin
  (``web/wage_engine.js``) has to reproduce it to 1e-9. A dependency we cannot
  mirror in JavaScript is a dependency that breaks the parity test.
* **Nothing is hard-coded that the site exposes as a control.** Lag length,
  the anchoring gain q, the channel elasticities e_j, the estimation window and
  the homogeneity switch are all parameters.

Why this specification and not Bernanke-Blanchard's as published
---------------------------------------------------------------
B&B's wage equation carries a *constant* catch-up coefficient, and in their US
pre-COVID sample it is insignificant (sum = -0.024, p = 0.77). Theory
(Afrouzi, Blanco, Drenik & Hurst 2024) and euro-area evidence (ECB Economic
Bulletin 1/2025) both say the coefficient should be state-dependent. Rather
than filter a latent time-varying parameter, we make the state **observable**:
lambda_t is built from the institutional coverage database (who is indexed to
what, by country and year) and interacted with the catch-up term. The
published constant-coefficient specification is nested at lambda_t == 1, and
``fit_wage_equation(..., interact=False)`` estimates exactly that -- which is
how the engine is validated against B&B's published coefficients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

PPY = 4  # periods per year; the wage model is quarterly throughout


# ============================================================================
# Configuration
# ============================================================================
@dataclass(frozen=True)
class WageConfig:
    """Parameters that define one wage-model specification.

    Attributes
    ----------
    lags:
        Number of own/other lags in the wage and price equations (B&B use 4).
    anchor_q:
        Signal-to-noise ratio of the local-level filter that produces trend
        inflation pi* (Eq. W1). q -> 0 is a perfectly anchored trend; large q
        makes pi* track realised inflation one-for-one. This is the model's
        "anchoring" dial, the observable counterpart of B&B's gamma.
    homogeneity:
        Impose sum(own-lag coefficients) + sum(trend coefficients) = 1 in the
        wage equation and sum(price lags) + sum(wage terms) = 1 in the price
        equation, so the long-run Phillips curve is vertical.
    elasticities:
        Pass-through elasticity e_j of each indexation channel (Eq. W3).
        Defaults are the literature's central estimates:
          automatic  0.90  Card (1986) marginal escalator elasticity 0.75-0.95
          public     1.00  statutory indexation of public pay is mechanical
          minwage    0.35  Cengiz et al. (2019): spillovers are ~40% of the
                           total wage gain and die out ~$3 above the floor
          benchmark  0.30  ECB OP 299 panel: 0.3-0.5pp private wage response
                           per 1pp of indexed public wage growth
    window:
        Rolling estimation window in quarters for the time-varying version
        (None = full sample).
    """

    lags: int = 4
    anchor_q: float = 0.05
    homogeneity: bool = True
    elasticities: Dict[str, float] = field(
        default_factory=lambda: {
            "automatic": 0.90,
            "public": 1.00,
            "minwage": 0.35,
            "benchmark": 0.30,
        }
    )
    window: Optional[int] = 80


# ============================================================================
# Eq. (W1) - trend inflation / the expectations anchor
# ============================================================================
def kalman_gain(q: float) -> float:
    """Steady-state Kalman gain of a random-walk-plus-noise model.

    For pi_t = tau_t + e_t, tau_t = tau_{t-1} + n_t, with signal-to-noise
    q = var(n)/var(e), the steady-state gain solves k^2 + q k - q = 0, i.e.

        k = (sqrt(q^2 + 4q) - q) / 2.

    q = 0 gives k = 0 (a constant trend: perfectly anchored expectations);
    q -> infinity gives k -> 1 (pi* = last quarter's inflation: no anchor).
    This is the fixed-gain limit of the Stock-Watson (2007) UCSV model, chosen
    over the full stochastic-volatility version precisely because a fixed gain
    is a single readable number that the site can put on a slider and the
    browser twin can reproduce exactly.
    """
    if q <= 0:
        return 0.0
    return (np.sqrt(q * q + 4.0 * q) - q) / 2.0


def trend_inflation(pi: pd.Series, q: float = 0.05,
                    init: Optional[float] = None) -> pd.Series:
    """Eq. (W1). Trend inflation pi*_t from the local-level filter.

    The filter is run on whatever inflation series is passed (annualised
    quarterly, or y/y). ``init`` defaults to the mean of the first four
    observations, which keeps the start-up transient short without peeking at
    the rest of the sample.
    """
    k = kalman_gain(q)
    vals = pi.to_numpy(dtype=float)
    out = np.empty_like(vals)
    level = float(np.nanmean(vals[:PPY])) if init is None else float(init)
    for i, x in enumerate(vals):
        if np.isfinite(x):
            level = level + k * (x - level)
        out[i] = level
    return pd.Series(out, index=pi.index, name="pistar")


# ============================================================================
# Eq. (W2) - the catch-up term
# ============================================================================
def rolling_trend_gap(x: pd.Series, window: int = 40,
                      min_periods: int = 20) -> pd.Series:
    """Deviation of a series from its own one-sided local linear trend.

    For each t, fit ``x = a + b*time`` by least squares on the ``window``
    observations *ending at t-1*, project one period forward, and return
    ``x_t - projection``. Nothing after t enters, so the series can be computed
    in real time, in a browser, and on the first day of a new quarter.

    A trailing moving average would do the same job badly: real wages trend, and
    a centred window is unavailable at the sample end, so an MA gap inherits a
    bias of half the window's drift. Projecting the fitted trend removes it.
    """
    v = x.to_numpy(dtype=float)
    n = len(v)
    out = np.full(n, np.nan)
    for t in range(n):
        lo = max(0, t - window)
        seg = v[lo:t]
        idx = np.arange(lo, t, dtype=float)
        ok = np.isfinite(seg)
        if int(ok.sum()) < min_periods or not np.isfinite(v[t]):
            continue
        xs, ys = idx[ok], seg[ok]
        xm, ym = xs.mean(), ys.mean()
        denom = float(((xs - xm) ** 2).sum())
        if denom <= 0:
            continue
        b = float(((xs - xm) * (ys - ym)).sum()) / denom
        a = ym - b * xm
        out[t] = v[t] - (a + b * t)
    return pd.Series(out, index=x.index, name="gap")


def real_wage_gap(wage: pd.Series, prices: pd.Series, window: int = 40) -> pd.Series:
    """Eq. (W2). The real-wage catch-up pressure term.

        rw_t     = 100 * log(W_t / P_t)
        catchup_t = -( rw_t - trend_t )

    Positive when the real wage has fallen below the trend it was on -- the
    state in which workers have something to catch up.

    This replaces Bernanke & Blanchard's inflation-surprise catch-up, and the
    replacement is not cosmetic. Their term is realised inflation minus the
    survey expectation formed a year earlier. Reproducing it without a survey,
    by differencing realised inflation against a filtered trend, makes it an
    *exact linear function* of the trend's own lags: with a fixed-gain filter,
    pi_t = pi*_{t-1} + (pi*_t - pi*_{t-1})/k, so the catch-up block and the
    trend block span the same space and the regression explodes -- in our panel
    it returned catch-up coefficients of +54 with a gain k of 0.2, i.e. exactly
    1/k times noise.

    The level formulation has no such defect, and it is the object the
    theoretical literature actually describes: Bernanke & Blanchard's own
    Eq. (2) has wages chase an *aspiration real wage*, and DeLuca & Van
    Zandweghe (2023) make the same point in arguing for an error-correction
    term on the level of the real wage. What we lose is comparability of the
    coefficient with their Table 1; what we gain is a coefficient that means
    something. Both are reported: ``catchup_bb`` keeps the surprise version for
    the validation exercise, flagged as collinear.
    """
    rw = 100.0 * np.log(wage.astype(float) / prices.reindex(wage.index).astype(float))
    return (-rolling_trend_gap(rw.dropna(), window)).rename("catchup")


def catchup(pi_yoy: pd.Series, pistar: pd.Series, horizon: int = PPY) -> pd.Series:
    """The Bernanke & Blanchard inflation-surprise catch-up, kept for reference.

        catchup_bb_t = pi^{yoy}_t - pi*_{t-horizon}

    Retained so the collinearity documented in ``real_wage_gap`` can be
    demonstrated rather than asserted. Do not put it in the same regression as
    a filtered trend.
    """
    return (pi_yoy - pistar.shift(horizon)).rename("catchup_bb")


# ============================================================================
# Eq. (W3) - institutional indexation intensity
# ============================================================================
def indexation_intensity(coverage: pd.DataFrame,
                         elasticities: Optional[Dict[str, float]] = None,
                         ) -> pd.Series:
    """Eq. (W3). lambda_t = sum_j c_{j,t} e_j, clipped to [0, 1].

    ``coverage`` has one column per channel (``automatic``, ``public``,
    ``minwage``, ``benchmark``), each the share of employees covered, indexed
    by date. Missing channels count as zero coverage.

    The clip matters: the channels are not mutually exclusive (a French
    employee can be covered by a SMIC-benchmarked agreement *and* by a formal
    inflation reference), so the raw sum can exceed one. Clipping at one keeps
    lambda interpretable as "the fraction of the wage bill that moves
    one-for-one with past prices".
    """
    el = dict(WageConfig().elasticities)
    if elasticities:
        el.update(elasticities)
    total = None
    for chan, e in el.items():
        if chan not in coverage.columns:
            continue
        contrib = coverage[chan].astype(float).fillna(0.0) * float(e)
        total = contrib if total is None else total + contrib
    if total is None:
        return pd.Series(0.0, index=coverage.index, name="lambda")
    return total.clip(0.0, 1.0).rename("lambda")


# ============================================================================
# Restricted least squares - the estimator behind Eqs. (W4), (W5), (W9)
# ============================================================================
@dataclass
class OLSFit:
    """A least-squares fit, with just enough to report and to simulate."""

    names: List[str]
    beta: np.ndarray
    se: np.ndarray
    resid: np.ndarray
    r2: float
    nobs: int
    index: pd.Index

    def coef(self) -> pd.Series:
        return pd.Series(self.beta, index=self.names, name="coef")

    def stderr(self) -> pd.Series:
        return pd.Series(self.se, index=self.names, name="se")

    def tstat(self) -> pd.Series:
        with np.errstate(divide="ignore", invalid="ignore"):
            return pd.Series(np.where(self.se > 0, self.beta / self.se, np.nan),
                             index=self.names, name="t")

    def for_country(self, country: Optional[str]) -> "pd.Series":
        """Effective coefficients for one country.

        In a partially pooled panel a block is either country-specific, and its
        columns are named ``gw_l1__DE``, or common, and named ``gw_l1``. This
        collapses the two into one canonical series so that everything
        downstream -- the gains, the simulator -- can be written once and does
        not need to know which blocks were pooled.
        """
        out: Dict[str, float] = {}
        for n, b in zip(self.names, self.beta):
            if "__" in n:
                base, c = n.rsplit("__", 1)
                if country is not None and c == country:
                    out[base] = float(b)
            else:
                out.setdefault(n, float(b))
        return pd.Series(out, name=country or "pooled")

    def countries(self) -> List[str]:
        return sorted({n.rsplit("__", 1)[1] for n in self.names if "__" in n})

    def sum_of(self, prefix: str, country: Optional[str] = None) -> float:
        """Sum of the coefficients whose name starts with ``prefix``.

        The published results this engine is validated against (B&B Tables 1-2)
        report sums of lag blocks, not individual lags, so this is the natural
        reporting unit. Pass ``country`` to sum that country's own block in a
        partially pooled fit.
        """
        if country is not None:
            c = self.for_country(country)
            return float(sum(v for n, v in c.items() if n.startswith(prefix)))
        return float(sum(b for n, b in zip(self.names, self.beta)
                         if n.startswith(prefix) and "__" not in n))


def _inv(A: np.ndarray, ridge: float = 1e-10) -> np.ndarray:
    """Inverse by Gauss-Jordan elimination with partial pivoting.

    numpy's ``pinv`` would be the obvious choice, but the browser twin has to
    reproduce this to 1e-9 and there is no SVD in ``web/wage_engine.js``.
    Gauss-Jordan is fifteen lines in both languages and gives bit-comparable
    results on well-conditioned problems; a small ridge on the diagonal, scaled
    to the matrix, keeps a singular block from producing infinities rather than
    silently pseudo-inverting it. Any design matrix that needs more than this
    is one whose coefficients should not be believed anyway.
    """
    k = A.shape[0]
    scale = float(np.trace(A)) / max(k, 1)
    M = A + np.eye(k) * (ridge * (scale if scale > 0 else 1.0))
    aug = np.concatenate([M, np.eye(k)], axis=1)
    for col in range(k):
        piv = col + int(np.argmax(np.abs(aug[col:, col])))
        if abs(aug[piv, col]) < 1e-300:
            continue
        if piv != col:
            aug[[col, piv]] = aug[[piv, col]]
        aug[col] = aug[col] / aug[col, col]
        for r in range(k):
            if r != col and aug[r, col] != 0.0:
                aug[r] = aug[r] - aug[r, col] * aug[col]
    return aug[:, k:]


def restricted_ols(y: np.ndarray, X: np.ndarray, names: Sequence[str],
                   R: Optional[np.ndarray] = None, r: Any = 0.0,
                   index: Optional[pd.Index] = None) -> OLSFit:
    """Least squares subject to linear restrictions ``R'b = r``.

    ``R`` is either a single restriction (a 1-D array of length k) or several
    (a 2-D array, k x m). The restricted estimator is the same closed form
    either way,

        b_r = b + V R (R'VR)^{-1} (r - R'b),     V = (X'X)^{-1}
        V_r = s^2 [ V - V R (R'VR)^{-1} R' V ]

    with (R'VR) a scalar in the one-restriction case and an m x m matrix
    otherwise. Degrees of freedom gain m.

    Several restrictions are needed as soon as the panel gives each country its
    own dynamics: the long-run homogeneity condition sum(a_c) + sum(b_c) = 1
    then has to hold once per country, not once overall, and imposing it as a
    single pooled restriction would let one country's persistence exceed unity
    while another's compensated.

    Standard errors are classical. They understate uncertainty here, because
    the panel is estimated on overlapping four-quarter growth rates and the
    residuals are serially correlated by construction; read the t-statistics as
    indicative.
    """
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    n, k = X.shape
    XtX = X.T @ X
    V = _inv(XtX)
    beta = V @ (X.T @ y)
    dof = n - k
    if R is not None:
        R = np.asarray(R, dtype=float)
        if R.ndim == 1:
            R = R.reshape(-1, 1)
        m = R.shape[1]
        rvec = np.full(m, float(r)) if np.isscalar(r) else np.asarray(r, dtype=float)
        VR = V @ R                                  # k x m
        RVR = R.T @ VR                              # m x m
        if np.all(np.isfinite(RVR)) and abs(np.linalg.det(RVR)) > 1e-300:
            # A single restriction is a scalar divide. Routing it through the
            # ridged Gauss-Jordan inverse instead costs about 1e-11 of accuracy
            # for nothing, and the single-restriction path is the one the
            # single-country equations and the older fits all use.
            RVRinv = (np.array([[1.0 / RVR[0, 0]]]) if m == 1 else _inv(RVR))
            beta = beta + VR @ (RVRinv @ (rvec - R.T @ beta))
            V = V - VR @ RVRinv @ VR.T
            dof = n - k + m
    resid = y - X @ beta
    ssr = float(resid @ resid)
    tss = float(((y - y.mean()) ** 2).sum())
    s2 = ssr / max(dof, 1)
    se = np.sqrt(np.maximum(np.diag(V) * s2, 0.0))
    r2 = 1.0 - ssr / tss if tss > 0 else float("nan")
    return OLSFit(list(names), beta, se, resid, r2, n,
                  index if index is not None else pd.RangeIndex(n))


def _lags(s: pd.Series, lags: Iterable[int], prefix: str) -> pd.DataFrame:
    return pd.DataFrame({f"{prefix}{L}": s.shift(L) for L in lags})


# ============================================================================
# Eq. (W4) - the indexation-augmented wage equation
# ============================================================================
def fit_wage_equation(panel: pd.DataFrame, cfg: Optional[WageConfig] = None,
                      interact: bool = True,
                      sample: Optional[Tuple[str, str]] = None) -> OLSFit:
    """Eq. (W4). Wage growth on its own lags, the anchor, slack and catch-up.

        gw_t = a0 + sum_{k=1..p} a_k gw_{t-k} + sum_k b_k pistar_{t-k}
                  + sum_k c_k slack_{t-k}
                  + sum_k d_k catchup_{t-k}
                  + sum_k dx_k [lambda_{t-k} * catchup_{t-k}]
                  + e1 gpty_{t-1} + f1 dmw_t + u_t

    subject to sum(a) + sum(b) = 1 when ``cfg.homogeneity``.

    With ``interact=True`` the catch-up block is entered TWICE: once at its own
    level and once multiplied by lambda_t. The level coefficients d_k are then
    the pass-through of a real-wage loss in a country with no indexation at
    all, and the interaction coefficients dx_k are the extra pass-through per
    unit of indexation intensity. The test that matters is sum(dx) > 0.

    ``interact=False`` drops lambda entirely, which recovers the Bernanke &
    Blanchard (2025) wage equation (their gexp is our pistar) and is what
    ``ism.wage_validate`` checks against their Table 1.

    ``panel`` must carry columns: ``gw``, ``pistar``, ``slack``, ``catchup``,
    ``lambda`` (if interacting), and optionally ``gpty`` and ``dmw``.
    Columns that are absent are simply not included, so a country with no
    minimum wage in a given era costs nothing.
    """
    cfg = cfg or WageConfig()
    p = cfg.lags
    df = panel.copy()
    if sample:
        df = df.loc[sample[0]:sample[1]]

    blocks = [_lags(df["gw"], range(1, p + 1), "gw_l"),
              _lags(df["pistar"], range(1, p + 1), "pistar_l")]
    if "slack" in df:
        blocks.append(_lags(df["slack"], range(1, p + 1), "slack_l"))
    blocks.append(_lags(df["catchup"], range(1, p + 1), "cu_l"))
    if interact and "lambda" in df:
        blocks.append(_lags((df["lambda"] * df["catchup"]).rename("cux"),
                            range(1, p + 1), "cux_l"))
    if "gpty" in df:
        blocks.append(_lags(df["gpty"], [1], "gpty_l"))
    if "dmw" in df:
        blocks.append(_lags(df["dmw"], [0], "dmw_l"))

    X = pd.concat(blocks, axis=1)
    X.insert(0, "const", 1.0)
    y = df["gw"]
    ok = X.notna().all(axis=1) & y.notna()
    X, y = X[ok], y[ok]
    if len(y) <= X.shape[1] + 2:
        raise ValueError(f"wage equation: only {len(y)} usable observations")

    R = None
    if cfg.homogeneity:
        R = np.array([1.0 if (n.startswith("gw_l") or n.startswith("pistar_l")) else 0.0
                      for n in X.columns])
    return restricted_ols(y.to_numpy(), X.to_numpy(), list(X.columns),
                          R=R, r=1.0, index=y.index)


# ============================================================================
# Eq. (W5) - the price equation, with a fiscal-transfer term
# ============================================================================
def fit_price_equation(panel: pd.DataFrame, cfg: Optional[WageConfig] = None,
                       sample: Optional[Tuple[str, str]] = None) -> OLSFit:
    """Eq. (W5). Price inflation on its lags, wages, relative prices, transfers.

        gp_t = b0 + sum_{k=1..p} B_k gp_{t-k} + sum_{k=0..p} M_k gw_{t-k}
                  + sum_{k=0..p} E_k grpe_{t-k} + sum_{k=0..p} F_k grpf_{t-k}
                  + sum_{k=0..p} P_k h_{t-k} + Bm gpty_{t-1} + v_t

    subject to sum(B) + sum(M) = 1 when ``cfg.homogeneity``.

    Two departures from Bernanke & Blanchard's price equation, both deliberate:

    * ``h_t`` -- the **income-based** fiscal support term: cash transfers and
      one-off payments to households, as an annualised growth contribution to
      household disposable income. B&B have no fiscal block; this is the term
      through which a government's response to an energy shock feeds back into
      prices. Price-based support (tariff shields, fuel-duty cuts, the 9-Euro
      ticket) is deliberately *not* here: it does not add demand, it subtracts
      mechanically from the measured index, and it is handled as a CPI wedge in
      the effective-wage block instead.
    * relative energy and food prices are measured against **wages** (grpe =
      400 dlog(P_energy / W)), which is B&B's own convention and makes these
      real-product-wage terms rather than relative-to-CPI terms.
    """
    cfg = cfg or WageConfig()
    p = cfg.lags
    df = panel.copy()
    if sample:
        df = df.loc[sample[0]:sample[1]]

    blocks = [_lags(df["gp"], range(1, p + 1), "gp_l"),
              _lags(df["gw"], range(0, p + 1), "gw_l")]
    # The transfer term is the CYCLICALLY ADJUSTED impulse where the pipeline
    # has computed one. Total transfers are dominated by automatic stabilisers
    # -- unemployment insurance rises in recessions, when inflation is falling
    # -- so the raw series enters a price equation with a spurious negative
    # sign. The browser twin has always used h_disc; this side was reading h,
    # and the two produced different M for every country until the parity test
    # was widened to cover it.
    h_col = "h_disc" if "h_disc" in df else "h"
    for col, pref in (("grpe", "grpe_l"), ("grpf", "grpf_l"), (h_col, "h_l")):
        if col in df:
            blocks.append(_lags(df[col], range(0, p + 1), pref))
    if "gpty" in df:
        blocks.append(_lags(df["gpty"], [1], "gpty_l"))

    X = pd.concat(blocks, axis=1)
    X.insert(0, "const", 1.0)
    y = df["gp"]
    ok = X.notna().all(axis=1) & y.notna()
    X, y = X[ok], y[ok]
    if len(y) <= X.shape[1] + 2:
        raise ValueError(f"price equation: only {len(y)} usable observations")

    R = None
    if cfg.homogeneity:
        R = np.array([1.0 if (n.startswith("gp_l") or n.startswith("gw_l")) else 0.0
                      for n in X.columns])
    return restricted_ols(y.to_numpy(), X.to_numpy(), list(X.columns),
                          R=R, r=1.0, index=y.index)


# ============================================================================
# Eqs. (W6)-(W8) - the Spiral Gain
# ============================================================================
def _cumulative_response(own: np.ndarray, driver: np.ndarray,
                         horizon: int = 12, stat: str = "end") -> float:
    """Response of a scalar AR(p) process to a permanent unit step in a driver.

        y_t = sum_k own_k y_{t-k} + sum_k driver_k x_{t-k},   x_t = 1 for t >= 0

    ``stat="end"`` returns y at t = horizon-1 -- "how much of the shock has
    passed through by then"; ``stat="mean"`` returns the average over the
    horizon.

    Why a finite horizon and not the long-run multiplier sum(driver)/(1-sum(own))
    -- the object one would reach for first? Because the homogeneity restriction
    makes the long-run multiplier uninformative by construction: imposing
    sum(price lags) + sum(wage terms) = 1 in the price equation sets its
    long-run pass-through to exactly 1 whatever the data say, since it is the
    assumption that the Phillips curve is vertical. The restriction is right --
    one does not want a model in which permanently higher wage growth leaves
    prices permanently behind -- but it means the long run cannot be the place
    to look for differences between regimes. Three years can: it is the horizon
    the euro-area sectoral pass-through literature reports (Ampudia, Lombardi &
    Renault put wage-to-price at 40% after two years and 50% after three), and
    it is long enough for an indexation clause to have fired several times and
    short enough that monetary policy has not yet undone the shock.
    """
    p = len(own)
    q = len(driver)
    y: List[float] = []
    for t in range(horizon):
        val = 0.0
        for k in range(1, p + 1):
            if t - k >= 0:
                val += own[k - 1] * y[t - k]
        for k in range(q):
            if t - k >= 0:
                val += driver[k]
        y.append(val)
    return float(y[-1] if stat == "end" else np.mean(y))


def price_to_wage_gain(wage_fit: OLSFit, lam: float, p: int = 4,
                       horizon: int = 3 * PPY,
                       country: Optional[str] = None) -> float:
    """Eq. (W6). Lambda(lambda_t): the three-year cumulative response of wage
    growth to a permanent 1pp rise in *realised* inflation, at indexation
    intensity ``lam``.

    The catch-up driver is the sum of the level block and lambda times the
    interaction block, so Lambda(0) is the pass-through with no indexation and
    Lambda(1) the pass-through under universal indexation. The difference
    between them is the paper's estimate of what an indexation clause is worth.

    ``country`` selects that country's own dynamics in a partially pooled fit.
    The catch-up coefficients are common, but the persistence they propagate
    through is not, so Lambda differs across countries even at the same lambda
    -- and it should: the same impulse in a labour market with an own-lag sum of
    0.97 and one with 0.22 does not produce the same three-year response.

    A 1pp permanent rise in realised inflation moves two regressors: the
    catch-up term (by 1, scaled by lambda_t if the equation was estimated with
    the interaction) and the trend pi*, which under the local-level filter
    converges to the new inflation rate. We deliberately hold pi* fixed here
    and read only the catch-up channel, because the pi* channel is the
    *expectations* route and is common to every regime -- what distinguishes
    1975 from 2023 is the catch-up route, and that is what the gain is meant to
    isolate. The two routes are added back together in ``simulate_loop``.
    """
    c = wage_fit.for_country(country) if country else wage_fit.coef()
    own = np.array([c.get(f"gw_l{k}", 0.0) for k in range(1, p + 1)])
    drv = np.array([c.get(f"cu_l{k}", 0.0) + float(lam) * c.get(f"cux_l{k}", 0.0)
                    for k in range(1, p + 1)])
    drv = np.concatenate([[0.0], drv])  # catch-up enters with a one-quarter lag
    return _cumulative_response(own, drv, horizon)


def wage_to_price_gain(price_fit: OLSFit, p: int = 4, horizon: int = 3 * PPY) -> float:
    """Eq. (W7). M: the three-year cumulative response of price inflation to a
    permanent 1pp rise in wage growth."""
    own = np.array([price_fit.coef().get(f"gp_l{k}", 0.0) for k in range(1, p + 1)])
    drv = np.array([price_fit.coef().get(f"gw_l{k}", 0.0) for k in range(0, p + 1)])
    return _cumulative_response(own, drv, horizon)


def fiscal_gain(price_fit: OLSFit, phi_e: float, mpc: float,
                p: int = 4, horizon: int = 3 * PPY) -> float:
    """Eq. (W8b). Phi: the extra price->income->price route that runs through
    the government rather than through the wage bargain.

    A 1pp inflation surprise triggers a fiscal response of ``phi_e`` (percent
    of household disposable income, from the estimated reaction function),
    of which a fraction ``mpc`` reaches demand and thence prices through the
    price equation's transfer term.
    """
    own = np.array([price_fit.coef().get(f"gp_l{k}", 0.0) for k in range(1, p + 1)])
    drv = np.array([price_fit.coef().get(f"h_l{k}", 0.0) for k in range(0, p + 1)])
    if not np.any(drv):
        return 0.0
    return float(phi_e) * float(mpc) * _cumulative_response(own, drv, horizon)


def spiral_gain(wage_fit: OLSFit, price_fit: OLSFit, lam: pd.Series,
                p: int = 4, horizon: int = 3 * PPY,
                phi_e: float = 0.0, mpc: float = 0.0,
                country: Optional[str] = None) -> pd.DataFrame:
    """Eq. (W8). G_t = Lambda(lambda_t) * M, with the fiscal route optional.

    Returns a frame with ``lambda``, ``Lambda`` (price->wage), ``M``
    (wage->price), ``G`` and ``G_fiscal``. G > 1 is the spiral condition: one
    turn of the loop more than reproduces itself within the three-year horizon,
    so the shock is self-sustaining without any further impulse.

    Both halves are now country-specific: M comes from that country's own price
    equation, and Lambda from its own wage dynamics with the common catch-up
    coefficients. Neither varies with t, so time variation in G is entirely
    institutional -- which is the claim being tested: what changed between the
    1970s and the 2020s is who is indexed, not how firms price or how wages
    propagate.
    """
    M = wage_to_price_gain(price_fit, p=p, horizon=horizon)
    Phi = fiscal_gain(price_fit, phi_e, mpc, p=p, horizon=horizon)
    lam = lam.astype(float)
    Lam = lam.map(lambda x: price_to_wage_gain(wage_fit, x, p=p, horizon=horizon,
                                               country=country))
    out = pd.DataFrame({"lambda": lam, "Lambda": Lam})
    out["M"] = M
    out["G"] = out["Lambda"] * M
    out["G_fiscal"] = (out["Lambda"] + Phi) * M
    return out


def rolling_gain(panel: pd.DataFrame, cfg: Optional[WageConfig] = None,
                 min_obs: int = 60) -> pd.DataFrame:
    """Eq. (W8) estimated on a rolling window, so M moves too.

    The fixed-M version above isolates the institutional story; this one lets
    pricing behaviour change as well, and is the honest robustness check. Both
    are exported and the site toggles between them.
    """
    cfg = cfg or WageConfig()
    w = cfg.window or len(panel)
    rows = []
    idx = panel.index
    for i in range(len(idx)):
        if i + 1 < max(min_obs, w // 2):
            continue
        lo = max(0, i + 1 - w)
        sub = panel.iloc[lo:i + 1]
        try:
            wf = fit_wage_equation(sub, cfg)
            pf = fit_price_equation(sub, cfg)
        except (ValueError, np.linalg.LinAlgError):
            continue
        lam = float(sub["lambda"].iloc[-1]) if "lambda" in sub else 1.0
        Lam = price_to_wage_gain(wf, lam, p=cfg.lags)
        M = wage_to_price_gain(pf, p=cfg.lags)
        rows.append({"date": idx[i], "lambda": lam, "Lambda": Lam, "M": M,
                     "G": Lam * M, "nobs": wf.nobs})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def fit_panel_wage_equation(panels: Dict[str, pd.DataFrame],
                            cfg: Optional[WageConfig] = None,
                            sample: Optional[Tuple[str, str]] = None,
                            interact: bool = True,
                            free: Sequence[str] = ("gw", "pistar", "slack"),
                            ) -> OLSFit:
    """Eq. (W4') -- the panel wage equation, PARTIALLY POOLED.

    Blocks named in ``free`` get their own coefficients in every country; the
    rest are common. The default frees the dynamics -- own-lag persistence, the
    weight on trend inflation, and the slack response -- and pools only the
    catch-up level and its interaction with lambda.

    Why not free everything, and why not pool everything
    ----------------------------------------------------
    Pooling all seven countries onto one coefficient vector is not credible.
    Wage-setting in Belgium, where half the private sector is on a pivot-index
    trigger, and in the United States, where almost nobody is, are not the same
    process, and an estimator that says they are will attribute to the catch-up
    term whatever the common persistence gets wrong. ``poolability_test``
    measures how badly, and on this panel it rejects.

    Freeing everything is the opposite failure. lambda barely moves inside a
    country: it is constant in Belgium, spans 0.014 to 0.124 across sixty-five
    years in the United States, and 0.236 to 0.274 in France. A country-by-
    country catch-up interaction is identified off almost no variation and
    returns noise. The whole reason the reference countries are in the panel is
    that lambda varies ACROSS them.

    So the split follows the economics rather than convenience: the parts that
    differ by country because labour markets differ are free, and the one
    parameter the paper is about -- how much of a real-wage loss comes back,
    and how that depends on indexation -- is common, because that is the only
    place cross-country variation exists to identify it. It is a restriction,
    it is stated as one, and ``mean_group_wage_equation`` gives the fully
    heterogeneous alternative for comparison.

    A practical consequence worth noting: because each country keeps its own
    persistence, the three-year catch-up Lambda is now country-specific even
    though the catch-up coefficients are common -- the same impulse propagates
    differently through different dynamics. ``price_to_wage_gain`` therefore
    takes a country.

    Fixed effects always absorb the level of each country's wage growth. The
    long-run homogeneity restriction is imposed ONCE PER COUNTRY when the
    dynamics are free, which is what the restriction matrix in
    ``restricted_ols`` is for.
    """
    cfg = cfg or WageConfig()
    p = cfg.lags
    free = tuple(free or ())
    codes = sorted(panels)

    def blocks_for(df: pd.DataFrame) -> List[Tuple[str, pd.Series, range]]:
        out = [("gw_l", df["gw"], range(1, p + 1)),
               ("pistar_l", df["pistar"], range(1, p + 1)),
               ("cu_l", df["catchup"], range(1, p + 1))]
        if "slack" in df:
            out.append(("slack_l", df["slack"], range(1, p + 1)))
        if interact and "lambda" in df:
            out.append(("cux_l", (df["lambda"] * df["catchup"]).rename("cux"),
                        range(1, p + 1)))
        return out

    # Column layout: common columns first, then one set per country for each
    # free block, then the fixed effects. Built once from the first country so
    # every panel writes into the same positions.
    frames, ys = [], []
    for code in codes:
        df = panels[code].loc[sample[0]:sample[1]] if sample else panels[code]
        parts = []
        for prefix, series, lags in blocks_for(df):
            block = _lags(series, lags, prefix)
            stem = prefix.split("_l")[0]
            if stem in free:
                block = block.rename(columns=lambda n, c=code: f"{n}__{c}")
            parts.append(block)
        X = pd.concat(parts, axis=1)
        X["_country"] = code
        frames.append(X)
        ys.append(df["gw"].rename("y"))

    X = pd.concat(frames)
    y = pd.concat(ys)
    for c in codes:
        X[f"fe_{c}"] = (X["_country"] == c).astype(float)
    X = X.drop(columns=["_country"])
    # A country's own columns are NaN on every other country's rows; that is
    # structural, not missing data, so fill before dropping incomplete rows.
    for col in X.columns:
        if "__" in col:
            owner = col.rsplit("__", 1)[1]
            X[col] = X[col].where(X[f"fe_{owner}"] == 1.0, 0.0)
    ok = X.notna().all(axis=1) & y.notna()
    X, y = X[ok], y[ok]
    if len(y) <= X.shape[1] + 2:
        raise ValueError(f"panel wage equation: {len(y)} rows for {X.shape[1]} regressors")

    R = None
    rvals = 0.0
    if cfg.homogeneity:
        cols = list(X.columns)
        is_dyn = lambda n: n.startswith("gw_l") or n.startswith("pistar_l")  # noqa: E731
        if "gw" in free or "pistar" in free:
            # one restriction per country
            R = np.zeros((len(cols), len(codes)))
            for j, c in enumerate(codes):
                for i, n in enumerate(cols):
                    base = n.rsplit("__", 1)[0] if "__" in n else n
                    owner = n.rsplit("__", 1)[1] if "__" in n else None
                    if is_dyn(base) and (owner is None or owner == c):
                        R[i, j] = 1.0
            rvals = np.ones(len(codes))
        else:
            R = np.array([1.0 if is_dyn(n) else 0.0 for n in cols])
            rvals = 1.0
    return restricted_ols(y.to_numpy(), X.to_numpy(), list(X.columns),
                          R=R, r=rvals, index=y.index)


def poolability_test(panels: Dict[str, pd.DataFrame],
                     cfg: Optional[WageConfig] = None,
                     sample: Optional[Tuple[str, str]] = None) -> Dict[str, float]:
    """Is one coefficient vector for seven countries defensible? (It is not.)

    A Chow-style F-test of the fully pooled wage equation against the fully
    heterogeneous one, both with country fixed effects:

        F = [(SSR_pooled - SSR_free) / q] / [SSR_free / (n - k_free)]

    Reported rather than acted on mechanically: a rejection says the pooled
    slopes are wrong, not that every slope must be freed. The paper's
    specification frees the dynamics, which is what this test rejects pooling
    on, and keeps the catch-up block common, which is what identification
    requires.
    """
    pooled = fit_panel_wage_equation(panels, cfg, sample, free=())
    freed = fit_panel_wage_equation(panels, cfg, sample,
                                    free=("gw", "pistar", "slack", "cu", "cux"))
    ssr_r = float(pooled.resid @ pooled.resid)
    ssr_u = float(freed.resid @ freed.resid)
    k_u = len(freed.names)
    q = k_u - len(pooled.names)
    n = freed.nobs
    if q <= 0 or n - k_u <= 0:
        return {"F": float("nan"), "df1": q, "df2": n - k_u, "p": float("nan")}
    F = ((ssr_r - ssr_u) / q) / (ssr_u / (n - k_u))
    p = float("nan")
    try:
        from scipy import stats
        p = float(stats.f.sf(F, q, n - k_u))
    except Exception:  # noqa: BLE001 - scipy is optional
        pass
    return {"F": float(F), "df1": float(q), "df2": float(n - k_u), "p": p,
            "ssr_pooled": ssr_r, "ssr_free": ssr_u,
            "r2_pooled": float(pooled.r2), "r2_free": float(freed.r2)}


def mean_group_wage_equation(panels: Dict[str, pd.DataFrame],
                             cfg: Optional[WageConfig] = None,
                             interact: bool = False) -> pd.DataFrame:
    """Pesaran-Smith mean-group estimates: fit each country, then average.

    Consistent under full slope heterogeneity, which is exactly what the
    poolability test says we have, and the natural robustness check on a
    partially pooled specification. The standard error is the cross-country
    standard deviation of the coefficient divided by sqrt(N) -- it measures
    disagreement between countries, not sampling error within them, and with
    N = 7 it is indicative at best.

    The interaction is off by default: within a country lambda is close to
    constant, so a country-level interaction is not identified and averaging
    seven noisy numbers does not fix that.
    """
    cfg = cfg or WageConfig()
    rows = {}
    for c, d in panels.items():
        try:
            rows[c] = fit_wage_equation(d, cfg, interact=interact).coef()
        except (ValueError, np.linalg.LinAlgError):
            continue
    if not rows:
        return pd.DataFrame()
    M = pd.DataFrame(rows).T
    N = len(M)
    return pd.DataFrame({
        "mean_group": M.mean(),
        "se": M.std(ddof=1) / np.sqrt(N),
        "n_countries": N,
        "min": M.min(),
        "max": M.max(),
    })


# ============================================================================
# Eq. (W9) - the fiscal reaction function
# ============================================================================
def fit_fiscal_rule(panel: pd.DataFrame, country_col: str = "country") -> OLSFit:
    """Eq. (W9). How hard does a government hand out money when prices jump?

        h_t = rho h_{t-1} + phi_e energyshock_t + phi_pi (pi_t - pi*_t)
                          + phi_x slack_t + phi_P populist_t + country FE + e_t

    Estimated on the pooled country panel with country fixed effects. ``h`` is
    the annualised growth contribution of government cash transfers to
    household disposable income; ``populist`` is the curated indicator from
    ``config/wage_politics.csv``.

    phi_P is the coefficient the paper's policy discussion turns on: it is the
    extra transfer response associated with a populist executive or an imminent
    election, over and above the response to the shock itself.
    """
    df = panel.dropna(subset=["h"]).copy()
    cols = ["h_l1", "energyshock", "pigap", "slack", "populist"]
    X = pd.DataFrame(index=df.index)
    X["h_l1"] = df.groupby(country_col)["h"].shift(1) if country_col in df else df["h"].shift(1)
    for c in ("energyshock", "pigap", "slack", "populist"):
        if c in df:
            X[c] = df[c]
    if country_col in df:
        for c in sorted(df[country_col].unique())[1:]:
            X[f"fe_{c}"] = (df[country_col] == c).astype(float)
    X.insert(0, "const", 1.0)
    y = df["h"]
    ok = X.notna().all(axis=1) & y.notna()
    X, y = X[ok], y[ok]
    return restricted_ols(y.to_numpy(), X.to_numpy(), list(X.columns), index=y.index)


# ============================================================================
# Eqs. (W10)-(W11) - the Effective Wage Index
# ============================================================================
def effective_wage_index(components: pd.DataFrame, shares: Dict[str, float],
                         handout_col: str = "handout") -> pd.Series:
    """Eq. (W10). A share-weighted index of everything that pays a household.

        EWI_t = sum_{c != handout} s_c X_{c,t}  +  (X_handout,t - 100)

    ``components`` carries one index column per income source -- ``wage``
    (market earnings), ``minwage`` (the statutory floor), ``benefit`` (indexed
    social benefits and pensions) -- each normalised to 100 in the base period,
    plus ``handout``.

    Handouts enter ADDITIVELY, not as a weighted component, and the distinction
    is not pedantic. A recurring income source is properly weighted by its share
    of income: the market wage is 42% of the bottom quartile's income in the
    United States, so a 10% raise is worth 4.2 index points. A one-off payment
    has no share -- it is a flow that exists in one year and not the next. Its
    component index is one plus the payment as a fraction of disposable income,
    so ``X_handout - 100`` is already the payment measured in index points and
    weighting it again by a "handout share" would shrink a EUR 300
    Energiepreispauschale to a rounding error. Written this way, Germany's 2022
    package moves the index by what it was actually worth to a household.

    The point of the index is that its four parts move for different reasons:
    the market wage follows the bargain, the floor follows a statutory formula,
    benefits follow an uprating rule with a lag, and handouts follow politics.
    An aggregate wage series shows only the first.
    """
    weighted = {k: v for k, v in shares.items()
                if k != handout_col and k in components.columns}
    tot = sum(weighted.values())
    if tot <= 0:
        raise ValueError("shares must sum to a positive number")
    # A missing component is missing, not zero. Filling it with zero would
    # silently report an index for a quarter in which one of its parts does not
    # exist -- and since the components are levels around 100, a zero is not a
    # neutral filler but a 100-point hole. The browser twin drops such rows, so
    # this must too or the parity test is meaningless.
    out = None
    for col, sh in weighted.items():
        part = components[col].astype(float) * (sh / tot)
        out = part if out is None else out + part
    if out is None:
        raise ValueError("no component columns matched the share keys")
    if handout_col in components.columns:
        h = components[handout_col].astype(float).fillna(100.0)
        out = out + (h - 100.0)
    return out.rename("ewi")


def real_effective_wage(ewi: pd.Series, cpi: pd.Series,
                        subsidy_wedge: Optional[pd.Series] = None,
                        base: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Eq. (W11). Real EWI, measured and subsidy-neutral, indexed to 100 at ``base``.

    Two deflators, because there are two questions:

    * **measured real** = EWI / CPI. What a statistician sees. Price-based
      support -- a tariff shield, a fuel-duty cut, a EUR 9 rail pass -- has
      already lowered the CPI, so this treats the subsidy as a price effect and
      credits the household with it.
    * **subsidy-neutral real** = EWI / CPI~, where CPI~ is the index that would
      have been recorded without those measures, reconstructed by cumulating
      ``subsidy_wedge`` -- the estimated contribution of the price measures to
      year-on-year inflation, negative while a shield is in force and positive
      as it unwinds.

    The gap between the two is the part of measured real income that is a
    consequence of *how* the support was delivered rather than of what
    households received. For France in 2022 it is worth about 2.6 percentage
    points of inflation; for Germany's summer-2022 fuel-and-transport package
    about one.

    A government choosing between a price cap and a cash transfer of equal cost
    is therefore also choosing how much measured inflation to record, and by
    implication how much every price-indexed contract in the economy will pay
    out. That is a policy lever hiding inside a statistical convention, and the
    wedge is what makes it visible.
    """
    ewi = ewi.dropna()
    cpi = cpi.reindex(ewi.index).astype(float)
    base = base if base is not None else ewi.index[0]
    if base not in ewi.index:
        base = ewi.index[0]
    out = pd.DataFrame({"nominal": ewi})
    real = ewi / cpi
    out["real"] = 100.0 * real / float(real.loc[base])
    if subsidy_wedge is not None:
        w = subsidy_wedge.reindex(ewi.index).fillna(0.0).to_numpy() / 100.0 / PPY
        cpi_star = cpi * np.exp(-np.cumsum(w))
        rsn = ewi / cpi_star
        out["real_subsidy_neutral"] = 100.0 * rsn / float(rsn.loc[base])
        out["wedge"] = out["real_subsidy_neutral"] - out["real"]
    return out


# ============================================================================
# Eq. (W12) - the loop simulator
# ============================================================================
@dataclass
class SimParams:
    """Knobs of the counterfactual simulator (the site's sliders)."""

    lam: float = 0.10            # indexation intensity
    anchor_q: float = 0.05       # expectations anchoring
    phi_e: float = 0.0           # fiscal response, % of hh income per 1pp of shock
    mpc: float = 0.30            # share of transfers reaching demand
    taylor: float = 0.5          # monetary response: pp of slack per pp of inflation
    shock: float = 10.0          # size of the relative energy price shock, pp
    shock_len: int = 4           # quarters the shock is sustained
    horizon: int = 24            # quarters simulated


def simulate_loop(wage_fit: OLSFit, price_fit: OLSFit,
                  params: Optional[SimParams] = None,
                  p: int = 4, country: Optional[str] = None) -> pd.DataFrame:
    """Eq. (W12). Propagate an energy shock through prices, wages, the fiscal
    response and expectations.

    The system simulated is the estimated one, in deviations from steady state:

        gp_t  = sum B_k gp_{t-k} + sum M_k gw_{t-k} + sum E_k grpe_{t-k}
                + sum P_k h_{t-k}
        gw_t  = sum a_k gw_{t-k} + sum b_k pistar_{t-k} + sum c_k slack_{t-k}
                + sum (d_k + lam * dx_k) catchup_{t-k}
        pistar_t = pistar_{t-1} + k(q) (gp_t - pistar_{t-1})
        rw_t     = rw_{t-1} + (gw_t - gp_t) / 4
        catchup_t = -rw_t
        h_t   = phi_e * max(gp_t - pistar_t, 0) * mpc     (the handout rule)
        slack_t = -taylor * (gp_t - pistar_t)             (the policy rule)

    The monetary rule is written as a direct slack response rather than a rate
    rule: the estimated wage equation takes slack, not the policy rate, so a
    Taylor rule would need an IS curve we have not estimated, and pretending
    otherwise would add a free parameter without adding information. ``taylor``
    is therefore "percentage points of slack opened per percentage point of
    inflation above trend" -- a reduced-form sacrifice-rate dial.

    Returns a frame of the simulated paths, in annualised percentage points
    relative to the no-shock baseline.
    """
    pr = params or SimParams()
    wc = wage_fit.for_country(country) if country else wage_fit.coef()
    pc = price_fit.coef()
    a = [wc.get(f"gw_l{k}", 0.0) for k in range(1, p + 1)]
    b = [wc.get(f"pistar_l{k}", 0.0) for k in range(1, p + 1)]
    c = [wc.get(f"slack_l{k}", 0.0) for k in range(1, p + 1)]
    d = [wc.get(f"cu_l{k}", 0.0) + pr.lam * wc.get(f"cux_l{k}", 0.0)
         for k in range(1, p + 1)]
    B = [pc.get(f"gp_l{k}", 0.0) for k in range(1, p + 1)]
    M = [pc.get(f"gw_l{k}", 0.0) for k in range(0, p + 1)]
    E = [pc.get(f"grpe_l{k}", 0.0) for k in range(0, p + 1)]
    P = [pc.get(f"h_l{k}", 0.0) for k in range(0, p + 1)]
    kgain = kalman_gain(pr.anchor_q)

    H = pr.horizon
    gp = np.zeros(H); gw = np.zeros(H); pis = np.zeros(H)
    cu = np.zeros(H); h = np.zeros(H); sl = np.zeros(H); rw = np.zeros(H)
    grpe = np.array([pr.shock if t < pr.shock_len else 0.0 for t in range(H)])

    def lagsum(coefs, arr, t, start):
        return sum(coefs[i] * arr[t - (i + start)]
                   for i in range(len(coefs)) if t - (i + start) >= 0)

    for t in range(H):
        gw[t] = (lagsum(a, gw, t, 1) + lagsum(b, pis, t, 1)
                 + lagsum(c, sl, t, 1) + lagsum(d, cu, t, 1))
        gp[t] = (lagsum(B, gp, t, 1) + lagsum(M, gw, t, 0)
                 + lagsum(E, grpe, t, 0) + lagsum(P, h, t, 0))
        prev = pis[t - 1] if t > 0 else 0.0
        pis[t] = prev + kgain * (gp[t] - prev)
        # The catch-up regressor must be the SAME OBJECT the coefficients were
        # estimated on -- the deviation of the log real wage from its trend, in
        # percent -- not the Bernanke & Blanchard inflation surprise. An earlier
        # version of this function used the surprise, which fed coefficients
        # estimated on a level gap a regressor measured in inflation
        # differences: different units, different scale, and every simulated
        # path wrong. In a deviation-from-baseline simulation the trend real
        # wage is the baseline, so the gap is just the cumulated real wage
        # shortfall; gw and gp are four-quarter rates, so one quarter adds a
        # quarter of the annual rate.
        rw[t] = (rw[t - 1] if t > 0 else 0.0) + (gw[t] - gp[t]) / PPY
        cu[t] = -rw[t]
        gap = gp[t] - pis[t]
        h[t] = pr.phi_e * max(gap, 0.0) * pr.mpc
        sl[t] = -pr.taylor * gap

    return pd.DataFrame({
        "quarter": np.arange(H),
        "energy": grpe,
        "price_inflation": gp,
        "wage_growth": gw,
        "trend": pis,
        "catchup": cu,
        "handout": h,
        "slack": sl,
        "real_wage": gw - gp,
        "real_wage_level": rw,
    })
