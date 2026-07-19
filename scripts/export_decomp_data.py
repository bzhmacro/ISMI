"""
export_decomp_data.py
=====================

Export the RAW category panels (log price, log quantity, MoM inflation, nominal
expenditure shares) for the supply/demand decomposition (Shapiro 2022-18), for
several scopes -- the US PCE backbone (headline, core, goods, services; monthly)
and the Bank of Canada quarterly HCE port (ca, ca_goods, ca_services) -- plus one
precomputed baseline combo per scope, into the compact JSON the static website
consumes:

    web/data/decomp.json

The website recomputes the decomposition CLIENT-SIDE (web/decomp_engine.js, a
parity-tested port of src/ism/decomp_engine.py), so users can vary the VAR lag
order J, the rolling window W, the precision cut-off (binary vs ambiguous), the
scope and category exclusions continuously, and switch between the contributions
view (Eq. 15) and the shares view (Eq. 14). Each scope carries its own frequency
(periods_per_year: 12 monthly for the US, 4 quarterly for Canada) and baseline
parameters, so the browser uses the right y/y horizon and defaults per scope.

Output schema (decomp v2)::

    { "meta": {schema, generated_utc, model, paper, ui, default_scope, scopes},
      "scopes": {
        "headline": { label, tab, source_note, n_categories, note, dates,
                      categories, ppy, baseline_params:{J,W}, ui:{var_lags,window},
                      panel:{logp,logq,w}, baseline:{contrib,shares,drivers},
                      author:{monthly,yoy} | null, headline_yoy },
        "core": {...}, "ca": {...}, "ca_goods": {...}, "ca_services": {...} } }

The US PCE panels self-fetch the BEA tables via BeaClient (cached): 2.4.4U
(price), 2.4.3U (real quantity), 2.4.5U (nominal). If the real-quantity table
U20403 is unreachable, pass `--proxy` to derive a real-expenditure stand-in
(nominal / price); the JSON is then flagged as DEMO so the site shows a banner.
The Canada panels self-fetch StatCan 36-10-0124 via StatCanClient (cached under
data/raw/statcan/; rebuild with `python scripts/fetch_statcan.py`). Any scope
whose data is unreachable is skipped, and the previously committed data kept.

    python scripts/export_decomp_data.py                 # all scopes it can build
    python scripts/export_decomp_data.py --proxy         # dev: US quantity = nominal/price
    python scripts/export_decomp_data.py headline        # one scope
    python scripts/export_decomp_data.py ca ca_goods     # only the Canada scopes
    python scripts/export_decomp_data.py uk fr de jp     # the UK / France / Germany / Japan ports
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

# Load .env so provider keys (ESTAT_API_ID, DESTATIS_API_TOKEN/KEY, …) are
# available to the self-fetching country scopes without an explicit `export`.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

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

# Monthly (US PCE) UI defaults and quarterly (Canada HCE) UI defaults.
UI_PARAMS = {
    "var_lags": [3, 12, 24],
    "window": {"min": 60, "max": 240, "step": 6, "default": 120},
    "precision_cut": {"min": 0.0, "max": 0.3, "step": 0.05, "default": 0.0},
    "views": ["contrib_yoy", "contrib_monthly", "shares"],
}
UI_QUARTERLY = {
    "var_lags": [4, 8, 12],
    "window": {"min": 20, "max": 80, "step": 4, "default": 40},
}

# ---------------------------------------------------------------------------
# Scope registry: one entry per selectable scope, US (monthly) + Canada (q).
# baseline = the precomputed combo the site paints instantly (Shapiro/BoC
# working-paper defaults); ppy = periods per year (12 monthly, 4 quarterly).
# ---------------------------------------------------------------------------
SCOPES = {
    "headline":    dict(country="us", tab="US headline", ppy=12, J=12, W=120,
                        ui=UI_PARAMS),
    "core":        dict(country="us", tab="US core",     ppy=12, J=12, W=120,
                        ui=UI_PARAMS),
    "goods":       dict(country="us", tab="US goods",    ppy=12, J=12, W=120,
                        ui=UI_PARAMS),
    "services":    dict(country="us", tab="US services", ppy=12, J=12, W=120,
                        ui=UI_PARAMS),
    "ca":          dict(country="ca", tab="Canada",          ppy=4, J=4, W=40,
                        ca_scope="total",    ui=UI_QUARTERLY),
    "ca_goods":    dict(country="ca", tab="Canada goods",    ppy=4, J=4, W=40,
                        ca_scope="goods",    ui=UI_QUARTERLY),
    "ca_services": dict(country="ca", tab="Canada services", ppy=4, J=4, W=40,
                        ca_scope="services", ui=UI_QUARTERLY),
    "uk":          dict(country="uk", tab="UK",      ppy=4, J=4, W=40, ui=UI_QUARTERLY),
    "fr":          dict(country="fr", tab="France",  ppy=4, J=4, W=40, ui=UI_QUARTERLY),
    "de":          dict(country="de", tab="Germany", ppy=4, J=4, W=40, ui=UI_QUARTERLY),
    "jp":          dict(country="jp", tab="Japan",   ppy=4, J=4, W=40, ui=UI_QUARTERLY),
}
DEFAULT_ORDER = list(SCOPES.keys())

# Display metadata for the quarterly national-accounts country ports
# (label, source_note, note). Canada is handled separately (total/goods/services).
COUNTRY_META = {
    "uk": ("UK PCE",
           "ONS Consumer Trends quarterly household final consumption expenditure "
           "by COICOP (ct.csv, current prices + chained volumes, SA)",
           "Decomposition computed in the browser from ONS Consumer Trends quarterly "
           "HCE (COICOP class leaves): reduced-form VAR of log price & log quantity "
           "on 4 lags over a 40-quarter window. No published author overlay."),
    "fr": ("France PCE",
           "INSEE quarterly national accounts, household consumption by product "
           "(~40 products from the 'par produit' tables; values + chained volumes, "
           "SA-WDA; A17 ~17-product fallback when the detailed source is offline)",
           "Decomposition computed in the browser from INSEE quarterly national-"
           "accounts consumption by product: reduced-form VAR of log price & log "
           "quantity on 4 lags over a 40-quarter window. No published author overlay."),
    "de": ("Germany PCE",
           "Eurostat quarterly national accounts, household consumption by "
           "durability (namq_10_fcs, SCA, nominal + chain-linked real)",
           "Decomposition computed in the browser from Eurostat's quarterly "
           "household consumption by durability (four categories: durable / semi-"
           "durable / non-durable goods, services — a coarse cross-section): 4 lags "
           "over a 40-quarter window. No published author overlay."),
    "jp": ("Japan PCE",
           "Cabinet Office quarterly SNA household final consumption by type "
           "(e-Stat 四半期別GDP速報, 2020 base, SA, nominal + real chained)",
           "Decomposition computed in the browser from Japan's quarterly SNA "
           "household consumption by type (four form categories: durable / semi-"
           "durable / non-durable goods, services — a coarse cross-section): 4 lags "
           "over a 40-quarter window. No published author overlay."),
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

    US scopes (headline/core) use the BEA pipeline (U20403/04/05); with
    proxy=True quantity is derived as nominal/price. The quarterly country ports
    (ca/uk/fr/de) use ism.decomp_ports (StatCan / ONS / INSEE / Destatis)."""
    spec = SCOPES[scope]
    country = spec["country"]
    if country == "ca":
        from ism.decomp_ports import build_ca_panels
        p = build_ca_panels(scope=spec["ca_scope"], spec="levels")
        return p.log_price, p.log_quantity, p.inflation, p.weights, p.categories
    if country in ("uk", "fr", "de", "jp"):
        from ism.decomp_ports import PORTS
        p = PORTS[country](spec="levels")
        return p.log_price, p.log_quantity, p.inflation, p.weights, p.categories

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
    elif scope in ("goods", "services"):
        from ism.decomp_pipeline import goods_services_keys
        gs = set(goods_services_keys(scope))
        keys = [k for k in keys if k in gs]
    p = price[keys].astype(float)
    nom = nominal[keys].astype(float)
    q = nom / p                                   # real-expenditure proxy
    infl = monthly_inflation(p, method="pct")
    w = nom.div(nom.sum(axis=1).replace(0, np.nan), axis=0)
    common = p.index
    logp, logq = np.log(p), np.log(q)
    categories = [(k, label_by_key.get(k, k)) for k in keys]
    return logp.loc[common], logq.loc[common], infl.loc[common], w.loc[common], categories


