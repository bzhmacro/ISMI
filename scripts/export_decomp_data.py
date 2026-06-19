"""
export_decomp_data.py
=====================

Export the RAW category panels (log price, log quantity, MoM inflation, nominal
expenditure shares) for the supply/demand decomposition (Shapiro 2022-18), for
the PCE backbone at two scopes -- headline and core -- plus one precomputed
baseline combo, into the compact JSON the static website consumes:

    web/data/decomp.json

The website recomputes the decomposition CLIENT-SIDE (web/decomp_engine.js, a
parity-tested port of src/ism/decomp_engine.py), so users can vary the VAR lag
order J, the rolling window W, the precision cut-off (binary vs ambiguous), the
scope (headline/core) and category exclusions continuously, and switch between
the contributions view (Eq. 15) and the shares view (Eq. 14).

Output schema (decomp v1)::

    { "meta": {schema, generated_utc, model, paper, ui, default_scope, scopes},
      "scopes": {
        "headline": { label, source_note, n_categories, note, dates, categories,
                      panel:{logp,logq,infl,w}, baseline:{contrib,shares,drivers},
                      author:{monthly,yoy} | null, headline_yoy },
        "core":     { ... } } }

The PCE panels self-fetch the BEA tables via BeaClient (cached): 2.4.4U (price),
2.4.3U (real quantity), 2.4.5U (nominal). If the real-quantity table U20403 is
unreachable, pass `--proxy` to derive a real-expenditure stand-in (nominal /
price); the JSON is then flagged as DEMO so the site shows a banner.

    python scripts/export_decomp_data.py                 # headline + core (needs BEA, incl. U20403)
    python scripts/export_decomp_data.py --proxy         # dev: quantity = nominal/price
    python scripts/export_decomp_data.py headline        # one scope
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

from ism.decomp_engine import (DecompConfig, rolling_var_residuals,            # noqa: E402
                               classify_labels, contributions, shock_shares,
                               yoy_contribution)
from ism.decomp_pipeline import (bea_wide, load_categories, core_exclusions,   # noqa: E402
                                 build_decomp_panels)
from ism.datasources import BeaClient, FredClient                              # noqa: E402
from ism.transforms import monthly_inflation, yoy_inflation                    # noqa: E402
from ism.decomp_validate import load_frbsf_author                             # noqa: E402

PANEL_DP = 6
ROUND = 5
BASELINE = dict(J=12, W=120, precision_cut=0.0)
UI_PARAMS = {
    "var_lags": [3, 12, 24],
    "window": {"min": 60, "max": 240, "step": 6, "default": 120},
    "precision_cut": {"min": 0.0, "max": 0.3, "step": 0.05, "default": 0.0},
    "views": ["contrib_yoy", "contrib_monthly", "shares"],
}


def _cols(df):
    out = []
    for c in df.columns:
        v = df[c].to_numpy(dtype=float)
        out.append([None if not np.isfinite(x) else round(float(x), PANEL_DP) for x in v])
    return out


def _ser(s, index):
    s = s.reindex(index)
    return [None if pd.isna(v) else round(float(v), ROUND) for v in s.to_numpy()]


def build_panels(scope, proxy=False):
    """Return (logp, logq, infl, weights, categories) for a scope.

    Uses the pipeline (BEA U20403/04/05). With proxy=True, derive quantity as
    nominal/price from the cached price & nominal tables (dev stand-in)."""
    if not proxy:
        p = build_decomp_panels(scope=scope, spec="levels", inflation_method="pct")
        return p.log_price, p.log_quantity, p.inflation, p.weights, p.categories

    bea = BeaClient()
    price = bea_wide(bea, "U20404")
    nominal = bea_wide(bea, "U20405")
    cats = load_categories()
    label_by_key = dict(zip(cats["key"].astype(str), cats["label"].astype(str)))
    keys = [k for k in cats["key"].astype(str) if k in price.columns and k in nominal.columns]
    if scope == "core":
        keys = [k for k in keys if k not in core_exclusions()]
    p = price[keys].astype(float)
    nom = nominal[keys].astype(float)
    q = nom / p                                   # real-expenditure proxy
    infl = monthly_inflation(p, method="pct")
    w = nom.div(nom.sum(axis=1).replace(0, np.nan), axis=0)
    common = p.index
    logp, logq = np.log(p), np.log(q)
    categories = [(k, label_by_key.get(k, k)) for k in keys]
    return logp.loc[common], logq.loc[common], infl.loc[common], w.loc[common], categories


def compute_baseline(logp, logq, infl, w):
    """Precompute the BASELINE combo (J=12, W=120, binary) for instant paint."""
    cfg = DecompConfig(var_lags=BASELINE["J"], window=BASELINE["W"],
                       precision_cut=BASELINE["precision_cut"])
    rp, rq = rolling_var_residuals(logp, logq, cfg)
    lab = classify_labels(rp, rq, cfg)
    contrib = contributions(infl, w, lab)
    yoy = yoy_contribution(contrib[["supply", "demand", "ambiguous", "total"]])
    shares = shock_shares(lab, w)
    index = logp.index

    # sparse latest-month drivers (category contribution to the supply/demand split)
    wlag = w.shift(1)
    cc = (wlag * infl)
    net = lab.supply.fillna(0) - lab.demand.fillna(0)
    contrib_cat = (cc * net)
    valid = contrib.dropna().index
    drivers = {}
    if len(valid):
        for d in valid[-22:]:
            row = contrib_cat.loc[d]
            items = [[i, round(float(v), ROUND)] for i, v in enumerate(row.to_numpy())
                     if np.isfinite(v) and abs(v) > 1e-6]
            items.sort(key=lambda p: -abs(p[1]))
            drivers[d.strftime("%Y-%m")] = items

    return {
        "contrib": {k: _ser(contrib[k], index) for k in ["supply", "demand", "ambiguous", "total"]},
        "contrib_yoy": {k: _ser(yoy[k], index) for k in ["supply", "demand", "ambiguous", "total"]},
        "shares": {k: _ser(shares[k], index) for k in ["supply", "demand", "ambiguous"]},
        "drivers": drivers,
    }


def build_scope(scope, proxy=False):
    try:
        logp, logq, infl, w, categories = build_panels(scope, proxy=proxy)
    except Exception as exc:
        print(f"  [{scope}] skipped: {type(exc).__name__}: {exc}")
        return None

    logp = logp.round(PANEL_DP); logq = logq.round(PANEL_DP)
    infl = infl.round(PANEL_DP); w = w.round(PANEL_DP)
    index = logp.index
    print(f"  [{scope}] {logp.shape[1]} categories, {logp.shape[0]} months"
          + (" (PROXY quantity)" if proxy else ""))

    # FRBSF published author overlay (supply/demand/ambiguous), monthly + yoy
    author = load_frbsf_author(scope=scope, index=index)

    # headline yoy inflation for context (PCEPI / core PCE)
    try:
        fred = FredClient()
        sid = "PCEPILFE" if scope == "core" else "PCEPI"
        s = fred.series(sid)
        s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
        headline_yoy = _ser(yoy_inflation(s), index)
    except Exception:
        headline_yoy = None

    return {
        "label": f"PCE ({scope})",
        "source_note": "BEA Underlying Detail 2.4.3U / 2.4.4U / 2.4.5U"
                       + (" (quantity = nominal/price proxy)" if proxy else ""),
        "n_categories": int(logp.shape[1]),
        "note": ("DEMO: quantity proxied as nominal/price; rerun the exporter "
                 "with BEA table U20403 for the exact series." if proxy else
                 "Decomposition computed in the browser from BEA underlying detail."),
        "dates": [d.strftime("%Y-%m") for d in index],
        "categories": [{"key": k, "label": lab} for k, lab in categories],
        # infl is derived in the browser from logp (price = exp(logp)), so the
        # payload ships only logp, logq and w.
        "panel": {"logp": _cols(logp), "logq": _cols(logq), "w": _cols(w)},
        "baseline": compute_baseline(logp, logq, infl, w),
        "author": author,
        "headline_yoy": headline_yoy,
    }


def main(argv=None):
    argv = argv or sys.argv[1:]
    proxy = "--proxy" in argv
    argv = [a for a in argv if not a.startswith("-")]
    wanted = [a.lower() for a in argv] or ["headline", "core"]

    dest = ROOT / "web" / "data" / "decomp.json"
    scopes, prev_default = {}, None
    if dest.exists():
        try:
            prev = json.loads(dest.read_text())
            scopes = dict(prev.get("scopes", {}))
            prev_default = prev.get("meta", {}).get("default_scope")
        except Exception:
            pass

    for scope in wanted:
        print(f"[{scope}] building ...")
        payload = build_scope(scope, proxy=proxy)
        if payload is not None:
            scopes[scope] = payload
        elif scope in scopes:
            print(f"  [{scope}] build failed; keeping previously committed data.")

    if not scopes:
        print("No scope could be built (check BEA key / network). Nothing written.")
        sys.exit(1)

    order = [s for s in ("headline", "core") if s in scopes]
    default = prev_default if prev_default in scopes else order[0]
    out = {
        "meta": {
            "schema": 1, "model": "decomp",
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "paper": "Shapiro (2024), FRBSF WP 2022-18 — Decomposing Supply and Demand Driven Inflation",
            "ui": UI_PARAMS,
            "baseline": f"J{BASELINE['J']}|W{BASELINE['W']}|binary",
            "demo": proxy,
            "default_scope": default, "scopes": order,
        },
        "scopes": {s: scopes[s] for s in order},
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    months = max(len(s["dates"]) for s in scopes.values())
    print(f"wrote {dest} ({dest.stat().st_size/1024:.0f} KB; scopes: "
          f"{', '.join(order)}; up to {months} months)")


if __name__ == "__main__":
    main()
