"""Synthetic tests for ism.oos_lasso (no network)."""
import os, sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ism.oos_lasso import (  # noqa: E402
    fit_adaptive_lasso, rolling_oos, choose_lambda, giacomini_white, table2,
)


def test_adaptive_lasso_recovers_sparsity():
    rng = np.random.default_rng(0)
    n = 400
    X = pd.DataFrame({f"x{j}": rng.normal(0, 1, n) for j in range(5)})
    y = (3.0 * X["x0"] - 2.0 * X["x1"] + rng.normal(0, 0.1, n)).rename("y")
    fit = fit_adaptive_lasso(X, y, lam=0.05)
    b = dict(zip(fit.columns, fit.beta_std))
    # relevant predictors large, irrelevant near zero (standardized coefs)
    assert abs(b["x0"]) > 1.0 and abs(b["x1"]) > 0.5
    assert all(abs(b[f"x{j}"]) < 0.2 for j in (2, 3, 4))


def test_gw_detects_better_model():
    rng = np.random.default_rng(1)
    n = 300
    err_base = pd.Series(rng.normal(0, 1.0, n))      # larger errors
    err_alt = pd.Series(rng.normal(0, 0.6, n))       # smaller errors -> better
    gw = giacomini_white(err_base, err_alt)
    assert gw["mean_loss_diff"] > 0 and gw["p"] < 0.05


def test_table2_ism_helps_when_predictive():
    rng = np.random.default_rng(2)
    n = 360
    idx = pd.date_range("1990-01-01", periods=n, freq="MS")
    ism = pd.Series(rng.normal(0, 0.2, n), index=idx).rename("ISM")
    pce = pd.Series(rng.normal(0, 0.5, n), index=idx).cumsum() * 0  # placeholder
    # Construct pce_yoy so that future inflation depends on ISM (genuine signal).
    base = pd.Series(2.0 + rng.normal(0, 0.3, n), index=idx)
    pce_yoy = base.rename("pce_yoy")
    # make y_{t+12} depend on ISM_t: embed by setting pce_yoy[t+12] += 1.5*ISM[t]
    arr = pce_yoy.to_numpy().copy()
    ismv = ism.to_numpy()
    for t in range(n - 12):
        arr[t + 12] += 1.5 * ismv[t]
    pce_yoy = pd.Series(arr, index=idx, name="pce_yoy")

    tbl = table2(pce_yoy, ism, controls=None, horizons=(12,), lam_grid=np.logspace(-3, 0, 8), window=120)
    row = tbl.iloc[0]
    assert row["rmsfe_ratio"] < 1.0          # +ISM forecasts better
    assert row["GW_p"] < 0.10                 # and significantly so


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
