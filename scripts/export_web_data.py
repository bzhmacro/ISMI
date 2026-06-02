"""
export_web_data.py
==================

Precompute the ISM index for every discrete parameter combination and write a
compact JSON the static website consumes. Run on your machine after the BEA data
is cached (see ISM_replication.ipynb / build_and_validate.py).

Combinations exported:
    AR order   in {1, 3, 12}
    run length in {2, 3, 4}
    weighting  in {extensive, size, stickiness}
= 27 combos, each a monthly series of ISM / S+ / S-.  Plus the author series and
12-month PCE inflation for overlay. Output: web/public/data/ism.json (small;
~27*3*~800 numbers).

    python scripts/export_web_data.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ism.engine import ISMConfig, residual_panel, momentum_signals  # noqa: E402
from ism import appendix as ap                                       # noqa: E402
from ism.datasources import FredClient                               # noqa: E402
from ism.transforms import monthly_inflation, yoy_inflation          # noqa: E402

BEA = ROOT / "data" / "raw" / "bea"
AR_ORDERS = (1, 3, 12)
RUN_LENGTHS = (2, 3, 4)
SCHEMES = ("extensive", "size", "stickiness")
RHO_CAP = 0.9


def _norm_key(c):
    c = str(c)
    return c[1:] if c[:2] in ("IA", "LA") else c[:-1]


def _load_bea(table):
    d = json.loads((BEA / f"{table}_M.json").read_text())
    df = pd.DataFrame(d["BEAAPI"]["Results"]["Data"])
    df["DataValue"] = pd.to_numeric(df["DataValue"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df["date"] = pd.to_datetime(df["TimePeriod"].astype(str).str.replace("M", "-") + "-01", errors="coerce")
    df["key"] = df["SeriesCode"].map(_norm_key)
    return df


def build_panel():
    keys = pd.read_csv(ROOT / "config" / "pce_categories.csv")["key"].astype(str).tolist()
    price, nominal = _load_bea("U20404"), _load_bea("U20405")
    pw = price.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()
    nw = nominal.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()
    keys = [k for k in keys if k in pw.columns and k in nw.columns]
    infl = monthly_inflation(pw[keys])
    weights = nw[keys].div(nw[keys].sum(axis=1).replace(0, np.nan), axis=0)
    common = infl.index.intersection(weights.index)
    return infl.loc[common], weights.loc[common]


def _shares(Mp, Mn, weights, valid):
    """Expenditure-weighted shares, renormalising weights monthly over the
    categories with a defined residual (valid) so shares stay in [0,1]."""
    w = weights.where(valid)
    wn = w.div(w.sum(axis=1).replace(0, np.nan), axis=0)
    sp = (wn * Mp.fillna(0)).sum(axis=1)
    sn = (wn * Mn.fillna(0)).sum(axis=1)
    return sp, sn


def _series_to_list(s, index):
    s = s.reindex(index)
    return [None if pd.isna(v) else round(float(v), 4) for v in s.to_numpy()]


def load_author(index):
    a = pd.read_excel(ROOT / "data" / "raw" / "ISM_public_author.xlsx")
    a.columns = [c.strip() for c in a.columns]
    idx = pd.to_datetime(a["time_month"].astype(str).str.strip().str.replace("m", "-") + "-01")
    df = pd.DataFrame({"ISM": a["ISM Index"].values, "S_pos": a["Positive Momentum Component"].values,
                       "S_neg": a["Negative Momentum Component"].values}, index=idx)
    return df.reindex(index)


def main():
    infl, weights = build_panel()
    index = infl.index
    valid_base = infl.notna() & weights.notna()

    combos = {}
    for ar in AR_ORDERS:
        R = residual_panel(infl, ISMConfig(ar_order=ar))
        rho = ap.rho_panel(infl, ISMConfig(ar_order=ar)).clip(upper=RHO_CAP)
        stick = 1.0 / (1.0 - rho)
        valid = valid_base & R.notna()
        for k in RUN_LENGTHS:
            mp, mn = momentum_signals(R, ISMConfig(run_length=k))
            rsum = R.rolling(k, min_periods=k).sum().abs()
            for scheme in SCHEMES:
                if scheme == "extensive":
                    Mp, Mn = mp, mn
                elif scheme == "size":
                    Mp, Mn = mp * rsum, mn * rsum
                else:  # stickiness
                    Mp, Mn = mp * stick, mn * stick
                sp, sn = _shares(Mp, Mn, weights, valid)
                ism = sp - sn
                combos[f"AR{ar}|k{k}|{scheme}"] = {
                    "ISM": _series_to_list(ism, index),
                    "S_pos": _series_to_list(sp, index),
                    "S_neg": _series_to_list(sn, index),
                }
        print(f"  AR({ar}) done")

    fred = FredClient()
    pcepi = fred.series("PCEPI"); pcepi.index = pd.to_datetime(pcepi.index).to_period("M").to_timestamp()
    pce_yoy = yoy_inflation(pcepi)
    author = load_author(index)

    out = {
        "meta": {
            "n_categories": int(infl.shape[1]),
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "ar_orders": list(AR_ORDERS), "run_lengths": list(RUN_LENGTHS), "schemes": list(SCHEMES),
            "paper": "Lansing & Shapiro (2026), FRBSF WP 2026-10",
            "note": "ISM index by parameter combo, rebuilt from BEA underlying detail (corr 0.99 vs authors).",
        },
        "dates": [d.strftime("%Y-%m") for d in index],
        "author": {"ISM": _series_to_list(author["ISM"], index),
                   "S_pos": _series_to_list(author["S_pos"], index),
                   "S_neg": _series_to_list(author["S_neg"], index)},
        "pce_yoy": _series_to_list(pce_yoy, index),
        "combos": combos,
    }
    dest = ROOT / "web" / "data" / "ism.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    kb = dest.stat().st_size / 1024
    print(f"wrote {dest} ({kb:.0f} KB, {len(combos)} combos, {len(index)} months)")


if __name__ == "__main__":
    main()
