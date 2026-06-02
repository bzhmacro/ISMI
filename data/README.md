# Data (not committed)

Raw data and caches are **intentionally excluded** from version control
(`data/raw/`, `data/processed/` are gitignored). They are fully reproducible from
`config/sources.yaml` (US) and `config/sources_europe.yaml` (EU). This keeps the
repo small, avoids redistributing third-party / author data, and prevents API
keys (which some providers echo into responses) from ever being committed.

## How to populate

1. Copy `.env.example` to `.env` and add your free API keys (FRED, BEA, BLS).
2. From the repo root, build the US data + index:
   ```bash
   pip install -e .
   python scripts/build_and_validate.py      # fetches BEA/FRED, builds & validates the index
   ```
   See `notebooks/ISM_replication.ipynb` for the guided version.

## Files you may need to add by hand (documented in config + loaders)

Placed under `data/raw/external/`:
- `ISM_public_author.xlsx` — the authors' published index (ground truth for the
  convergence check). Provided by the paper's authors; not redistributed here.
- `ie_data.xls` — Shiller S&P 500 (auto-downloads if missing).
- `barnichon_hwi.csv` — Barnichon (2010) Help-Wanted Index, for the V/U splice.
- `kanzig_oilshock.csv` — Kanzig (2021) oil-supply news shock (Fig 3b).
- `stoxx600.csv` — STOXX Europe 600 monthly close (EU equity control).

The BEA category set is pinned in `config/pce_categories.csv` (committed), so the
index is reproducible without re-deriving the category list.
