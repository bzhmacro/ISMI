"""
export_trim_data.py
===================

Export everything the trimmed-mean and CPI-to-PCE pages need into
``web/data/trim.json``.

Like the other two models, the website recomputes **client-side**: the payload
ships the raw seasonally adjusted category panels and the versioned weight
panels, and ``web/trim_worker.js`` (running ``web/trim_engine.js``, a
parity-tested port of ``src/ism/trim_engine.py``) re-trims the cross-section
whenever a control moves.  That is what makes the trim fractions, the weight
vintage and the category set *live* rather than a set of pre-baked lines.

Output schema (v1)::

    { "meta":   { schema, generated_utc, default_scope, scopes, ui, sources },
      "scopes": { "<key>": { label, tab, source_note, weight_note, notes, sa,
                             ppy, dates, categories, panel {inflation, weights},
                             weights_source, official, headline, baseline,
                             validation } },
      "cpipce": { dates, table, groups, bridge, notes } }

    python scripts/export_trim_data.py                 # everything
    python scripts/export_trim_data.py cpi45 pce       # selected scopes
    python scripts/export_trim_data.py --no-cpipce     # skip the bridge page

The CPI scopes self-fetch from the BLS flat files (no key, no daily cap); PCE
reads the panels already committed in ``web/data/ism.json`` unless ``BEA_API_KEY``
is set.  A scope that fails to build is skipped with a warning rather than
aborting the export -- the site hides any scope that is absent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from ism.cpi_pce import (bridge_nowcast, gap_decomposition,  # noqa: E402
                         load_concordance)
from ism.trim_engine import (MEDIAN_CPI, TRIM16_CPI, TRIM_PCE,  # noqa: E402
                             TrimConfig, compute_trim)
from ism.trim_pipeline import (build_cleveland_panel, build_cpi70_panel,  # noqa: E402
                               build_pce_panel, panel_from_web_data)
from ism.trim_validate import compare_to_official, official_series  # noqa: E402

OUT = ROOT / "web" / "data" / "trim.json"
ISM_JSON = ROOT / "web" / "data" / "ism.json"

PANEL_DP = 6          # decimals kept for the shipped panels
SERIES_DP = 4

ALL_SCOPES = ("cpi45", "cpi70", "pce", "uk", "fr", "de", "jp", "ca")
DEFAULT_SCOPES = ("cpi45", "cpi70", "pce")

TABS = {"cpi45": "US CPI (Cleveland cut)", "cpi70": "US CPI (70 strata)",
        "pce": "US PCE", "uk": "UK", "fr": "France", "de": "Germany",
        "jp": "Japan", "ca": "Canada"}

MEASURES = {"median": MEDIAN_CPI, "trim16": TRIM16_CPI, "trim_pce": TRIM_PCE}

UI = {
    "lower": {"min": 0, "max": 0.5, "step": 0.01, "default": 0.08},
    "upper": {"min": 0, "max": 0.5, "step": 0.01, "default": 0.08},
    "presets": {
        "median": {"lower": 0.5, "upper": 0.5,
                   "label": "Median (Cleveland)"},
        "trim16": {"lower": 0.08, "upper": 0.08,
                   "label": "16% trim (Cleveland)"},
        "trim_pce": {"lower": 0.24, "upper": 0.31,
                     "label": "24/31 trim (Dallas)"},
    },
    "sa_methods": ["none", "rolling", "dummy"],
    "weight_vintages": ["versioned", "latest", "first"],
    "horizons": [1, 3, 6, 12],
}

SOURCES = {
    "cleveland": "https://www.clevelandfed.org/indicators-and-data/median-cpi",
    "dallas": "https://www.dallasfed.org/research/pce",
    "bls_flat": "https://download.bls.gov/pub/time.series/cu/",
    "bls_ri": "https://www.bls.gov/cpi/tables/relative-importance/home.htm",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _round(v, dp):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, dp)


def _series(s: pd.Series, index: pd.Index, dp: int = SERIES_DP) -> list:
    s = s.reindex(index)
    return [_round(v, dp) for v in s.to_numpy()]


def _panel(df: pd.DataFrame, index: pd.Index, keys: list[str], dp: int) -> list[list]:
    df = df.reindex(index=index, columns=keys)
    return [[_round(v, dp) for v in df[k].to_numpy()] for k in keys]


def _dates(index: pd.Index) -> list[str]:
    return [d.strftime("%Y-%m") for d in pd.DatetimeIndex(index)]


def load_ism_payload() -> dict:
    if not ISM_JSON.exists():
        raise SystemExit(f"{ISM_JSON} not found; run scripts/export_web_data.py first")
    return json.loads(ISM_JSON.read_text())


# ---------------------------------------------------------------------------
# scopes
# ---------------------------------------------------------------------------
def build_panel(scope: str, ism_payload: dict, force: bool = False):
    if scope == "cpi45":
        return build_cleveland_panel(force=force)
    if scope == "cpi70":
        return build_cpi70_panel(force=force)
    if scope == "pce":
        if os.environ.get("BEA_API_KEY"):
            return build_pce_panel(force=force)
        base = panel_from_web_data(ism_payload, "pce", sa="none")
        return build_pce_panel(inflation_panel=base.inflation,
                               weights=base.weights, labels=base.labels)
    return panel_from_web_data(ism_payload, scope)


def headline_for(scope: str, ism_payload: dict, index: pd.Index):
    """The published 12-month rate to draw behind the trimmed mean."""
    backbone = {"cpi45": "cpi", "cpi70": "cpi"}.get(scope, scope)
    block = (ism_payload.get("backbones") or {}).get(backbone)
    if not block:
        return None
    idx = pd.to_datetime([d + "-01" for d in block["dates"]])
    s = pd.Series(block["headline"]["series"], index=idx, dtype=float)
    return {"label": block["headline"].get("label", "headline inflation (12m, %)"),
            "series": _series(s, index)}


def official_for(scope: str, official: dict, index: pd.Index):
    """The published limited-influence series that belong on this scope's chart."""
    out = {}
    if scope.startswith("cpi"):
        cle = official.get("cleveland")
        if cle is not None:
            out["median"] = {
                "label": "Cleveland Fed median CPI",
                "rate": _series(cle["median_saar"], index),
                "yoy": _series(cle["median_yoy"], index),
            }
            out["trim16"] = {
                "label": "Cleveland Fed 16% trimmed-mean CPI",
                "rate": _series(cle["trim16_saar"], index),
                "yoy": _series(cle["trim16_yoy"], index),
            }
    if scope == "pce":
        dal = official.get("dallas")
        if dal is not None:
            out["trim_pce"] = {
                "label": "Dallas Fed trimmed mean PCE",
                "rate": _series(dal["m1"], index),
                "yoy": _series(dal["m12"], index),
            }
    return out


