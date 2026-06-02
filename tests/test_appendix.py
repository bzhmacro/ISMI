"""Synthetic tests for ism.appendix (no network)."""
import os, sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ism.engine import ISMConfig, residual_panel  # noqa: E402
from ism import appendix as ap  # noqa: E402


def test_run_probability():
    # alpha=0 -> p=0.5 ; P(>=3 positive)=0.5*0.5^2=0.125 ; either-sign = 0.25
    assert ap.run_probability(0.0, 3) == pytest.approx(0.125)
    assert ap.run_probability(0.0, 3, same_sign_either=True) == pytest.approx(0.25)
    # increasing in alpha
    vals = ap.run_probability(np.array([-0.5, 0.0, 0.5, 0.9]), 3)
    assert np.all(np.diff(vals) > 0)


def test_rolling_rho_alpha_white_residuals():
    # pi_t = 0.5 pi_{t-1} + white  -> rho_hat ~ 0.5, alpha_hat ~ 0
    rng = np.random.default_rng(0)
    n = 400
    y = np.zeros(n)
    for t in range(1, n):
        y[t] = 0.5 * y[t - 1] + rng.normal(0, 1)
    s = pd.Series(y, index=pd.date_range("1980-01-01", periods=n, freq="MS"))
    out = ap.rolling_rho_alpha(s, window=120).dropna()
    assert out["rho_hat"].mean() == pytest.approx(0.5, abs=0.1)
    assert abs(out["alpha_hat"].mean()) < 0.12


def test_aggregate_ism_ternary():
    rng = np.random.default_rng(1)
    n = 200
    s = pd.Series(rng.normal(0.2, 0.4, n), index=pd.date_range("1990-01-01", periods=n, freq="MS"))
    out = ap.aggregate_ism(s, ISMConfig(window=120, run_length=3))
    vals = set(np.unique(out["ISM_agg"].dropna()))
    assert vals.issubset({-1.0, 0.0, 1.0})


def test_consecutive_run_shares_decreasing():
    rng = np.random.default_rng(2)
    m = pd.date_range("1970-01-01", periods=300, freq="MS")
    resid = pd.DataFrame(rng.normal(0, 1, size=(300, 20)), index=m,
                         columns=[f"c{i}" for i in range(20)])
    sh = ap.consecutive_run_shares(resid, kmax=4)
    assert (sh["positive_share"].diff().dropna() <= 1e-9).all()  # non-increasing in k
    assert sh.loc[sh["k"] == 1, "positive_share"].iloc[0] > 0.3   # ~half are positive


def test_compute_ism_weighted_runs():
    rng = np.random.default_rng(3)
    m = pd.date_range("1990-01-01", periods=180, freq="MS")
    cats = [f"c{i}" for i in range(30)]
    infl = pd.DataFrame(rng.normal(0.2, 0.4, size=(180, 30)), index=m, columns=cats)
    w = pd.DataFrame(1.0, index=m, columns=cats)
    for scheme in ("size", "stickiness"):
        out = ap.compute_ism_weighted(infl, w, ISMConfig(window=120), scheme=scheme)
        assert {"ISM", "S_pos", "S_neg"}.issubset(out.columns)
        assert np.allclose((out["S_pos"] - out["S_neg"]).dropna(), out["ISM"].dropna())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
