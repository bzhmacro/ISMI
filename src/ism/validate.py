"""
ism.validate
============

Convergence checks: compare a computed ISM result against the author-provided
ground truth (data/raw/ISM_public_author.xlsx) and report correlation, RMSE,
mean absolute error, and max absolute deviation for each of ISM, S+ and S-.

This is the quantitative answer to "did we replicate the index?". It also writes
an overlay chart so divergence is visible by eye.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT


AUTHOR_FILE = REPO_ROOT / "data" / "raw" / "ISM_public_author.xlsx"
AUTHOR_COLS = {
    "ISM Index": "ISM",
    "Positive Momentum Component": "S_pos",
    "Negative Momentum Component": "S_neg",
}


def load_author_truth(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the author's ISM_public.xlsx as a monthly DataFrame [ISM, S_pos, S_neg]."""
    path = path or AUTHOR_FILE
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    # time_month like '1969m1' -> Timestamp('1969-01-01').
    months = (
        df["time_month"].astype(str).str.strip().str.replace("m", "-", regex=False)
    )
    idx = pd.to_datetime(months + "-01", format="%Y-%m-%d", errors="coerce")
    out = df[list(AUTHOR_COLS)].rename(columns=AUTHOR_COLS)
    out.index = idx
    out.index.name = "date"
    return out


def compare_series(ours: pd.Series, truth: pd.Series) -> dict:
    """Alignment-aware comparison stats between two monthly series."""
    j = pd.concat([ours.rename("ours"), truth.rename("truth")], axis=1).dropna()
    if j.empty:
        return {"n": 0}
    d = j["ours"] - j["truth"]
    return {
        "n": int(len(j)),
        "corr": float(j["ours"].corr(j["truth"])),
        "rmse": float(np.sqrt((d**2).mean())),
        "mae": float(d.abs().mean()),
        "max_abs": float(d.abs().max()),
        "mean_bias": float(d.mean()),
    }


def convergence_report(result, truth: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Full convergence table comparing an ISMResult to author truth.

    Parameters
    ----------
    result : ism.engine.ISMResult (has .ism, .s_pos, .s_neg)
    truth  : optional pre-loaded author frame; otherwise loaded from disk.

    Returns a DataFrame indexed by series name with the comparison stats.
    """
    truth = truth if truth is not None else load_author_truth()
    rows = {
        "ISM": compare_series(result.ism, truth["ISM"]),
        "S_pos": compare_series(result.s_pos, truth["S_pos"]),
        "S_neg": compare_series(result.s_neg, truth["S_neg"]),
    }
    return pd.DataFrame(rows).T


def overlay_chart(result, truth: Optional[pd.DataFrame] = None, out_path: Optional[Path] = None):
    """Plot our ISM vs the author's ISM; save PNG. Returns the path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    truth = truth if truth is not None else load_author_truth()
    out_path = out_path or (REPO_ROOT / "outputs" / "convergence_ISM.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(truth.index, truth["ISM"], label="Author ISM (published)", lw=1.6, color="black")
    ax.plot(result.ism.index, result.ism.values, label="Replicated ISM", lw=1.1, color="tab:red", alpha=0.8)
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_title("ISM index: replication vs. author ground truth")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path
