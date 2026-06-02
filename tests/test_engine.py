"""
Synthetic + identity tests for ism.engine.

These tests need NO network or real data. They verify that the code is a
faithful translation of Eqs. (3)-(8):

1. test_momentum_run_logic
   A hand-built residual panel with a known run of +/- residuals must produce
   exactly the M+/M- pattern implied by Eqs. (4)-(5).

2. test_shares_and_index
   With known weights, S+ / S- / ISM must equal the hand-computed values
   (Eqs. 6-8).

3. test_ar1_recovers_known_residual_sign
   On data generated from a known AR(1), the rolling residual at the window end
   must have the expected sign.

4. test_identity_against_author_file (skipped if file absent)
   The author's published ISM_public.xlsx must satisfy ISM == S+ - S- to
   floating tolerance, confirming our reading of Eq. (8) matches theirs.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ism.engine import (  # noqa: E402
    ISMConfig,
    compute_ism,
    expenditure_weighted_shares,
    momentum_signals,
    rolling_ar_residuals,
)

MONTHS = pd.period_range("2000-01", periods=12, freq="M").to_timestamp()


def test_momentum_run_logic():
    # category A: residuals +,+,+,... ; category B: -,-,-,...
    cfg = ISMConfig(run_length=3)
    resid = pd.DataFrame(
        {
            "A": [1, 1, 1, -1, 1, 1, 1, 1, -1, -1, 1, 1],
            "B": [-1, -1, -1, -1, -1, 1, -1, -1, -1, -1, -1, -1],
        },
        index=MONTHS,
        dtype=float,
    )
    m_pos, m_neg = momentum_signals(resid, cfg)

    # A: first positive run of length 3 completes at index 2 (0-based).
    assert m_pos["A"].tolist() == [0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0]
    assert m_neg["A"].sum() == 0  # A never has 3 consecutive negatives
    # B: negative run completes at index 2, broken at 5, resumes at 8.
    assert m_neg["B"].tolist() == [0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1]
    assert m_pos["B"].sum() == 0


def test_shares_and_index():
    cfg = ISMConfig(run_length=3)
    resid = pd.DataFrame(
        {"A": [1, 1, 1], "B": [-1, -1, -1]}, index=MONTHS[:3], dtype=float
    )
    weights = pd.DataFrame(
        {"A": [0.7, 0.7, 0.7], "B": [0.3, 0.3, 0.3]}, index=MONTHS[:3]
    )
    m_pos, m_neg = momentum_signals(resid, cfg)
    s_pos, s_neg = expenditure_weighted_shares(m_pos, m_neg, weights)

    # At month index 2 both runs complete: A positive (w=0.7), B negative (w=0.3)
    assert s_pos.iloc[2] == pytest.approx(0.7)
    assert s_neg.iloc[2] == pytest.approx(0.3)
    assert (s_pos - s_neg).iloc[2] == pytest.approx(0.4)  # Eq. (8)


def test_ar1_recovers_known_residual_sign():
    # Build inflation from a known AR(1) with a big positive shock at the end.
    rng = np.random.default_rng(0)
    n = 130
    mu, rho = 0.2, 0.5
    y = np.zeros(n)
    eps = rng.normal(0, 0.1, n)
    for t in range(1, n):
        y[t] = mu + rho * y[t - 1] + eps[t]
    y[-1] += 5.0  # large positive shock at the final month
    s = pd.Series(y, index=pd.period_range("1990-01", periods=n, freq="M").to_timestamp())

    cfg = ISMConfig(ar_order=1, window=120)
    resid = rolling_ar_residuals(s, cfg)
    # The injected shock should make the last window-end residual strongly +.
    assert resid.iloc[-1] > 1.0


def test_identity_against_author_file():
    here = os.path.dirname(__file__)
    path = os.path.join(here, "..", "data", "raw", "ISM_public_author.xlsx")
    if not os.path.exists(path):
        pytest.skip("author file not present")
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    diff = df["ISM Index"] - (
        df["Positive Momentum Component"] - df["Negative Momentum Component"]
    )
    # Author file is published rounded to 3 decimals, so the identity holds to
    # ~1e-3 rather than machine precision. This still confirms ISM = S+ - S-.
    assert diff.abs().max() < 2e-3  # confirms our reading of Eq. (8)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
