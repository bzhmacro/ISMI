---
name: replicate-econ-paper
description: >-
  Replicate a quantitative economics / finance paper as a portable, auditable
  artifact: a readable Python package whose code maps to the paper's equations, a
  data-source registry that fetches every input reproducibly from public providers
  (FRED, BEA, BLS, Eurostat, ONS, e-Stat, World Bank, IMF, OECD), validation
  against the authors' published numbers, and a zero-build interactive website that
  recomputes the model live in the browser. Use whenever the user wants to
  reproduce, port, extend, or "turn into a website" a paper that builds an index,
  estimator, decomposition, or forecast from public time-series/panel data, even if
  they name only one piece ("scrape the data sources", "build the index", "validate
  against their file", "ship it as an interactive site", "port it to another
  country"). Trigger on "replicate this paper", "reproduce the index", "rebuild from
  the data", "make the data pipeline reproducible", "parity-test a JS version",
  "deploy the model as a dashboard", or "redo this for another country".
license: MIT
---

# Replicate an economics paper (data → engine → validation → website)

This skill captures a methodology — first built replicating Lansing & Shapiro
(2026)'s Inflation Shock Momentum index, and reused across country ports and a
second model (a supply/demand decomposition) — for turning a quantitative
economics paper into something **reproducible, auditable, portable, and
explorable**:

- a **data-source registry** that declares every external input once, and thin
  fetch clients that cache each pull with provenance so the whole data state can
  be rebuilt and audited from the registry alone;
- a **readable engine** where each function maps to a numbered equation and the
  whole computation flows from one canonical data contract;
- a **validation layer** that converges the rebuilt output onto the authors'
  published numbers and a written record of every judgment call and residual
  difference;
- a **zero-build website** that ships the *raw* inputs and recomputes the model
  client-side, with a JS engine kept honest by a Python↔JS parity test.

Read this file for the shape of the system and the build order, then open the
reference file for the layer you are working on:

- `references/architecture.md` — package layout, the **`(panel, weights)` data
  contract**, equation→code discipline, how a model becomes portable, multi-model
  and multi-country structure.
- `references/data-sources.md` — the `sources.yaml` registry schema and the fetch
  clients: caching, provenance sidecars, the **network-block vs API-error** split,
  rate-limit/window chunking, bulk fallbacks, and per-country source mappings.
- `references/web-port.md` — the static site, the **parity-tested JS twin** of the
  engine, the worker, the JSON export, Vercel deploy, and a scheduled auto-refresh.
- `references/validation.md` — converging on author ground truth, the convergence
  table, and the **DECISIONS log + differences report** discipline that makes the
  replication defensible.

The `templates/` directory has runnable skeletons (a generic registry, a fetch
client, an engine, the export script, the web triplet, and a parity test). Copy
them into the new project and re-point them; they encode the patterns below so a
new replication starts from working code, not a blank page.

## The mental model: one data contract, four layers

Almost every empirical paper of this kind reduces to **a transform of a panel of
time series into a smaller object** (an index, a set of contributions, a
forecast). The single most important design decision is to name that panel
explicitly and route everything through it:

> The engine only ever sees a **`(panel, weights)`** pair — `panel` is
> months × units (categories, sectors, bonds, regions…), `weights` is the
> aligned importance of each unit. It knows nothing about the country, the
> provider, or the file format.

Everything upstream of that contract is *plumbing* (fetch + assemble), everything
downstream is *maths* (the equations) and *presentation* (validation + website).
Get the contract right and three hard things become easy: porting to another
country is "write one new loader that returns the same pair"; feeding in a
forecast scenario is "append future rows to the panel and recompute"; and the
website is "ship the panel as JSON and reimplement the maths in JS."

The four layers, in build order:

1. **Registry + fetch** (`config/sources.yaml` + `datasources.py`). Declare every
   source; fetch reproducibly with caching and provenance. See
   `references/data-sources.md`.
2. **Pipeline → engine** (`pipeline.py` builds the `(panel, weights)` pair;
   `engine.py` runs the equations). See `references/architecture.md`.
3. **Validation** (converge on the authors' file; log decisions & differences).
   See `references/validation.md`.
4. **Website** (export raw panels to JSON; recompute in a parity-tested JS twin).
   See `references/web-port.md`.

## Build sequence

Work the layers in order; each rests on the one before. Do **not** start the
website before the Python engine validates, and do not tune the engine before the
data is reproducible — otherwise you cannot tell a data bug from a maths bug.

1. **Read the paper for the data appendix first, not the theory.** Identify every
   external series/table, its provider and exact identifier, the sample, the
   transform (level → growth, real vs nominal, SA vs NSA), and the unit of
   disaggregation ("the fourth level", "COICOP 4-digit", "the S&P 500
   constituents"). Write these into `config/sources.yaml` *as you read* — the
   registry is your reading notes. See `references/data-sources.md`.

2. **Stand up the fetch clients.** One small class per provider, sharing a robust
   HTTP layer. Every successful pull is cached with a `.fetch.json` provenance
   sidecar. Crucially, distinguish a **network block** (proxy/firewall — the key
   is irrelevant) from an **API error** (bad key/params) so failures are
   actionable. Keys come from env vars; never commit them.

3. **Pin the unit set deterministically.** The single hardest part of most
   replications is recovering the authors' exact cross-section (e.g. "129
   categories"). Walk the provider hierarchy, take a reproducible cut, and **pin
   it to a CSV in `config/`** so it never drifts. Record how you derived it.

4. **Build the `(panel, weights)` pair**, then **write the engine** with each
   function mapping to a numbered equation. Keep parameters (window, lags, run
   length, weighting) as arguments, not constants — robustness checks and ports
   reuse the same code.

5. **Validate against ground truth.** Print a convergence table (correlation,
   RMSE, MAE, max abs diff) vs the authors' published series; save an overlay
   chart. Write `DECISIONS.md` (the calls you made and the alternatives) and a
   `differences_report.md` (what still differs and why). See
   `references/validation.md`.

6. **Lock it with synthetic unit tests** that need no network: the engine
   identities, the loaders/parsers, and — once the site exists — the Python↔JS
   parity test.

7. **Export and build the website.** Ship the *raw* panels (not a precomputed
   grid) plus one baseline combo as JSON; recompute live in a Web Worker running
   a JS port of the engine; keep the port honest with the parity test; deploy
   static (no build step) and optionally auto-refresh on a schedule. See
   `references/web-port.md`.

8. **Port and extend.** A new country is a new loader returning the same
   `(panel, weights)` pair plus a `sources_<cc>.yaml` mapping; a second model is a
   new engine behind the same contract and a toggle in the site.

## Guardrails worth keeping

- **Reproducible from the registry alone.** No raw data and no secrets in git;
  everything downloads from `sources.yaml`, every pull leaves a provenance trail.
- **Readable over clever.** Each engine function is a direct, auditable
  translation of one equation — someone should be able to read it next to the
  paper. Comment the equation number.
- **Degrade gracefully.** Optional external files (author-hosted shocks, long
  histories) should be drop-in: if absent, the pipeline still runs on a shorter
  sample with a clear note, never a crash.
- **One contract, many fronts.** Resist provider- or country-specific logic
  leaking into the engine. If it knows what a "BEA table" is, the abstraction has
  leaked.
