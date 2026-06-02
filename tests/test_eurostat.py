"""Synthetic tests for ism.eurostat (no network)."""
import os, sys
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ism import eurostat as eu  # noqa: E402


def _synthetic_jsonstat():
    # dims [coicop, time]; size [2,2]; row-major flat = coicop_pos*2 + time_pos
    return {
        "id": ["coicop", "time"],
        "size": [2, 2],
        "dimension": {
            "coicop": {"category": {"index": {"CP00": 0, "CP01": 1},
                                     "label": {"CP00": "All-items", "CP01": "Food"}}},
            "time": {"category": {"index": {"2020-01": 0, "2020-02": 1}}},
        },
        "value": {"0": 100.0, "1": 101.0, "2": 50.0, "3": 50.5},
    }


def test_parse_jsonstat_decodes_grid():
    df = eu.parse_jsonstat(_synthetic_jsonstat())
    assert len(df) == 4
    df["date"] = eu._eu_time_to_timestamp(df["time"])
    wide = df.pivot_table(index="date", columns="coicop", values="value")
    assert wide.loc["2020-01-01", "CP00"] == pytest.approx(100.0)
    assert wide.loc["2020-02-01", "CP00"] == pytest.approx(101.0)
    assert wide.loc["2020-01-01", "CP01"] == pytest.approx(50.0)
    assert wide.loc["2020-02-01", "CP01"] == pytest.approx(50.5)


def test_time_code_variants():
    s = pd.Series(["2020M01", "2020-12"])
    out = eu._eu_time_to_timestamp(s)
    assert list(out) == [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-01")]


def test_monthly_weights_ffill():
    annual = pd.DataFrame({"CP00": [1000, 1000], "CP01": [120, 130]}, index=[2019, 2020])
    midx = pd.date_range("2019-01-01", "2020-12-01", freq="MS")
    mw = eu.monthly_weights_from_annual(annual, midx)
    assert mw.loc["2019-06-01", "CP01"] == 120      # 2019 weight held through the year
    assert mw.loc["2020-06-01", "CP01"] == 130      # 2020 weight from Jan 2020
    assert mw.shape[0] == len(midx)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
