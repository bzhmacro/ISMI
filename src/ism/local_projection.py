"""
ism.local_projection
=====================

Jorda (2005) local projections for the paper's two LP exercises.

Figure 2 / Eq. (9): cumulative response of the log PCE price level to an ISM
(or S+, S-) surprise:

    ln(p_{t+h}) - ln(p_{t-1}) = c + b_h * ISM_t
                                  + sum_{i=1}^{12} ISM_{t-i}
                                  + sum_{i=0}^{12} X_{t-i} + e_{t+h}

The coefficient b_h on the contemporaneous ISM is the impulse response at horizon
h. By Frisch-Waugh this equals the response to the part of ISM_t orthogonal to
its 12 lags and to current+12 lags of the controls X -- i.e. the paper's "ISM
surprise". We estimate Eq. (9) directly and read b_h, with Newey-West (HAC) SEs.

Figure 3 / Eq. (15): response of the ISM index to an external shock:

    ISM_{t+h} - ISM_{t-1} = c + b_h * shock_t
                              + sum_{i=1}^{12} ISM_{t-i}
                              + sum_{i=1}^{12} Recession_{t-i} + e_{t+h}

where shock_t is the Romer-Romer attempted-disinflation dummy or the Kanzig
oil-supply news shock.

Both are special cases of `jorda_lp` below. Responses can be scaled to a
one-standard-deviation shock (for continuous shocks like ISM or Kanzig) or left
in raw units (for a 0/1 event dummy like Romer-Romer).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import statsmodels.api as sm
except ImportError:
    sm = None


def _lag_block(series: pd.Series, lags: Sequence[int], prefix: str) -> pd.DataFrame:
    """DataFrame of selected lags of a series (lag 0 = contemporaneous)."""
    return pd.DataFrame({f"{prefix}_l{L}": series.shift(L) for L in lags})


@dataclass
class LPResult:
    horizons: np.ndarray
    beta: np.ndarray          # impulse response at each horizon
    se: np.ndarray            # HAC standard error
    nobs: np.ndarray

    def to_frame(self) -> pd.DataFrame:
        z90 = 1.645
        return pd.DataFrame({
            "h": self.horizons, "beta": self.beta, "se": self.se,
            "lo_1sd": self.beta - self.se, "hi_1sd": self.beta + self.se,
            "lo_90": self.beta - z90 * self.se, "hi_90": self.beta + z90 * self.se,
            "nobs": self.nobs,
        })


def jorda_lp(
    target: pd.Series,
    shock: pd.Series,
    horizons: Sequence[int],
    extra_regressors: Optional[Dict[str, Tuple[pd.Series, Sequence[int]]]] = None,
    scale_by_sd: bool = True,
    hac_maxlags=None,
) -> LPResult:
    """Generic Jorda local projection.

    For each horizon h, regress  (target_{t+h} - target_{t-1})  on a constant,
    the contemporaneous `shock`, and the `extra_regressors` (each given as
    (series, lags)). Returns the sequence of coefficients on `shock` (the impulse
    response) with Newey-West HAC standard errors (maxlags defaults to h + 1).

    Parameters
    ----------
    target : the level/index whose cumulative change is the dependent variable
             (e.g. 100*ln(PCEPI) for Eq. 9, or the ISM index for Eq. 15).
    shock  : the impulse variable; its contemporaneous coefficient is the IRF.
    extra_regressors : {name: (series, [lags])} added to the RHS (e.g. ISM lags,
             control lags, recession lags).
    scale_by_sd : if True, multiply beta and se by sd(shock) so the IRF is the
             response to a one-standard-deviation shock (use for continuous
             shocks; set False for a 0/1 event dummy).
    """
    if sm is None:
        raise RuntimeError("statsmodels is required: pip install statsmodels")

    extra_regressors = extra_regressors or {}
    sd = float(shock.std(ddof=0)) if scale_by_sd else 1.0

    betas, ses, nobs = [], [], []
    for h in horizons:
        y = (target.shift(-h) - target.shift(1)).rename("y")
        X = pd.DataFrame({"shock": shock})
        for name, (series, lags) in extra_regressors.items():
            X = pd.concat([X, _lag_block(series, lags, name)], axis=1)
        data = pd.concat([y, X], axis=1).dropna()
        Xc = sm.add_constant(data[X.columns])
        L = (h + 1) if hac_maxlags is None else hac_maxlags
        m = sm.OLS(data["y"], Xc).fit(cov_type="HAC", cov_kwds={"maxlags": L})
        betas.append(m.params["shock"] * sd)
        ses.append(m.bse["shock"] * sd)
        nobs.append(int(m.nobs))
    return LPResult(np.asarray(horizons), np.asarray(betas), np.asarray(ses), np.asarray(nobs))


# ---------------------------------------------------------------------------
# Eq. (9): IRF of the log PCE price level to an ISM / S+ / S- surprise
# ---------------------------------------------------------------------------
def irf_price_to_ism(
    pce_price_index: pd.Series,
    ism: pd.Series,
    controls: pd.DataFrame,
    horizons: Sequence[int] = range(0, 61),
    ism_lags: int = 12,
    control_lags: int = 12,
) -> pd.DataFrame:
    """Figure 2: cumulative log-PCE-price response (in pp) to a 1 sd ISM surprise.

    `pce_price_index` is the aggregate PCE price level (e.g. PCEPI). We use
    target = 100*ln(price) so the response is in percentage points. ISM lags 1..L
    and controls 0..L are partialled out (the Frisch-Waugh "surprise").
    """
    target = (100.0 * np.log(pce_price_index)).rename("lnP")
    extra = {"ismlag": (ism, range(1, ism_lags + 1))}
    for col in controls.columns:
        extra[col] = (controls[col], range(0, control_lags + 1))
    res = jorda_lp(target, ism.rename("shock"), horizons, extra, scale_by_sd=True)
    return res.to_frame()


# ---------------------------------------------------------------------------
# Eq. (15): response of the ISM index to an external shock
# ---------------------------------------------------------------------------
def response_ism_to_shock(
    ism: pd.Series,
    shock: pd.Series,
    recession: pd.Series,
    horizons: Sequence[int] = range(0, 37),
    ism_lags: int = 12,
    recession_lags: int = 12,
    scale_by_sd: bool = True,
) -> pd.DataFrame:
    """Figure 3: response of ISM to a shock (Romer-Romer dummy or Kanzig oil news).

    Set scale_by_sd=False for the Romer-Romer 0/1 event dummy (response to the
    event), True for the continuous Kanzig shock (response to a 1 sd move).
    """
    extra = {
        "ismlag": (ism, range(1, ism_lags + 1)),
        "rec": (recession, range(1, recession_lags + 1)),
    }
    res = jorda_lp(ism.rename("target"), shock.rename("shock"), horizons, extra,
                   scale_by_sd=scale_by_sd)
    return res.to_frame()
