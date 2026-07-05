# Validation: converge on ground truth, and write down every call

A replication is only believable if you can show two things: that your rebuilt
output lands on the authors' published numbers, and that you can account for every
choice and every residual difference. This layer is what separates "I got a similar
chart" from "this is a defensible replication."

## Contents
- The convergence table
- The overlay chart
- DECISIONS.md — the judgment-call log
- differences_report.md — what still differs and why
- Synthetic unit tests
- Isolating the binding choice

## The convergence table

When the authors publish their series (often an appendix spreadsheet, sometimes
provided on request), align it to your computed output and print a table of
distance metrics for every component you reproduce:

| series | correlation | RMSE | MAE | max abs diff |
|---|---|---|---|---|
| Index | 0.990 | 0.030 | … | 0.21 |
| S⁺ component | 0.982 | 0.022 | … | 0.23 |
| S⁻ component | 0.986 | 0.021 | … | 0.13 |

Print it from `run.py index` (and from `scripts/build_and_validate.py`) so it
regenerates on every build and a regression is obvious. State the exact spec the
table is computed under (window, lags, run length, weighting). Decide up front what
"converged" means for your paper — correlation ≥ ~0.99 and RMSE within the paper's
own reported tolerance is a reasonable bar for an index.

## The overlay chart

Numbers convince reviewers; a picture convinces everyone else. Save an overlay of
your series on the authors' to `outputs/` (`validate.overlay_chart`). When they sit
essentially on top of each other, that image is the headline evidence.

## DECISIONS.md — the judgment-call log

Every replication forces choices the paper underspecifies. Record them as you go, so
they can be revisited, in a consistent format:

```
## D3. Defining the "fourth level / 129 categories"
- Options considered, with #units and correlation vs the author series:
  summary level (58, 0.97); ultimate leaves (227, 0.962); level-4 (59, 0.938);
  level-5 incl. NPISH (142, 0.982); level-5 excl. addenda + NPISH (130, 0.990).
- Taken: the 130-unit level-5 cut excluding addenda and the NPISH net-output layer.
  Lands one above the paper's 129 at correlation 0.990.
- Not taken: chasing exactly 129 by dropping one more — without the authors' exact
  list this risks removing a legitimate unit; the residual is within the reported
  RMSE. Flagged in differences_report.md.
```

For each decision: the **options on the table**, the **path taken and why**, and the
**caveats you could not resolve** (e.g. an external file's exact format is
unverified from this environment). This log is also where country-port choices and
second-model choices live.

## differences_report.md — what still differs and why

A short, honest accounting of the gap between your output and the authors':

- The headline result (the convergence table again) up top.
- **How the hardest part was pinned** — typically the cross-section. Walk through
  the steps (code mismatch, missing hierarchy in the API, where you recovered
  depth) and the empirical tuning table (candidate sets × correlation) that
  justifies the final cut.
- **Remaining differences**, each with a magnitude and an explanation (e.g. "130 vs
  129 units — one boundary unit extra; impact within the 0.03 RMSE"), and an
  explicit statement that they don't affect the qualitative findings.
- A **reproducibility** note: which committed files + scripts regenerate the pinned
  set and the table, and that all raw pulls are cached with provenance.
- A **status table** of every downstream exhibit (each figure/table: replicated /
  in-notebook / needs-external-file).

Writing this forces you to actually understand the residual instead of hand-waving
it, and it is the first thing a careful reader will look for.

## Synthetic unit tests (no network)

Lock the maths with tests that need no API access, so CI is fast and deterministic:

- **Engine identities** — momentum-run logic; `Index == S⁺ − S⁻`; AR residual
  recovery on a known DGP; weights renormalise to 1 over defined units.
- **Loaders/parsers** — the trickier file parsers (e.g. the Shiller spreadsheet),
  windowing/chunking, missing-value sentinels.
- **Downstream machinery** — that a genuinely predictive signal lowers out-of-sample
  RMSFE with a significant test statistic on synthetic data; local-projection signs.
- **Python↔JS parity** — the cross-language test from web-port.md.

Test on synthetic data precisely because the build environment often can't reach the
providers — the live numbers are produced when the user runs on their machine, but
the logic is proven anywhere.

## Isolating the binding choice

When you're far from the authors' numbers, change one thing at a time and watch the
correlation. In practice a single choice usually dominates (the cross-section), and
several plausible-looking ones (log vs % transform, raw vs renormalised weights)
turn out not to move the result at all. Demonstrating that — "all candidates sat at
0.982 until the unit-set fix took it to 0.990" — both finds the real lever and tells
you where *not* to keep fiddling.
