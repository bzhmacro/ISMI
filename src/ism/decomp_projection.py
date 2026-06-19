"""
ism.decomp_projection
=====================

Section 4 of Shapiro (2022-18): local projections (Jordà 2005) of the supply-
and demand-driven inflation contributions onto externally identified shocks
(Eq. 21), plus the recession-dynamics LP of Figure 4.

Both reuse the generic `jorda_lp` from ism.local_projection (the same engine the
momentum-paper exhibits use), so the econometrics live in one place.

Eq. (21): for each horizon h, the cumulative growth of contribution j ∈ {dem, sup}
between t-1 and t+h is regressed on the HFI monetary shock, the oil-supply shock,
and controls Y (current + 6 lags of both contributions, unemployment, the excess
bond premium and a credit spread):

    π^j_{t+h,t-1} = α^h_j HFI_t + β^h_j OS_t + A^h_j Σ_{τ=0..6} Y_{t-τ} + ζ_{j,t+h}

We read α^h (the response to the monetary shock) and β^h (the response to the
oil-supply shock) as two separate one-shock projections (each controlling for the
other shock and Y), matching the paper's reported impulse responses to core and
headline contributions over 24 months.

Figure 4: cumulative response of a contribution following NBER recession peaks,
controlling for 12 lags of the contribution and 12 lags + intervening recession
-peak dummies.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from .local_projection import jorda_lp


def _yoy_running(monthly: pd.Series) -> pd.Series:
    """12-month running product of a monthly contribution (pp)."""
    g = 1.0 + monthly / 100.0
    return 100.0 * (g.rolling(12, min_periods=12).apply(np.prod, raw=True) - 1.0)


def irf_contribution_to_shock(
    contribution: pd.Series,
    shock: pd.Series,
    other_shock: Optional[pd.Series] = None,
    controls: Optional[pd.DataFrame] = None,
    other_contribution: Optional[pd.Series] = None,
    horizons: Sequence[int] = range(0, 25),
    control_lags: int = 6,
    scale_by_sd: bool = True,
) -> pd.DataFrame:
    """Eq. (21): cumulative IRF of a contribution to one shock over `horizons`.

    Parameters
    ----------
    contribution:
        Monthly supply- or demand-driven contribution π^j_t (pp), from
        `ism.decomp_engine.contributions`.
    shock:
        The impulse (HFI monetary or oil-supply). Its coefficient is the IRF.
    other_shock:
        The other shock, included contemporaneously as a control (so each IRF
        partials out the other), per the paper's single regression.
    controls:
        Y_t columns (unemployment, EBP, credit spread); each enters at lags
        0..control_lags.
    other_contribution:
        The complementary contribution (the paper controls for current+6 lags of
        BOTH contributions); enters at lags 0..control_lags.
    scale_by_sd:
        Scale the IRF to a one-standard-deviation shock (True) or raw units.

    Returns the LP result frame (h, beta, se, bands).
    """
    target = contribution.rename("contrib")
    extra = {}
    if other_shock is not None:
        extra["othershock"] = (other_shock, [0])
    # current + 6 lags of both contributions
    extra["ownc"] = (contribution, range(0, control_lags + 1))
    if other_contribution is not None:
        extra["otherc"] = (other_contribution, range(0, control_lags + 1))
    if controls is not None:
        for col in controls.columns:
            extra[col] = (controls[col], range(0, control_lags + 1))
    return jorda_lp(target, shock.rename("shock"), horizons, extra,
                    scale_by_sd=scale_by_sd).to_frame()


def recession_response(
    contribution: pd.Series,
    recession_peak: pd.Series,
    horizons: Sequence[int] = range(0, 37),
    contrib_lags: int = 12,
    rec_lags: int = 12,
) -> pd.DataFrame:
    """Figure 4: cumulative response of a contribution after a recession peak.

    Regresses the cumulative change in `contribution` from t-1 to t+h on the
    recession-peak dummy, controlling for 12 lags of the contribution and
    12 lags + the contemporaneous recession-peak dummy.
    """
    extra = {
        "clag": (contribution, range(1, contrib_lags + 1)),
        "rec": (recession_peak, range(1, rec_lags + 1)),
    }
    return jorda_lp(contribution.rename("target"), recession_peak.rename("shock"),
                    horizons, extra, scale_by_sd=False).to_frame()


def run_section4(
    contrib: pd.DataFrame,
    monetary_shock: Optional[pd.Series] = None,
    oil_shock: Optional[pd.Series] = None,
    controls: Optional[pd.DataFrame] = None,
    recession_peak: Optional[pd.Series] = None,
    horizons_irf: Sequence[int] = range(0, 25),
    horizons_rec: Sequence[int] = range(0, 37),
) -> dict:
    """Convenience: run all available Section-4 projections.

    `contrib` must have columns "supply" and "demand" (monthly, pp). Returns a
    dict of LP result frames keyed by exercise, skipping any whose shock series
    is unavailable.
    """
    sup, dem = contrib["supply"], contrib["demand"]
    out: dict = {}
    if monetary_shock is not None:
        out["monetary->demand"] = irf_contribution_to_shock(
            dem, monetary_shock, other_shock=oil_shock, controls=controls,
            other_contribution=sup, horizons=horizons_irf)
        out["monetary->supply"] = irf_contribution_to_shock(
            sup, monetary_shock, other_shock=oil_shock, controls=controls,
            other_contribution=dem, horizons=horizons_irf)
    if oil_shock is not None:
        out["oil->demand"] = irf_contribution_to_shock(
            dem, oil_shock, other_shock=monetary_shock, controls=controls,
            other_contribution=sup, horizons=horizons_irf)
        out["oil->supply"] = irf_contribution_to_shock(
            sup, oil_shock, other_shock=monetary_shock, controls=controls,
            other_contribution=dem, horizons=horizons_irf)
    if recession_peak is not None:
        out["recession->demand"] = recession_response(dem, recession_peak, horizons_rec)
        out["recession->supply"] = recession_response(sup, recession_peak, horizons_rec)
    return out
