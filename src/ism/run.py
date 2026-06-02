"""
ism.run  --  command-line orchestrator for the replication.

Usage (run from the repo root, with .env containing the API keys):

    # after `pip install -e .` you get the `ism` command:
    ism fetch       # download BEA category tables + FRED controls (caches to data/raw)
    ism index       # build category panel -> compute ISM -> save + validate vs author
    ism table1      # in-sample forecast regressions (Table 1)
    ism figures     # Figure 1 + convergence overlay
    ism all         # everything end-to-end

    # without installing, run the script directly (it self-adds src/ to the path):
    python src/ism/run.py all

Each step caches its inputs/outputs so re-runs are cheap and auditable. The
fetch step needs network access to BEA/FRED (run it where those hosts are
reachable; this project's sandbox blocks them).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python src/ism/run.py` as well as `python -m ism.run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass

from ism.datasources import BeaClient, FredClient, REPO_ROOT
from ism.engine import ISMConfig, compute_ism
from ism import pipeline, controls as controls_mod, validate, forecasting, figures


PROC = REPO_ROOT / "data" / "processed"


def cmd_fetch():
    """Download + cache raw inputs."""
    bea = BeaClient()
    print("[fetch] BEA price table U20404 ...")
    bea.table("U20404")
    print("[fetch] BEA nominal table U20405 ...")
    bea.table("U20405")
    print("[fetch] FRED controls ...")
    controls_mod.build_controls(FredClient()).to_parquet(PROC / "controls.parquet")
    print("[fetch] done. Raw caches + provenance under data/raw/.")


def _load_or_build_panel():
    inf_p = PROC / "category_inflation.parquet"
    w_p = PROC / "category_weights.parquet"
    if inf_p.exists() and w_p.exists():
        return pd.read_parquet(inf_p), pd.read_parquet(w_p)
    infl, w = pipeline.build_category_panel()
    pipeline.save_panel(infl, w)
    return infl, w


def cmd_index(cfg: ISMConfig | None = None):
    infl, w = _load_or_build_panel()
    cfg = cfg or ISMConfig()  # AR(1), W=120, K=3
    result = compute_ism(infl, w, cfg)
    out = result.to_frame()
    PROC.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROC / "ism_index_replicated.csv")
    print("[index] computed ISM. Convergence vs author ground truth:")
    rep = validate.convergence_report(result)
    print(rep.to_string())
    rep.to_csv(REPO_ROOT / "outputs" / "convergence_report.csv")
    return result


def cmd_table1():
    result = cmd_index()
    ctrl = pd.read_parquet(PROC / "controls.parquet") if (PROC / "controls.parquet").exists() else None
    pce_yoy = ctrl["pce_yoy"] if ctrl is not None else None
    if pce_yoy is None:
        print("[table1] controls/PCE not available; run fetch first.")
        return
    tbl = forecasting.table1(pce_yoy, result.ism, result.s_pos, result.s_neg, controls=ctrl)
    tbl.to_csv(REPO_ROOT / "outputs" / "table1_replicated.csv", index=False)
    print(tbl.to_string(index=False))


def cmd_figures():
    result = cmd_index()
    ctrl_path = PROC / "controls.parquet"
    pce_yoy = pd.read_parquet(ctrl_path)["pce_yoy"] if ctrl_path.exists() else None
    p1 = figures.figure1(result.ism, result.s_pos, result.s_neg, pce_yoy)
    p2 = validate.overlay_chart(result)
    print(f"[figures] wrote {p1} and {p2}")


def main(argv=None):
    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else "all"
    if cmd == "fetch":
        cmd_fetch()
    elif cmd == "index":
        cmd_index()
    elif cmd == "table1":
        cmd_table1()
    elif cmd == "figures":
        cmd_figures()
    elif cmd == "all":
        cmd_fetch(); cmd_table1(); cmd_figures()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
