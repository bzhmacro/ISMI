"""
FINAL category selection + convergence check.

The paper's 129 fourth-level categories = the level-5 cut of BEA table 2.4.4U
(every node at level 5 plus branches that terminate earlier), EXCLUDING:
  - addenda / special aggregates (Market-based, *excluding*, gross output,
    Control group, PCE food/energy aggregates, Less: lines), and
  - the NPISH "... services to households" net-output lines (a parallel
    accounting layer that overlaps the regular service categories).

This lands on exactly 129 categories. The script pins them to
config/pce_categories.csv and reports correlation of ISM / S+ / S- vs the author.

Run:  python scripts/finalize_categories.py
"""
import csv, json, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ism.engine import ISMConfig, compute_ism
BEA = ROOT / "data" / "raw" / "bea"
CSV = BEA / "T20404U_interactive.csv"
OUT = ROOT / "config" / "pce_categories.csv"

EXCLUDE = re.compile(
    r"(Market-based|excluding|gross output|Control group|^Less:|Addenda|"
    r"services to households|"                       # NPISH net-output layer
    r"Final consumption expenditures of nonprofit|"
    r"PCE energy goods|PCE food and energy)", re.I)


def key(c):
    c = str(c); return c[1:] if c[:2] in ("IA", "LA") else c[:-1]


def load_api(table):
    d = json.loads((BEA / f"{table}_M.json").read_text())
    df = pd.DataFrame(d["BEAAPI"]["Results"]["Data"])
    df["DataValue"] = pd.to_numeric(df["DataValue"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df["LineNumber"] = pd.to_numeric(df["LineNumber"], errors="coerce")
    df["date"] = pd.to_datetime(df["TimePeriod"].astype(str).str.replace("M", "-") + "-01", errors="coerce")
    df["key"] = df["SeriesCode"].map(key)
    return df


def parse_csv():
    rows = []
    with open(CSV, newline="", encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            if len(r) < 2 or not str(r[0]).strip().lstrip("-").isdigit():
                continue
            label = r[1]; depth = len(label) - len(label.lstrip(" "))
            rows.append((int(str(r[0]).strip()), depth, label.strip()))
    t = pd.DataFrame(rows, columns=["line", "depth", "label"])
    w = sorted(t["depth"].unique()); t["level"] = t["depth"].map({x: i + 1 for i, x in enumerate(w)})
    t["has_child"] = t["depth"].shift(-1).fillna(-1).to_numpy() > t["depth"].to_numpy()
    t["excl"] = t["label"].str.contains(EXCLUDE, regex=True)
    t.loc[t["label"].str.fullmatch(r"Personal consumption expenditures.*"), "excl"] = True
    return t


price, nominal = load_api("U20404"), load_api("U20405")
line2code = price.dropna(subset=["LineNumber"]).drop_duplicates("LineNumber").set_index("LineNumber")["SeriesCode"]
pw = price.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()
nw = nominal.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()

tree = parse_csv()
tree["SeriesCode"] = tree["line"].map(line2code); tree["key"] = tree["SeriesCode"].map(key)
tree = tree.dropna(subset=["SeriesCode"])

TARGET_LEVEL = 5
at = tree["level"] == TARGET_LEVEL
shallow = (tree["level"] < TARGET_LEVEL) & (~tree["has_child"])
sel = tree[(at | shallow) & ~tree["excl"]].drop_duplicates("key")
print(f"SELECTED CATEGORIES: {len(sel)}  (paper: 129)")

OUT.parent.mkdir(parents=True, exist_ok=True)
# BEA's own PCE goods/services split: table 2.4.5U puts "Goods" at line 2 and
# "Services" at line 150, so every leaf with line < 150 is a good and line >= 150
# a service. Emit it as the `gs` column so the decomposition's goods/services
# scopes (ism.decomp_pipeline.goods_services_keys) survive a category rebuild.
sel = sel.copy()
sel["gs"] = ["G" if int(x) < 150 else "S" for x in sel["line"]]
sel[["key", "SeriesCode", "line", "level", "label", "gs"]].to_csv(OUT, index=False)
print(f"wrote -> {OUT}  (goods={int((sel['gs']=='G').sum())}, "
      f"services={int((sel['gs']=='S').sum())})")

# build ISM and validate
keys = [k for k in sel["key"] if k in pw.columns and k in nw.columns]
infl = 100 * (np.log(pw[keys]) - np.log(pw[keys].shift(1)))
wts = nw[keys].div(nw[keys].sum(axis=1).replace(0, np.nan), axis=0)
common = infl.index.intersection(wts.index)
res = compute_ism(infl.loc[common], wts.loc[common], ISMConfig())

a = pd.read_excel(ROOT / "data" / "raw" / "ISM_public_author.xlsx"); a.columns = [c.strip() for c in a.columns]
aidx = pd.to_datetime(a["time_month"].astype(str).str.strip().str.replace("m", "-") + "-01")
truth = pd.DataFrame({"ISM": a["ISM Index"].values, "S_pos": a["Positive Momentum Component"].values,
                      "S_neg": a["Negative Momentum Component"].values}, index=aidx)

def stats(x, y):
    j = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna(); d = j["x"] - j["y"]
    return round(j["x"].corr(j["y"]), 4), round(float(np.sqrt((d**2).mean())), 4), round(float(d.abs().max()), 4)

print("\nconvergence vs author (corr, rmse, max_abs):")
for nm, col, s in [("ISM", "ISM", res.ism), ("S_pos", "S_pos", res.s_pos), ("S_neg", "S_neg", res.s_neg)]:
    print(f"  {nm:6s}", stats(s, truth[col]))

pd.concat([res.ism, res.s_pos, res.s_neg], axis=1).to_csv(ROOT / "data" / "processed" / "ism_index_replicated.csv")
print("\nsaved data/processed/ism_index_replicated.csv")
