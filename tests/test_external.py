"""Synthetic tests for ism.external_data (no network)."""
import os, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ism import external_data as ext  # noqa: E402


def test_romer_romer_dummy():
    idx = pd.date_range("1979-01-01", "1989-12-01", freq="MS")
    d = ext.romer_romer_dummy(idx, "medium_high")
    assert d.loc["1979-10-01"] == 1 and d.loc["1981-05-01"] == 1 and d.loc["1988-12-01"] == 1
    assert d.sum() == 3  # 2022 episode is outside this index window
    assert d.loc["1980-01-01"] == 0


def test_vu_splice_continuity_and_priority():
    # JOLTS openings (level, thousands) from 2000; Barnichon index from 1990.
    jolts = pd.Series(5000.0, index=pd.date_range("2000-12-01", "2010-12-01", freq="MS"))
    hwi = pd.Series(50.0, index=pd.date_range("1990-01-01", "2010-12-01", freq="MS"))  # index units
    unemp = pd.Series(10000.0, index=pd.date_range("1990-01-01", "2010-12-01", freq="MS"))
    vu = ext.build_vu_ratio(jolts, unemp, hwi)
    # On the overlap, JOLTS wins: vu = 5000/10000 = 0.5
    assert vu.loc["2005-01-01"] == pytest.approx(0.5)
    # Pre-2000, Barnichon scaled to JOLTS units (50 -> 5000), so vu also ~0.5
    assert vu.loc["1995-01-01"] == pytest.approx(0.5, rel=1e-6)
    # Falls back to JOLTS-only if no Barnichon (ratio starts 2000)
    vu2 = ext.build_vu_ratio(jolts, unemp, None)
    assert vu2.index.min() == pd.Timestamp("2000-12-01")


def test_shiller_parser(tmp_path):
    # Build a minimal ie_data-like workbook: 2 preamble rows, header (Date,P,extra), data.
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Stock Market Data", None, None])      # preamble
    ws.append([None, None, None])                      # preamble
    ws.append(["Date", "P", "Other"])                  # header row (index 2)
    rows = [(1871.01, 4.44, 1), (1871.10, 4.86, 1), (1871.12, 5.00, 1), (1872.01, 5.10, 1)]
    for r in rows:
        ws.append(list(r))
    f = tmp_path / "ie_data.xls"
    wb.save(f)

    s = ext.load_shiller_sp500(local=f)
    assert s.loc["1871-01-01"] == pytest.approx(4.44)
    assert s.loc["1871-10-01"] == pytest.approx(4.86)   # .10 -> October, not January
    assert s.loc["1871-12-01"] == pytest.approx(5.00)
    assert s.loc["1872-01-01"] == pytest.approx(5.10)
    assert s.index.is_monotonic_increasing


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
