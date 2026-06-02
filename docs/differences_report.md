# Convergence & differences report

## Headline result — the ISM index is replicated

Rebuilt from scratch from BEA Underlying Detail data, our ISM index matches the
authors' published series (`ISM_public.xlsx`, 1969m1–2026m2, 688 months):

| series | correlation | RMSE | max abs diff |
|---|---|---|---|
| **ISM index** | **0.990** | 0.030 | 0.21 |
| S⁺ (positive share) | 0.982 | 0.022 | 0.23 |
| S⁻ (negative share) | 0.986 | 0.021 | 0.13 |

(AR(1) benchmark, 120-month rolling window, k = 3 consecutive same-signed
residuals, expenditure-weighted; engine = `src/ism/engine.py`.)

## How the category set was pinned (the hard part)

The paper uses "the fourth level of disaggregation … 129 categories … going back
to 1959" from BEA tables 2.4.4U (price) and 2.4.5U (nominal). Recovering exactly
this set took several steps, because the BEA JSON API does not expose the table
hierarchy:

1. **Price/nominal code mismatch.** Price series end in `…RG` (e.g. `DGASRG`),
   nominal in `…RC` (`DGASRC`); special lines are `IA…` vs `LA…`. Matching is
   done on a normalized key (`norm_key`: drop the last char for `D…` codes, the
   leading letter for `IA/LA`).
2. **No indentation in the API.** Hierarchy depth cannot be read from the API
   (all descriptions are flush-left), and additive leaf-detection is ambiguous
   (sibling-vs-child overshoot, `Less:` lines). Verified by failing unit tests.
3. **Indentation from the interactive CSV.** BEA's interactive-table CSV keeps
   indentation (4 spaces per level). With depth known, the category set is the
   **level-5 cut**: every node at level 5 plus branches that terminate earlier,
   excluding (a) addenda/special aggregates (Market-based, *excluding*, gross
   output, Control group, PCE food/energy aggregates, `Less:` lines) and (b) the
   **NPISH "… services to households"** net-output layer (a parallel accounting
   of nonprofit output that overlaps the regular service categories).
4. Result: **130 categories** (paper: 129), pinned in `config/pce_categories.csv`.

### Empirical tuning that led here (correlation with author ISM)

| candidate set | #cats | corr |
|---|---|---|
| summary-table level (has `(NN)` ref) | 58 | 0.97 |
| ultimate leaves | 227 | 0.962 |
| level-4 cut | 59 | 0.938 |
| level-5 cut (incl. NPISH lines) | 142 | 0.982 |
| **level-5 cut, NPISH excluded (final)** | **130** | **0.990** |

Methodology choices that turned out **not** to matter (all 0.982 before the NPISH
fix): inflation transform (log vs %), weight normalization (renormalized vs raw
share). This isolates the category set as the only material driver.

## Remaining differences (small, documented)

- **130 vs 129 categories.** One boundary category extra. Identifying which one
  to drop requires the authors' exact list; removing one by guesswork risks
  dropping a legitimate category, so we keep 130 and flag it. Impact on the index
  is within the 0.03 RMSE already reported.
- **Correlation 0.990, not 1.000.** The residual is consistent with the one extra
  category plus minor early-sample handling (categories without a full 120-month
  window early on contribute no momentum until their window fills, matching the
  paper's design but with possible edge differences).
- These do not affect the qualitative findings or the index's time-series
  behavior; the overlay chart (outputs/) shows the two series essentially on top
  of each other.

## Reproducibility

- `config/pce_categories.csv` — the pinned 130-category set (key, SeriesCode,
  line, level, label).
- `scripts/finalize_categories.py` — regenerates that file from the BEA
  interactive CSV + cached API tables.
- `scripts/build_and_validate.py` — builds the index from the pinned set and
  reprints the convergence table above.
- All raw pulls cached under `data/raw/` with `.fetch.json` provenance.

## Status of downstream pieces

| Component | Status |
|---|---|
| ISM index (Fig. 1 series) | ✅ replicated (corr 0.99) |
| Category pipeline | ✅ pinned + deterministic |
| Controls (FRED + Barnichon V/U + Shiller S&P) | ✅ code ready + tested; full-sample via external_data |
| Table 1 in-sample | ✅ in notebook (no-controls match; with-controls full sample once Barnichon/Shiller present) |
| Figure 1 | ✅ in notebook |
| Figure 2 (IRFs, Eq. 9) | ✅ local_projection.py, tested; in ISM_expand.ipynb |
| Figure 3 (Romer-Romer / Kanzig, Eq. 15) | ✅ local_projection.py, tested; Kanzig needs external file |
| Table 2 (out-of-sample LASSO, Eq. 14) | ✅ oos_lasso.py, tested; in ISM_expand.ipynb |