def compute_baseline(logp, logq, infl, w, J=12, W=120, ppy=12):
    """Precompute the BASELINE combo (binary labels) for instant paint.

    (J, W, ppy) default to the monthly US baseline; pass the quarterly BoC
    baseline (4, 40, 4) for the Canada scopes so the precomputed combo matches
    the browser's default parameters and the y/y horizon is one year."""
    cfg = DecompConfig(var_lags=J, window=W, precision_cut=0.0,
                       periods_per_year=ppy)
    rp, rq = rolling_var_residuals(logp, logq, cfg)
    lab = classify_labels(rp, rq, cfg)
    contrib = contributions(infl, w, lab)
    yoy = yoy_contribution(contrib[["supply", "demand", "ambiguous", "total"]],
                           periods=ppy)
    shares = shock_shares(lab, w)
    index = logp.index

    # sparse latest-period drivers. Each item is
    #   [category, TRUE signed contribution to inflation (pp), shock (+1/-1)],
    # matching web/decomp_engine.js: the contribution keeps its real sign (effect
    # on inflation) and the shock type (supply/demand) is carried separately so
    # the UI colours by type without flipping the bar's sign.
    wlag = w.shift(1)
    cc = (wlag * infl)                                   # true per-category contribution
    net = lab.supply.fillna(0) - lab.demand.fillna(0)    # +1 supply / -1 demand / 0 neither
    valid = contrib.dropna().index
    drivers = {}
    if len(valid):
        for d in valid[-22:]:
            cc_row = cc.loc[d].to_numpy()
            net_row = net.loc[d].to_numpy()
            items = [[i, round(float(cc_row[i]), ROUND), int(net_row[i])]
                     for i in range(len(cc_row))
                     if net_row[i] != 0 and np.isfinite(cc_row[i]) and abs(cc_row[i]) > 1e-6]
            items.sort(key=lambda p: -abs(p[1]))
            drivers[d.strftime("%Y-%m")] = items

    return {
        "contrib": {k: _ser(contrib[k], index) for k in ["supply", "demand", "ambiguous", "total"]},
        "contrib_yoy": {k: _ser(yoy[k], index) for k in ["supply", "demand", "ambiguous", "total"]},
        "shares": {k: _ser(shares[k], index) for k in ["supply", "demand", "ambiguous"]},
        "drivers": drivers,
    }


