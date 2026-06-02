"""Synthetic tests for ism.local_projection (no network)."""
import os, sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ism.local_projection import jorda_lp, irf_price_to_ism, response_ism_to_shock  # noqa: E402


def test_jorda_recovers_known_irf():
    """If d(level)_t = 0.5*shock_t (+noise), the cumulative response to a unit
    shock is 0.5 at every horizon, because future shocks are orthogonal."""
    rng = np.random.default_rng(0)
    n = 600
    idx = pd.date_range("1970-01-01", periods=n, freq="MS")
    shock = pd.Series(rng.normal(0, 1, n), index=idx, name="shock")
    dlevel = 0.5 * shock + rng.normal(0, 0.05, n)
    level = pd.Series(np.cumsum(dlevel.to_numpy()), index=idx, name="level")

    res = jorda_lp(level, shock, horizons=range(0, 7), scale_by_sd=False).to_frame()
    # beta_h should be ~0.5 for all h
    assert np.allclose(res["beta"].to_numpy(), 0.5, atol=0.07), res[["h", "beta"]]
    # standard errors positive and finite
    assert (res["se"] > 0).all() and np.isfinite(res["se"]).all()


def test_wrappers_run_and_shapes():
    rng = np.random.default_rng(1)
    n = 400
    idx = pd.date_range("1980-01-01", periods=n, freq="MS")
    ism = pd.Series(rng.normal(0, 0.2, n), index=idx).cumsum().rename("ISM")
    price = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.003, n))), index=idx)
    controls = pd.DataFrame({"x1": rng.normal(0, 1, n), "x2": rng.normal(0, 1, n)}, index=idx)

    irf = irf_price_to_ism(price, ism, controls, horizons=range(0, 13))
    assert list(irf["h"]) == list(range(0, 13))
    assert {"beta", "se", "lo_90", "hi_90"}.issubset(irf.columns)

    rec = pd.Series((rng.random(n) < 0.1).astype(float), index=idx)
    shock = pd.Series(rng.normal(0, 1, n), index=idx)
    resp = response_ism_to_shock(ism, shock, rec, horizons=range(0, 13))
    assert list(resp["h"]) == list(range(0, 13))
    assert np.isfinite(resp["beta"]).all()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
