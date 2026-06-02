"""
Canonical ISM builder + convergence check (run on your machine).

Category set: the 129/130 fourth-level PCE categories pinned in
config/pce_categories.csv (produced by scripts/finalize_categories.py from the
BEA interactive table 2.4.4U: level-5 cut, excluding addenda/special aggregates
and the NPISH "... services to households" net-output layer).

Pipeline:
  - read pinned category keys from config/pce_categories.csv
  - load full-history price (U20404) & nominal (U20405) from data/raw/bea/*.json
    matching price (...RG / IA...) to nominal (...RC / LA...) on a normalized key
  - monthly inflation = 100*dln(price); weights = nominal share (renormalised)
  - compute ISM via the tested engine, validate vs author file, save outputs

Run:  python scripts/build_and_validate.py
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ism.engine import ISMConfig, compute_ism

BEA = ROOT / "data" / "raw" / "bea"
CONFIG = ROOT / "config" / "pce_categories.csv"


def norm_key(code):
    code = str(code)
    return code[1:] if code[:2] in ("IA", "LA") else code[:-1]


def load_api(table):
    d = json.loads((BEA / f"{table}_M.json").read_text())
    df = pd.DataFrame(d["BEAAPI"]["Results"]["Data"])
    df["DataValue"] = pd.to_numeric(df["DataValue"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df["date"] = pd.to_datetime(df["TimePeriod"].astype(str).str.replace("M", "-") + "-01", errors="coerce")
    df["key"] = df["SeriesCode"].map(norm_key)
    return df


def build_panel():
    keys = pd.read_csv(CONFIG)["key"].astype(str).tolist()
    price, nominal = load_api("U20404"), load_api("U20405")
    pw = price.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()
    nw = nominal.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()
    keys = [k for k in keys if k in pw.columns and k in nw.columns]
    infl = 100 * (np.log(pw[keys]) - np.log(pw[keys].shift(1)))
    weights = nw[keys].div(nw[keys].sum(axis=1).replace(0, np.nan), axis=0)
    common = infl.index.intersection(weights.index)
    return infl.loc[common], weights.loc[common], len(keys)


def load_author():
    a = pd.read_excel(ROOT / "data" / "raw" / "ISM_public_author.xlsx"); a.columns = [c.strip() for c in a.columns]
    idx = pd.to_datetime(a["time_month"].astype(str).str.strip().str.replace("m", "-") + "-01")
    return pd.DataFrame({"ISM": a["ISM Index"].values, "S_pos": a["Positive Momentum Component"].values,
                         "S_neg": a["Negative Momentum Component"].values}, index=idx)


def stats(x, y):
    j = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna(); d = j["x"] - j["y"]
    return dict(corr=round(j["x"].corr(j["y"]), 4), rmse=round(float(np.sqrt((d**2).mean())), 4),
                max_abs=round(float(d.abs().max()), 4), n=len(j))


if __name__ == "__main__":
    infl, weights, ncat = build_panel()
    print(f"panel: {infl.shape[0]} months x {ncat} categories, {infl.index.min().date()} -> {infl.index.max().date()}")
    res = compute_ism(infl, weights, ISMConfig())          # AR(1), W=120, k=3
    truth = load_author()
    print("convergence vs author:")
    for nm, col, s in [("ISM", "ISM", res.ism), ("S_pos", "S_pos", res.s_pos), ("S_neg", "S_neg", res.s_neg)]:
        print(f"  {nm:6s}", stats(s, truth[col]))
    out = ROOT / "data" / "processed"; out.mkdir(parents=True, exist_ok=True)
    pd.concat([res.ism, res.s_pos, res.s_neg], axis=1).rename(
        columns={"S_pos": "Positive Momentum", "S_neg": "Negative Momentum"}
    ).to_csv(out / "ism_index_replicated.csv")
    print(f"saved {out/'ism_index_replicated.csv'}")
