# Archived: wages, indexation and the spiral gain

This was the site's fifth model ("Wages & indexation"). It was taken off the site
on 24 November 2026 because the series it showed looked wrong and need checking
before they go back in front of readers. Nothing here has been changed: every
file was moved with `git mv`, so its history is intact (`git log --follow <file>`).

The last commit with the model live on the site is `828a109` ("Download data ·
all countries" on every page). `git checkout 828a109 -- <path>` gets back any
file exactly as it was.

## What the model was

When prices move, what happens to what households are paid, and does that feed
back into prices? Two objects:

- **The Effective Wage Index** adds market pay, statutory wage floors, indexed
  benefits and one-off handouts, weighted by an income group's actual income
  composition, and deflates by both the recorded price index and the index that
  would have been recorded without caps and tariff shields.
- **The Spiral Gain** `G = Λ × M`: price-to-wage catch-up times wage-to-price
  pass-through, read at a three-year horizon. The indexation intensity λ comes
  from a hand-built, row-by-row sourced database of who was indexed to what
  (`config/indexation_coverage.csv`), seven countries from 1960.

The full write-up is in `README_section.md` (the section as it stood in the main
README), `docs/wage_methodology.md` (maths→code map, Eqs. W1–W12),
`docs/DECISIONS_wage.md` (the judgment calls), the paper
(`paper/wage_inflation.md`, rendered as `web/paper/wage_inflation.html` and
`.pdf`) and `ORIGINAL_COMMIT_MSG.txt` (the commit message that introduced it,
with the Chow-test and pooling results).

## What is where

The folder mirrors the repo layout, so each file sits at its old path under
`archive/wage-model/`.

| Archived at | Was at | What it is |
|---|---|---|
| `src/ism/wage_engine.py` | `src/ism/` | the maths (Eqs. W1–W12) |
| `src/ism/wage_pipeline.py` | `src/ism/` | country panels, statutory uprating rules |
| `src/ism/wage_sources.py` | `src/ism/` | keyless FRED / ONS / Eurostat / INSEE clients |
| `src/ism/wage_validate.py` | `src/ism/` | validation checks |
| `scripts/build_wage.py` | `scripts/` | fetch, assemble, estimate, validate |
| `scripts/export_wage_data.py` | `scripts/` | writes `web/data/wage.json` |
| `scripts/build_paper.py` | `scripts/` | renders the paper to HTML + PDF |
| `config/indexation_coverage.csv`, `config/wage_*.csv` | `config/` | the institutional database and inputs |
| `data/wage/` | `data/wage/` | estimation panels, fits, `validation.txt` |
| `docs/wage_methodology.md` | `docs/` | maths→code map |
| `docs/DECISIONS_wage.md` | section of `docs/DECISIONS.md` | the "Wage model (model 5)" section |
| `paper/` | `paper/` | paper source, PDF, LaTeX assets and fonts |
| `web/wage_app.js`, `web/wage_engine.js` | `web/` | the page and its parity-tested JS engine |
| `web/data/wage.json` | `web/data/` | the site payload |
| `web/paper/` | `web/paper/` | the paper as served on the site |
| `web/index_wage_view.html` | part of `web/index.html` | the `#wage-view` markup and its two script tags |
| `web/wage_styles.css` | part of `web/styles.css` | the page's CSS |
| `README_section.md` | section of `README.md` | "Fifth model: wages, indexation and the spiral gain" |
| `ORIGINAL_COMMIT_MSG.txt` | `COMMIT_MSG.txt` (repo root) | the introducing commit message |

Not in the repo: `tests/` is gitignored, so `tests/test_wage_engine.py` and
`tests/test_wage_parity.py` exist only in your local copy. The parity test is
what makes `web/wage_engine.js` trustworthy. Keep it.

## What to check before it goes back

It was archived because the data looked bad. Places to start:

- `data/wage/validation.txt`: the last validation run.
- The French and German series. `docs/DECISIONS_wage.md` records an earlier
  INSEE series mix-up that made the French real wage fall 11% over 2019–22, and
  the German tax-free inflation bonus, which inflates measured 2023–24 wage
  growth.
- The four channel elasticities behind λ (0.90 / 1.00 / 0.35 / 0.30). They are
  assumptions, not estimates.

## Restoring it

From the repo root:

```bash
A=archive/wage-model
git mv $A/src/ism/wage_*.py src/ism/
git mv $A/scripts/build_wage.py $A/scripts/export_wage_data.py $A/scripts/build_paper.py scripts/
git mv $A/config/indexation_coverage.csv $A/config/wage_*.csv config/
git mv $A/docs/wage_methodology.md docs/
git mv $A/data/wage data/wage
git mv $A/paper paper
git mv $A/web/wage_app.js $A/web/wage_engine.js web/
git mv $A/web/data/wage.json web/data/
git mv $A/web/paper web/paper
```

Then paste back by hand:

1. `web/index_wage_view.html` into `web/index.html`, just before `</main>`, and
   its two `<script>` tags after `cpipce_app.js`;
2. `web/wage_styles.css` into `web/styles.css`;
3. `docs/DECISIONS_wage.md` into `docs/DECISIONS.md`;
4. the `wages()` exporter and its `["wage-view", …]` entry into
   `web/page_download.js` (see commit `828a109`);
5. the `paper/.header.tex` line in `.gitignore` back to its old path.

Then rebuild with `python scripts/build_wage.py && python scripts/export_wage_data.py`.

The scripts resolve paths from the repo root (`src/`, `config/`, `data/`), so
they only run once moved back. They will not run from inside `archive/`.