def build_scope(scope, proxy=False):
    spec = SCOPES[scope]
    country = spec["country"]
    is_quarterly = country != "us"
    try:
        logp, logq, infl, w, categories = build_panels(scope, proxy=proxy)
    except Exception as exc:
        print(f"  [{scope}] skipped: {type(exc).__name__}: {exc}")
        return None

    logp = logp.round(PANEL_DP); logq = logq.round(PANEL_DP)
    infl = infl.round(PANEL_DP); w = w.round(PANEL_DP)
    index = logp.index
    unit = "quarters" if is_quarterly else "months"
    print(f"  [{scope}] {logp.shape[1]} categories, {logp.shape[0]} {unit}"
          + (" (PROXY quantity)" if (proxy and not is_quarterly) else ""))

    if is_quarterly:
        # Quarterly national-accounts country ports (ca/uk/fr/de). No published
        # author overlay; the computed Total line is the reference. The dotted
        # "Published inflation" overlay is the aggregate implicit deflator's y/y
        # change, reconstructed from the panel itself.
        author = None
        headline_yoy = _ser(_aggregate_yoy(logp, w, spec["ppy"]), index)
        if country == "ca":
            label = {"total": "Canada PCE (total)", "goods": "Canada PCE (goods)",
                     "services": "Canada PCE (services)"}[spec["ca_scope"]]
            source_note = ("Statistics Canada detailed household final consumption "
                           "expenditure, quarterly (table 36-10-0124, SA, current + "
                           "2017 constant prices)")
            note = ("Decomposition computed in the browser from Statistics Canada's "
                    "quarterly HCE (Bank of Canada SAP 2026-33): reduced-form VAR of "
                    "log price & log quantity on 4 lags over a 40-quarter window. "
                    "Total = computed aggregate; no published author overlay.")
        else:
            label, source_note, note = COUNTRY_META[country]
    elif scope in ("goods", "services"):
        # US goods/services split (BEA table 2.4.5U aggregate: line < 150 = goods,
        # line >= 150 = services). FRBSF publishes only headline/core, so there is
        # no author overlay; the dotted overlay is the panel's own aggregate
        # implicit-deflator y/y change, as for the Canada goods/services scopes.
        author = None
        headline_yoy = _ser(_aggregate_yoy(logp, w, spec["ppy"]), index)
        label = f"PCE ({scope})"
        source_note = ("BEA Underlying Detail 2.4.3U / 2.4.4U / 2.4.5U, goods vs "
                       "services per BEA's PCE aggregate split (table 2.4.5U: "
                       "line < 150 = goods, line >= 150 = services)"
                       + (" (quantity = nominal/price proxy)" if proxy else ""))
        note = ("DEMO: quantity proxied as nominal/price; rerun the exporter "
                "with BEA table U20403 for the exact series." if proxy else
                "Decomposition computed in the browser from BEA underlying detail, "
                "restricted to PCE goods (or services). No published author overlay.")
    else:
        # FRBSF published author overlay (supply/demand/ambiguous), monthly + yoy
        author = load_frbsf_author(scope=scope, index=index)
        try:
            fred = FredClient()
            sid = "PCEPILFE" if scope == "core" else "PCEPI"
            s = fred.series(sid)
            s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
            headline_yoy = _ser(yoy_inflation(s), index)
        except Exception:
            headline_yoy = None
        label = f"PCE ({scope})"
        source_note = ("BEA Underlying Detail 2.4.3U / 2.4.4U / 2.4.5U"
                       + (" (quantity = nominal/price proxy)" if proxy else ""))
        note = ("DEMO: quantity proxied as nominal/price; rerun the exporter "
                "with BEA table U20403 for the exact series." if proxy else
                "Decomposition computed in the browser from BEA underlying detail.")

    return {
        "label": label,
        "tab": spec["tab"],
        "source_note": source_note,
        "n_categories": int(logp.shape[1]),
        "note": note,
        "dates": [d.strftime("%Y-%m") for d in index],
        "categories": [{"key": k, "label": lab} for k, lab in categories],
        # infl is derived in the browser from logp (price = exp(logp)), so the
        # payload ships only logp, logq and w.
        "panel": {"logp": _cols(logp), "logq": _cols(logq), "w": _cols(w)},
        "ppy": spec["ppy"],
        "baseline_params": {"J": spec["J"], "W": spec["W"]},
        "ui": spec["ui"],
        "baseline": compute_baseline(logp, logq, infl, w,
                                     J=spec["J"], W=spec["W"], ppy=spec["ppy"]),
        "author": author,
        "headline_yoy": headline_yoy,
    }