def export_scope(scope: str, panel, official: dict, ism_payload: dict) -> dict:
    index = panel.inflation.index
    keys = list(panel.inflation.columns)
    groups = {}
    if scope == "cpi45":
        from ism.trim_pipeline import load_cleveland_components
        comp = load_cleveland_components()
        groups = dict(zip(comp["key"], comp["group"]))

    block = {
        "label": panel.label,
        "tab": TABS.get(scope, scope),
        "source_note": panel.source_note,
        "weight_note": panel.weight_note,
        "notes": list(panel.notes),
        "sa": panel.sa,
        "ppy": panel.periods_per_year,
        "n_categories": len(keys),
        "dates": _dates(index),
        "categories": [{"key": k, "label": panel.labels.get(k, k),
                        "group": groups.get(k, "")} for k in keys],
        "panel": {
            "inflation": _panel(panel.inflation, index, keys, PANEL_DP),
            "weights": _panel(panel.weights, index, keys, 8),
        },
    }
    if panel.weights_source is not None:
        block["weights_source"] = list(panel.weights_source.reindex(index)
                                       .fillna("").astype(str))

    head = headline_for(scope, ism_payload, index)
    if head:
        block["headline"] = head
    block["official"] = official_for(scope, official, index)

    # One precomputed combo per measure, for an instant first paint before the
    # worker has booted.
    baseline = {}
    for name, base in MEASURES.items():
        cfg = TrimConfig(lower=base.lower, upper=base.upper, sa=panel.sa,
                         periods_per_year=panel.periods_per_year)
        res = compute_trim(panel.inflation, panel.weights, cfg)
        baseline[name] = {"lower": base.lower, "upper": base.upper,
                          "rate": _series(res.rate, index),
                          "yoy": _series(res.yoy, index),
                          "n": [int(v) for v in res.n_categories.reindex(index)
                                .fillna(0).to_numpy()]}
    block["baseline"] = baseline

    rep = compare_to_official(panel, MEASURES, official)
    block["validation"] = ([] if rep.empty else
                           [{k: (_round(v, 4) if isinstance(v, float) else v)
                             for k, v in row.items()}
                            for row in rep.to_dict("records")])
    return block


