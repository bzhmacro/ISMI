"""
ism.figures
===========

Replication of the paper's charts. Figure 1 is the headline:
  Panel A: ISM index together with 12-month PCE inflation.
  Panel B: the two components S+ (positive) and S- (negative).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .datasources import REPO_ROOT


def figure1(
    ism: pd.Series,
    s_pos: pd.Series,
    s_neg: pd.Series,
    pce_yoy: Optional[pd.Series] = None,
    out_path: Optional[Path] = None,
):
    """Reproduce Figure 1 (two stacked panels). Saves PNG, returns the path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = out_path or (REPO_ROOT / "outputs" / "figure1_ISM.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (axA, axB) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

    # Panel A: ISM + 12m PCE inflation on a secondary axis.
    axA.plot(ism.index, ism.values, color="tab:blue", lw=1.3, label="ISM Index")
    axA.axhline(0, color="grey", lw=0.6)
    axA.set_ylabel("ISM Index")
    if pce_yoy is not None:
        ax2 = axA.twinx()
        ax2.plot(pce_yoy.index, pce_yoy.values, color="tab:orange", lw=1.0,
                 label="PCE inflation (12m)")
        ax2.set_ylabel("PCE inflation (12m, %)")
    axA.set_title("Panel A: Inflation Shock Momentum Index and 12-month PCE inflation")
    axA.legend(loc="upper left")

    # Panel B: components.
    axB.plot(s_pos.index, s_pos.values, color="tab:orange", lw=1.1,
             label="Positive momentum share $S^+_t$")
    axB.plot(s_neg.index, s_neg.values, color="tab:blue", lw=1.1,
             label="Negative momentum share $S^-_t$")
    axB.set_title("Panel B: Components of the ISM index")
    axB.set_ylabel("Share of expenditure")
    axB.legend(loc="upper left")

    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path