def _aggregate_yoy(logp, w, ppy):
    """Aggregate implicit-deflator y/y inflation from the category panel.

    Reconstructs the expenditure-weighted price level (Laspeyres, prior-period
    weights) and returns its year-over-year percent change -- the headline PCE
    (HCE) inflation overlay for the Canada scopes. `logp`/`w` are the rounded
    export panels; `ppy` is the periods-per-year horizon (4 for quarterly)."""
    price = np.exp(logp)
    per = price.pct_change() * 100.0                       # per-period % change
    contrib = (w.shift(1) * per).sum(axis=1, min_count=1)  # weighted aggregate
    g = 1.0 + contrib / 100.0
    prod = g.rolling(ppy, min_periods=ppy).apply(np.prod, raw=True)
    return 100.0 * (prod - 1.0)


def main(argv=None):
    argv = argv or sys.argv[1:]
    proxy = "--proxy" in argv
    argv = [a for a in argv if not a.startswith("-")]
    wanted = [a.lower() for a in argv] or list(DEFAULT_ORDER)
    unknown = [s for s in wanted if s not in SCOPES]
    if unknown:
        print(f"unknown scope(s): {', '.join(unknown)}; known: {', '.join(SCOPES)}")
        sys.exit(2)

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
        print("No scope could be built (check BEA/StatCan data & network). Nothing written.")
        sys.exit(1)

    order = [s for s in DEFAULT_ORDER if s in scopes]
    default = prev_default if prev_default in scopes else order[0]
    out = {
        "meta": {
            "schema": 2, "model": "decomp",
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "paper": "Shapiro (2024), FRBSF WP 2022-18 — Decomposing Supply and Demand Driven Inflation; "
                     "Canada: Kang, Sekkel, Taskin & Yang (2026), Bank of Canada SAP 2026-33",
            "ui": UI_PARAMS,
            "demo": proxy,
            "default_scope": default, "scopes": order,
        },
        "scopes": {s: scopes[s] for s in order},
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    periods = max(len(s["dates"]) for s in scopes.values())
    print(f"wrote {dest} ({dest.stat().st_size/1024:.0f} KB; scopes: "
          f"{', '.join(order)}; up to {periods} periods)")


if __name__ == "__main__":
    main()
