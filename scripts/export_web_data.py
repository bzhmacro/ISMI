"""
export_web_data.py
==================

Precompute the ISM index for every discrete parameter combination and write a
compact JSON the static website consumes:  web/data/ism.json.

For each AR order in {1,3,12} x run length in {2,3,4} x weighting in
{extensive, size, stickiness} (27 combos) we export ISM / S+ / S- monthly, plus:
  * the author series and 12-month PCE inflation (overlay),
  * the category list (key + label), and
  * per-combo LATEST-month category contributions to the index (the "drivers"):
        contrib_i = w_i * (M+_i - M-_i)   (these sum exactly to ISM_t)

This script is self-fetching: it pulls the BEA tables via BeaClient (cached), so
it runs both locally and in CI (GitHub Actions). The author overlay is optional
(skipped if data/raw/external/ISM_public_author.xlsx is absent).

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
from ism.datasources import BeaClient, FredClient                    # noqa: E402
from ism.transforms import monthly_inflation, yoy_inflation          # noqa: E402

AR_ORDERS = (1, 3, 12)
RUN_LENGTHS = (2, 3, 4)
SCHEMES = ("extensive", "size", "stickiness")
RHO_CAP = 0.9
DRIVER_MIN = 1e-6   # drop ~zero contributions from the sparse drivers list

# author file may live in data/raw/ or data/raw/external/
AUTHOR_PATHS = [ROOT / "data" / "raw" / "external" / "ISM_public_author.xlsx",
                ROOT / "data" / "raw" / "ISM_public_author.xlsx"]


def _norm_key(c):
    c = str(c)
    return c[1:] if c[:2] in ("IA", "LA") else c[:-1]


def _bea_wide(bea, table):
    """Fetch a BEA table via the client (cached) and pivot to [date x key]."""
    df = bea.table(table)
    df["date"] = pd.to_datetime(df["TimePeriod"].astype(str).str.replace("M", "-") + "-01", errors="coerce")
    df["key"] = df["SeriesCode"].map(_norm_key)
    return df.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()


def build_panel():
    cats = pd.read_csv(ROOT / "config" / "pce_categories.csv")
    label_by_key = dict(zip(cats["key"].astype(str), cats["label"].astype(str)))
    bea = BeaClient()
    pw = _bea_wide(bea, "U20404")
    nw = _bea_wide(bea, "U20405")
    keys = [k for k in cats["key"].astype(str) if k in pw.columns and k in nw.columns]
    infl = monthly_inflation(pw[keys])
    weights = nw[keys].div(nw[keys].sum(axis=1).replace(0, np.nan), axis=0)
    common = infl.index.intersection(weights.index)
    return infl.loc[common], weights.loc[common], [(k, label_by_key.get(k, k)) for k in keys]


def _norm_weights(weights, valid):
    w = weights.where(valid)
    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0)


def _series_to_list(s, index):
    s = s.reindex(index)
    return [None if pd.isna(v) else round(float(v), 4) for v in s.to_numpy()]


def load_author(index):
    for p in AUTHOR_PATHS:
        if p.exists():
            a = pd.read_excel(p)
            a.columns = [c.strip() for c in a.columns]
            idx = pd.to_datetime(a["time_month"].astype(str).str.strip().str.replace("m", "-") + "-01")
            df = pd.DataFrame({"ISM": a["ISM Index"].values,
                               "S_pos": a["Positive Momentum Component"].values,
                               "S_neg": a["Negative Momentum Component"].values}, index=idx)
            return df.reindex(index)
    print("[export] author file not found -> overlay omitted")
    return None


def _latest_drivers(wn, Mp, Mn, index):
    """Sparse per-category contributions w_i*(M+_i - M-_i) at the latest month
    with a defined index value. Returns (date_str, [[cat_idx, contrib], ...])."""
    net = (Mp.fillna(0) - Mn.fillna(0))
    contrib = (wn * net)
    row_ok = contrib.notna().any(axis=1) & wn.notna().any(axis=1)
    if not row_ok.any():
        return None, []
    L = np.where(row_ok.to_numpy())[0][-1]
    vals = contrib.iloc[L].to_numpy()
    out = [[int(i), round(float(v), 5)] for i, v in enumerate(vals)
           if np.isfinite(v) and abs(v) > DRIVER_MIN]
    out.sort(key=lambda p: -abs(p[1]))
    return index[L].strftime("%Y-%m"), out


def main():
    infl, weights, categories = build_panel()
    index = infl.index
    valid_base = infl.notna() & weights.notna()

    combos, drivers = {}, {}
    for ar in AR_ORDERS:
        R = residual_panel(infl, ISMConfig(ar_order=ar))
        rho = ap.rho_panel(infl, ISMConfig(ar_order=ar)).clip(upper=RHO_CAP)
        stick = 1.0 / (1.0 - rho)
        valid = valid_base & R.notna()
        wn = _norm_weights(weights, valid)
        for k in RUN_LENGTHS:
            mp, mn = momentum_signals(R, ISMConfig(run_length=k))
            rsum = R.rolling(k, min_periods=k).sum().abs()
            for scheme in SCHEMES:
                if scheme == "extensive":
                    Mp, Mn = mp, mn
                elif scheme == "size":
                    Mp, Mn = mp * rsum, mn * rsum
                else:
                    Mp, Mn = mp * stick, mn * stick
                sp = (wn * Mp.fillna(0)).sum(axis=1)
                sn = (wn * Mn.fillna(0)).sum(axis=1)
                ism = sp - sn
                key = f"AR{ar}|k{k}|{scheme}"
                combos[key] = {"ISM": _series_to_list(ism, index),
                               "S_pos": _series_to_list(sp, index),
                               "S_neg": _series_to_list(sn, index)}
                ddate, dlist = _latest_drivers(wn, Mp, Mn, index)
                drivers[key] = {"date": ddate, "contrib": dlist}
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
        "categories": [{"key": k, "label": lab} for k, lab in categories],
        "author": None if author is None else {
            "ISM": _series_to_list(author["ISM"], index),
            "S_pos": _series_to_list(author["S_pos"], index),
            "S_neg": _series_to_list(author["S_neg"], index)},
        "pce_yoy": _series_to_list(pce_yoy, index),
        "combos": combos,
        "drivers": drivers,
    }
    dest = ROOT / "web" / "data" / "ism.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {dest} ({dest.stat().st_size/1024:.0f} KB, {len(combos)} combos, "
          f"{len(index)} months, {len(categories)} categories)")


if __name__ == "__main__":
    main()
