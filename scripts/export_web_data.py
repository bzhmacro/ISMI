"""
export_web_data.py
==================

Export the RAW category panels (inflation + expenditure weights) for the
price backbones -- PCE (BEA underlying detail), CPI (BLS item strata) and
UK CPI (ONS COICOP classes) -- plus ONE precomputed baseline combo, into the
compact JSON the static website consumes:  web/data/ism.json.

Since schema v3 the website computes the ISM index CLIENT-SIDE (web/engine.js,
a parity-tested port of src/ism/engine.py), so users can vary every parameter
continuously (AR order, window length W, run length k, weighting scheme, rho
cap, category exclusions). This script therefore ships:
  * per-backbone "panel": {"inflation": [...], "weights": [...]} -- one array
    per category, monthly, nulls for missing (rounded to 8 dp; the browser
    engine consumes these directly),
  * the baseline combo AR(1)|k=3|extensive precomputed (instant first paint
    before the worker finishes booting) + its latest-month drivers,
  * the author overlay (PCE only), 12-month headline inflation, and the
    category list (key + label).

Output schema (v3, backbone-aware)::

    { "meta": {..., "schema": 3, "ui": {...},
               "default_backbone": "pce", "backbones": ["pce","cpi","uk"]},
      "backbones": {
        "pce": { "label","source_note","n_categories","note","dates",
                 "categories","author","headline":{"label","series"},
                 "panel","combos","drivers" },
        "cpi": { ... , "author": null },
        "uk":  { ... , "author": null } } }

The PCE backbone self-fetches the BEA tables via BeaClient (cached); the CPI
backbone self-fetches the BLS item strata via BlsClient (cached); the UK
backbone self-fetches the ONS MM23 bulk CSV via OnsClient (cached).  Each
backbone is built independently and a failure in one (e.g. BEA host blocked)
does not abort the other -- the website simply hides any backbone that is
absent.

The parity contract between this exporter's maths and the browser engine is
enforced by tests/test_web_engine_parity.py.

    python scripts/export_web_data.py            # all backbones (pce cpi uk fr de jp)
    python scripts/export_web_data.py pce         # only PCE
    python scripts/export_web_data.py uk          # only UK CPI (ONS MM23)
    python scripts/export_web_data.py fr de       # France + Germany (Eurostat HICP v2)
    python scripts/export_web_data.py jp          # Japan (e-Stat; needs ESTAT_API_ID)
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
from ism.datasources import BeaClient, FredClient, BlsClient         # noqa: E402
from ism.transforms import monthly_inflation, yoy_inflation          # noqa: E402
from ism import cpi_pipeline                                         # noqa: E402
from ism import uk_pipeline                                          # noqa: E402
from ism.ons import OnsClient                                        # noqa: E402
from ism.eurostat import (EurostatClient, hicp_labels,               # noqa: E402
                          hicp_price_panel, hicp_weights,
                          monthly_weights_from_annual, HICP_ALL_ITEMS)
from ism.eu_pipeline import select_coicop_leaves                     # noqa: E402

AR_ORDERS = (1, 3, 12)
SCHEMES = ("extensive", "size", "stickiness")
RHO_CAP = 0.9
DRIVER_MIN = 1e-6   # drop ~zero contributions from the sparse drivers list
PANEL_DP = 8        # decimals kept for the raw panels shipped to the browser

# the one combo precomputed for instant first paint (the paper's baseline)
BASELINE = dict(ar=1, k=3, scheme="extensive")

# parameter ranges the website exposes (the browser engine accepts anything;
# these just bound the controls)
UI_PARAMS = {
    "ar_orders": list(AR_ORDERS),
    "window": {"min": 60, "max": 240, "step": 6, "default": 120},
    "k": {"min": 2, "max": 8, "default": 3},
    "schemes": list(SCHEMES),
    "rho_cap": {"min": 0.5, "max": 0.99, "step": 0.01, "default": RHO_CAP},
}

# author file may live in data/raw/ or data/raw/external/
AUTHOR_PATHS = [ROOT / "data" / "raw" / "external" / "ISM_public_author.xlsx",
                ROOT / "data" / "raw" / "ISM_public_author.xlsx"]


# ---------------------------------------------------------------------------
# small helpers (shared across backbones)
# ---------------------------------------------------------------------------
def _norm_key(c):
    c = str(c)
    return c[1:] if c[:2] in ("IA", "LA") else c[:-1]


def _bea_wide(bea, table):
    """Fetch a BEA table via the client (cached) and pivot to [date x key]."""
    df = bea.table(table)
    df["date"] = pd.to_datetime(df["TimePeriod"].astype(str).str.replace("M", "-") + "-01", errors="coerce")
    df["key"] = df["SeriesCode"].map(_norm_key)
    return df.pivot_table(index="date", columns="key", values="DataValue", aggfunc="first").sort_index()


def _norm_weights(weights, valid):
    w = weights.where(valid)
    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0)


def _series_to_list(s, index):
    s = s.reindex(index)
    return [None if pd.isna(v) else round(float(v), 4) for v in s.to_numpy()]


def _latest_drivers(wn, Mp, Mn, index, n_history=22):
    """Sparse per-category contributions w_i*(M+_i - M-_i).

    Returns (date_str, contrib_list, history) where:
      - date_str / contrib_list  = latest month (backward-compat)
      - history = list of {date, contrib} for the last n_history valid months
    """
    net = (Mp.fillna(0) - Mn.fillna(0))
    contrib = (wn * net)
    row_ok = contrib.notna().any(axis=1) & wn.notna().any(axis=1)
    if not row_ok.any():
        return None, [], []
    valid_locs = list(np.where(row_ok.to_numpy())[0])
    # latest entry (backward-compat)
    L = valid_locs[-1]
    def _row(loc):
        vals = contrib.iloc[loc].to_numpy()
        out = [[int(i), round(float(v), 5)] for i, v in enumerate(vals)
               if np.isfinite(v) and abs(v) > DRIVER_MIN]
        out.sort(key=lambda p: -abs(p[1]))
        return index[loc].strftime("%Y-%m"), out
    latest_date, latest_contrib = _row(L)
    # history: last n_history valid months, newest-last
    history_locs = valid_locs[-n_history:]
    history = [{"date": d, "contrib": c} for loc in history_locs for d, c in [_row(loc)]]
    return latest_date, latest_contrib, history


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


# ---------------------------------------------------------------------------
# panel builders, one per backbone -> (inflation_panel, weights, categories)
# ---------------------------------------------------------------------------
def build_pce_panel():
    cats = pd.read_csv(ROOT / "config" / "pce_categories.csv")
    label_by_key = dict(zip(cats["key"].astype(str), cats["label"].astype(str)))
    bea = BeaClient()
    pw = _bea_wide(bea, "U20404")
    nw = _bea_wide(bea, "U20405")
    keys = [k for k in cats["key"].astype(str) if k in pw.columns and k in nw.columns]
    infl = monthly_inflation(pw[keys])
    weights = nw[keys].div(nw[keys].sum(axis=1).replace(0, np.nan), axis=0)
    common = infl.index.intersection(weights.index)
    cat_list = [(k, label_by_key.get(k, k)) for k in keys]
    return infl.loc[common], weights.loc[common], cat_list


def build_cpi_panel():
    cats = cpi_pipeline.load_cpi_categories()
    label_by_key = dict(zip(cats["key"], cats["label"]))
    infl, weights = cpi_pipeline.build_cpi_category_panel(BlsClient())
    keys = list(infl.columns)
    cat_list = [(k, label_by_key.get(k, k)) for k in keys]
    return infl, weights, cat_list


def build_uk_panel():
    infl, weights, labels = uk_pipeline.build_uk_cpi_panel(OnsClient())
    # labels are SHOUTING in MM23; title-case them for the UI, keep the code.
    def pretty(code, lab):
        lab = lab.title() if lab.isupper() else lab
        return f"{lab} ({code})"
    cat_list = [(k, pretty(k, labels[k])) for k in infl.columns]
    return infl, weights, cat_list


def build_euro_panel(geo):
    """HICP (ECOICOP v2) -> (inflation, weights, categories, headline_yoy).

    Same construction as ism.eu_pipeline.build_hicp_panel, but also returns
    the labelled category list and the all-items yoy for the web payload.
    """
    client = EurostatClient()
    price = hicp_price_panel(client, geo=geo)
    headline = yoy_inflation(price[HICP_ALL_ITEMS])
    leaves = select_coicop_leaves(price)
    price = price[leaves].dropna(how="all", axis=1)
    annual = hicp_weights(client, geo=geo)
    wm = monthly_weights_from_annual(annual, price.index)
    cols = [c for c in price.columns if c in wm.columns]
    price, wm = price[cols], wm[cols]
    infl = monthly_inflation(price)
    weights = wm.where(price.notna())
    weights = weights.div(weights.sum(axis=1).replace(0, np.nan), axis=0)
    common = infl.index.intersection(weights.index)
    labels = hicp_labels(client, geo=geo)
    cat_list = [(c, f"{labels.get(c, c)} ({c})") for c in cols]
    return infl.loc[common], weights.loc[common], cat_list, headline


# ---------------------------------------------------------------------------
# the core: baseline combo (for instant paint) + raw panels (for the browser)
# ---------------------------------------------------------------------------
def compute_baseline(infl, weights):
    """Precompute the single BASELINE combo, mirroring web/engine.js exactly."""
    index = infl.index
    ar, k, scheme = BASELINE["ar"], BASELINE["k"], BASELINE["scheme"]
    assert scheme == "extensive", "baseline must be the extensive-margin combo"

    R = residual_panel(infl, ISMConfig(ar_order=ar))
    valid = infl.notna() & weights.notna() & R.notna()
    wn = _norm_weights(weights, valid)
    mp, mn = momentum_signals(R, ISMConfig(run_length=k))
    sp = (wn * mp.fillna(0)).sum(axis=1)
    sn = (wn * mn.fillna(0)).sum(axis=1)
    # months with no valid category have an UNDEFINED index, not 0 (the browser
    # engine emits null there too)
    dead = ~valid.any(axis=1)
    sp[dead], sn[dead] = np.nan, np.nan
    ism = sp - sn

    key = f"AR{ar}|k{k}|{scheme}"
    combos = {key: {"ISM": _series_to_list(ism, index),
                    "S_pos": _series_to_list(sp, index),
                    "S_neg": _series_to_list(sn, index)}}
    ddate, dlist, dhistory = _latest_drivers(wn, mp, mn, index)
    drivers = {key: {"date": ddate, "contrib": dlist, "history": dhistory}}
    print(f"    baseline {key} done")
    return combos, drivers


def panel_payload(infl, weights):
    """Raw per-category panels for the client-side engine (nulls for NaN)."""
    def cols(df):
        out = []
        for c in df.columns:
            v = df[c].to_numpy(dtype=float)
            out.append([None if not np.isfinite(x) else round(float(x), PANEL_DP)
                        for x in v])
        return out
    return {"inflation": cols(infl), "weights": cols(weights)}


def build_backbone(name):
    """Assemble the full per-backbone payload, or None if its data is unreachable."""
    try:
        if name == "pce":
            infl, weights, categories = build_pce_panel()
            label, source_note = "PCE", "BEA Underlying Detail (tables 2.4.4U / 2.4.5U)"
            head_label = "PCE inflation (12m, %)"
            fred = FredClient()
            pcepi = fred.series("PCEPI")
            pcepi.index = pd.to_datetime(pcepi.index).to_period("M").to_timestamp()
            headline = yoy_inflation(pcepi)
            author = load_author(infl.index)
            note = "ISM computed in the browser from BEA underlying detail (corr 0.99 vs authors)."
            weight_note = "expenditure weights = monthly nominal PCE shares (BEA 2.4.5U)"
        elif name == "cpi":
            infl, weights, categories = build_cpi_panel()
            label, source_note = "CPI", "BLS CPI-U item strata (CUUR0000*, US city average, NSA)"
            head_label = "CPI inflation (12m, %)"
            headline = cpi_pipeline.headline_cpi_yoy(BlsClient())
            author = None  # no published author ISM for the CPI backbone
            note = ("ISM computed in the browser from BLS CPI item strata; "
                    "weights = Dec-2023 relative importance (renormalised monthly).")
            weight_note = "weights = BLS Dec-2023 relative importance (static, renormalised monthly)"
        elif name == "uk":
            infl, weights, categories = build_uk_panel()
            label, source_note = "UK CPI", "ONS MM23 consumer price inflation series (COICOP class level, NSA)"
            head_label = "UK CPI inflation (12m, %)"
            headline = uk_pipeline.headline_uk_cpi_yoy(OnsClient())
            author = None  # no published author ISM for the UK
            note = ("ISM computed in the browser from ONS CPI COICOP classes "
                    "(MM23); weights = annual ONS CPI weights (per mille), "
                    "forward-filled monthly and renormalised. History starts "
                    "1988, so the W=120 baseline yields an index from ~1998.")
            weight_note = "weights = ONS annual CPI weights (per mille), ffilled monthly, renormalised"
        elif name in ("fr", "de"):
            geo = name.upper()
            country = {"fr": "France", "de": "Germany"}[name]
            infl, weights, categories, headline = build_euro_panel(geo)
            label = f"{geo} HICP"
            source_note = f"Eurostat HICP ECOICOP v2 (prc_hicp_minr / prc_hicp_iw, geo={geo}, NSA)"
            head_label = f"{country} HICP inflation (12m, %)"
            author = None
            note = (f"ISM computed in the browser from {country}'s HICP by COICOP "
                    "(Eurostat, ECOICOP v2, class-level leaves); weights = annual "
                    "HICP item weights, forward-filled monthly and renormalised. "
                    "History starts 1996, so the W=120 baseline yields an index "
                    "from ~2006.")
            weight_note = "weights = annual Eurostat HICP item weights (per mille), ffilled monthly, renormalised"
        elif name == "jp":
            # Requires a free e-Stat application ID (ESTAT_API_ID in .env);
            # without it this backbone is skipped with a clear message.
            from ism import jp_pipeline
            from ism.estat import EstatClient
            client = EstatClient()
            infl, weights, labels = jp_pipeline.build_jp_cpi_panel(client)
            categories = [(k, f"{labels[k]} ({k})") for k in infl.columns]
            label, source_note = "JP CPI", "Statistics Bureau of Japan CPI via e-Stat (2020-base, table 0003427113, NSA)"
            head_label = "Japan CPI inflation (12m, %)"
            headline = jp_pipeline.headline_jp_cpi_yoy(client)
            author = None
            note = ("ISM computed in the browser from Japan's CPI item "
                    "classification (e-Stat); weights = per-base CPI weights "
                    "(fixed between base revisions), renormalised monthly.")
            weight_note = "weights = CPI weights per base revision (static within base, renormalised monthly)"
        else:
            raise ValueError(name)
    except Exception as exc:   # e.g. BEA host blocked, or BLS unavailable
        print(f"  [{name}] skipped: {type(exc).__name__}: {exc}")
        return None

    print(f"  [{name}] {infl.shape[1]} categories, {infl.shape[0]} months")
    # Round FIRST, then compute the baseline from the rounded panel, so the
    # precomputed combo and the browser engine see byte-identical inputs (a
    # borderline residual sign can otherwise flip between the two).
    infl, weights = infl.round(PANEL_DP), weights.round(PANEL_DP)
    combos, drivers = compute_baseline(infl, weights)
    index = infl.index
    return {
        "panel": panel_payload(infl, weights),
        "label": label,
        "source_note": source_note,
        "weight_note": weight_note,
        "n_categories": int(infl.shape[1]),
        "note": note,
        "dates": [d.strftime("%Y-%m") for d in index],
        "categories": [{"key": k, "label": lab} for k, lab in categories],
        "author": None if author is None else {
            "ISM": _series_to_list(author["ISM"], index),
            "S_pos": _series_to_list(author["S_pos"], index),
            "S_neg": _series_to_list(author["S_neg"], index)},
        "headline": {"label": head_label, "series": _series_to_list(headline, index)},
        "combos": combos,
        "drivers": drivers,
    }


def main(argv=None):
    argv = argv or sys.argv[1:]
    wanted = [a.lower() for a in argv] or ["pce", "cpi", "uk", "fr", "de", "jp"]

    dest = ROOT / "web" / "data" / "ism.json"

    # Seed from any existing file so a partial regen (e.g. `... cpi`) refreshes
    # only the requested gauge and preserves the other backbone's real data.
    backbones, prev_default = {}, None
    if dest.exists():
        try:
            prev = json.loads(dest.read_text())
            if "backbones" in prev:
                backbones = dict(prev["backbones"])
                prev_default = prev.get("meta", {}).get("default_backbone")
        except Exception:
            pass

    for name in wanted:
        print(f"[{name}] building ...")
        payload = build_backbone(name)
        if payload is not None:
            backbones[name] = payload
        elif name in backbones:
            print(f"  [{name}] build failed; keeping previously committed data.")

    if not backbones:
        print("No backbone could be built (check API keys / network). Nothing written.")
        sys.exit(1)

    default = (prev_default if prev_default in backbones
               else "pce" if "pce" in backbones else next(iter(backbones)))
    # Stable order: US gauges first, then the country ports, then anything else.
    KNOWN = ("pce", "cpi", "uk", "fr", "de", "jp")
    order = [b for b in KNOWN if b in backbones] + \
            [b for b in backbones if b not in KNOWN]
    out = {
        "meta": {
            "schema": 3,
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "ar_orders": list(AR_ORDERS), "schemes": list(SCHEMES),
            "ui": UI_PARAMS,
            "baseline": f"AR{BASELINE['ar']}|k{BASELINE['k']}|{BASELINE['scheme']}",
            "paper": "Lansing & Shapiro (2026), FRBSF WP 2026-10",
            "default_backbone": default,
            "backbones": order,
        },
        "backbones": {b: backbones[b] for b in order},
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    months = max(len(b["dates"]) for b in backbones.values())
    print(f"wrote {dest} ({dest.stat().st_size/1024:.0f} KB; backbones: "
          f"{', '.join(order)}; up to {months} months)")


if __name__ == "__main__":
    main()
