"""Synthetic tests for ism.eu_pipeline (no network)."""
import os, sys
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ism import eu_pipeline as eup  # noqa: E402


def _panel(cols):
    idx = pd.date_range("2000-01-01", periods=3, freq="MS")
    return pd.DataFrame(1.0, index=idx, columns=cols)


def test_coicop_leaf_selection_depth4():
    cols = ["CP00", "CP01", "CP011", "CP0111", "CP0112", "CP012", "CP02", "GD", "SERV"]
    leaves = eup.select_coicop_leaves(_panel(cols), max_digits=4)
    assert leaves == sorted(["CP0111", "CP0112", "CP012", "CP02"])
    # analytic aggregates (GD, SERV) and all-items CP00 excluded
    assert "GD" not in leaves and "SERV" not in leaves and "CP00" not in leaves


def test_coicop_leaf_selection_depth3():
    cols = ["CP00", "CP01", "CP011", "CP0111", "CP012", "CP02"]
    leaves = eup.select_coicop_leaves(_panel(cols), max_digits=3)
    assert leaves == sorted(["CP011", "CP012", "CP02"])   # capped at 3 digits


def test_cepr_recession_dummy():
    idx = pd.date_range("2007-01-01", "2021-12-01", freq="MS")
    d = eup.cepr_recession_dummy(idx)
    assert d.loc["2009-01-01"] == 1     # GFC
    assert d.loc["2020-04-01"] == 1     # covid
    assert d.loc["2017-06-01"] == 0     # expansion
    assert set(d.unique()).issubset({0.0, 1.0})


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