# ---------------------------------------------------------------------------
# the CPI -> PCE page
# ---------------------------------------------------------------------------
def export_cpipce(panels: dict, ism_payload: dict) -> dict | None:
    cpi = panels.get("cpi70") or panels.get("cpi45")
    pce = panels.get("pce")
    if cpi is None or pce is None:
        print("[export_trim] cpipce: needs a CPI scope and PCE; skipped")
        return None

    block = ism_payload["backbones"]["pce"]
    pce_pub = pd.Series(block["headline"]["series"],
                        index=pd.to_datetime([d + "-01" for d in block["dates"]]),
                        dtype=float)

    conc = load_concordance()
    gap = gap_decomposition(cpi.inflation, cpi.weights, pce.inflation,
                            pce.weights, conc=conc, pce_published=pce_pub)
    err = gap.check()
    print(f"[export_trim] cpipce: identity closes to {err:.2e}")
    if err > 1e-6:
        print("[export_trim] WARNING the decomposition identity does not close")

    bridge = bridge_nowcast(cpi.inflation, cpi.weights, pce.inflation,
                            pce.weights, conc=conc)
    print(f"[export_trim] cpipce: bridge RMSE {bridge.rmse:.3f}pp (m/m), "
          f"window {bridge.window}")

    table = gap.table.dropna(subset=["gap"])
    index = table.index
    cols = ["cpi", "pce", "gap"] + list(gap.COMPONENTS) + ["ccpi_proxy"]

    lab_cpi = (conc[conc.gauge == "cpi"].groupby("group")["label"]
               .apply(lambda s: "; ".join(s.head(4))).to_dict())
    lab_pce = (conc[conc.gauge == "pce"].groupby("group")["label"]
               .apply(lambda s: "; ".join(s.head(4))).to_dict())
    roles = conc.drop_duplicates("group").set_index("group")["role"].to_dict()

    last_w_cpi = gap.weights_cpi.reindex(index).ffill().iloc[-1]
    last_w_pce = gap.weights_pce.reindex(index).ffill().iloc[-1]
    slopes = bridge.coefficients.reindex(index)
    last_slope = slopes.ffill().iloc[-1] if len(slopes) else pd.Series(dtype=float)

    groups = []
    for g in sorted(set(gap.group_cpi.columns) | set(gap.group_pce.columns)):
        groups.append({
            "group": g,
            "role": "common" if g in gap.common else "scope",
            "cpi_members": lab_cpi.get(g, ""),
            "pce_members": lab_pce.get(g, ""),
            "w_cpi": _round(100 * last_w_cpi.get(g, np.nan), 3),
            "w_pce": _round(100 * last_w_pce.get(g, np.nan), 3),
            "slope": _round(last_slope.get(g, np.nan), 3),
            "cpi_yoy": _series(gap.group_cpi[g].rolling(12, min_periods=12).sum(),
                               index) if g in gap.group_cpi else None,
            "pce_yoy": _series(gap.group_pce[g].rolling(12, min_periods=12).sum(),
                               index) if g in gap.group_pce else None,
        })

    contrib = bridge.contributions
    return {
        "dates": _dates(index),
        # 5 dp, not the usual 4: the six components have to still sum to the
        # gap after rounding, and validate_web_data.py checks that they do.
        "table": {c: _series(table[c], index, 5) for c in cols},
        "components": list(gap.COMPONENTS),
        "groups": groups,
        "roles": roles,
        "bridge": {
            "window": bridge.window,
            "rmse": _round(bridge.rmse, 4),
            "monthly": {"implied": _series(bridge.monthly["implied"], index),
                        "actual": _series(bridge.monthly["actual"], index)},
            "yoy": {"implied": _series(bridge.yoy["implied"], index),
                    "actual": _series(bridge.yoy["actual"], index)},
            "latest_month": contrib.attrs.get("month") if len(contrib) else None,
            "contributions": ([] if contrib.empty else
                              [{"group": r["group"], "role": r["role"],
                                "implied_rate": _round(r["implied_rate"], 4),
                                "weight": _round(r["weight"], 5),
                                "contribution": _round(r["contribution"], 5)}
                               for r in contrib.to_dict("records")]),
        },
        "notes": list(gap.notes),
        "cpi_scope": cpi.key,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scopes", nargs="*", default=list(DEFAULT_SCOPES),
                    help=f"scopes to export (default: {' '.join(DEFAULT_SCOPES)}; "
                         f"available: {' '.join(ALL_SCOPES)})")
    ap.add_argument("--no-cpipce", action="store_true",
                    help="skip the CPI-to-PCE page")
    ap.add_argument("--force", action="store_true", help="bypass download caches")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    ism_payload = load_ism_payload()
    official = official_series(force=args.force)

    panels, scopes = {}, {}
    for scope in args.scopes:
        try:
            panel = build_panel(scope, ism_payload, force=args.force)
            panels[scope] = panel
            scopes[scope] = export_scope(scope, panel, official, ism_payload)
            v = scopes[scope]["validation"]
            best = ", ".join(f"{r['measure']}/{r['horizon']} corr {r['corr']:.3f}"
                             for r in v) or "no published counterpart"
            print(f"[export_trim] {scope}: {panel.n_categories} categories, "
                  f"{scopes[scope]['dates'][0]}..{scopes[scope]['dates'][-1]} "
                  f"({best})")
        except Exception as exc:
            print(f"[export_trim] {scope}: SKIPPED ({exc})")
            traceback.print_exc(limit=2)

    if not scopes:
        raise SystemExit("[export_trim] no scope built; nothing written")

    payload = {
        "meta": {
            "schema": 1,
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "default_scope": "cpi45" if "cpi45" in scopes else list(scopes)[0],
            "scopes": list(scopes),
            "ui": UI,
            "sources": SOURCES,
        },
        "scopes": scopes,
    }

    if not args.no_cpipce:
        cpipce = export_cpipce(panels, ism_payload)
        if cpipce:
            payload["cpipce"] = cpipce

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    mb = args.out.stat().st_size / 1e6
    print(f"[export_trim] wrote {args.out} ({mb:.1f} MB, "
          f"{len(scopes)} scopes{', + cpipce' if 'cpipce' in payload else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
