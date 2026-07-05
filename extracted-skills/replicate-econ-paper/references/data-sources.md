# Data sources: the registry and the fetch clients

The goal of this layer is a strong claim: **the entire data state can be rebuilt
and audited from `config/sources.yaml` plus the cached provenance sidecars** — no
manual downloads, no undocumented spreadsheets, no secrets in git. This file
describes the registry schema and the fetch-client patterns that deliver it.

## Contents
- Why a registry
- `sources.yaml` schema
- The fetch client: shared HTTP layer
- Caching + provenance sidecars
- The network-block vs API-error split (the key insight)
- Provider quirks (rate limits, windowing, error-in-200, bulk fallbacks)
- External / author-hosted files
- Country mapping files
- The fetch CLI

## Why a registry

Replications rot because the data provenance lives in someone's head or a one-off
script. A single declarative registry fixes that: it is simultaneously your
reading notes on the paper's data appendix, the single source of truth the
downloader reads, and the thing a reviewer audits. Updating a series ID or URL in
one place refreshes the whole pipeline.

## `sources.yaml` schema

Group sources by **role in the paper**, not by provider, and annotate each with the
exact identifier, access method, and what it feeds. A representative shape (see
`templates/config/sources.yaml` for a copyable version):

```yaml
meta:
  paper: "Author (Year). Title. Venue/WP no."
  doi:   "https://doi.org/…"
  sample: {start: "1959-02", end: "2026-02"}
  notes: >
    Anything that explains the sample boundaries (e.g. why the index starts later
    than the data: the first W-month window).

keys:                      # names of the ENV VARS, never the keys themselves
  fred: {env: "FRED_API_KEY"}
  bea:  {env: "BEA_API_KEY"}

core_units:                # the heart: the cross-section price/weight source
  provider: bea
  dataset:  "NIUnderlyingDetail"
  method:   "GetData"
  frequency: "M"
  tables:
    price_index:    {table_name: "U20404", role: "p_{i,t} -> unit inflation"}
    nominal_expend: {table_name: "U20405", role: "w_{i,t} -> weights (Eqs 6-7)"}
  selection: {level: 4, expected_n_units: 129}   # how the cross-section is cut
  bulk_fallback:                                  # if the API is unreachable
    url:   "https://apps.bea.gov/national/Release/ZIP/Underlying.zip"
    files: ["U20404-M.csv", "U20405-M.csv"]

controls:                  # each predictor, with provider + transform + role
  inflation_expectations_1y:
    provider: fred
    series_id: "MICH"
    transforms: ["as_is"]
    role: "1-yr-ahead household inflation expectations"
    proxy_before_1978: "trailing 12-month inflation (paper fn 14)"

external_shocks:           # identified shocks for validation sections
  kanzig_oil_supply_news:
    provider: external
    url: "https://www.diegokaenzig.com/research"
    role: "oil supply news shock (Eq. 15)"

ground_truth:              # the authors' published numbers
  author_index:
    provider: manual
    file: "data/raw/author_index.xlsx"
    columns: ["time_month", "Index", "S_pos", "S_neg"]
    role: "validate computed Index / S+ / S- (convergence table)"

external_files:            # drop-in files the loaders expect on disk
  shiller_sp500:
    path: "data/raw/external/ie_data.xls"
    auto_download: true
    url: "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
    loader: "pkg.external_data.load_shiller_sp500"
```

Useful per-entry fields: `provider`, identifier (`series_id` / `table_name` /
`series_pattern`), `method`, `frequency`, `role` (one line on what equation/column
it feeds), `transforms`, `selection`, `bulk_fallback`, and any `note`/`proxy_…`
documenting simplifications. Write the *why* in `notes`/`role` — future-you and
reviewers read this, not the code.

## The fetch client: shared HTTP layer

One small class per provider (`FredClient`, `BeaClient`, `BlsClient`, …), each with
one job, all sharing a single robust request function and a **pooled
`requests.Session`** with a real `User-Agent` (some government endpoints answer
slowly or oddly to the default urllib agent, and a pooled session avoids
connection-reset flakes). The shared `_request()` handles retries with exponential
backoff, honours `Retry-After`, retries 429/5xx and transient connection errors,
and surfaces 4xx immediately as non-retryable. See
`templates/src/pkg/datasources.py` for a complete, copyable implementation.

## Caching + provenance sidecars

Every successful download is written to `data/raw/<provider>/<id>.json` (or `.csv`)
**and** a sibling `<id>.fetch.json` recording the URL, the parameters (with any
key/userid/token redacted), the UTC timestamp, and the filename. Re-running is a
no-op unless `force=True`. This makes the cache self-describing: months later you
can answer "where did this number come from and when" from the sidecar alone.

## The network-block vs API-error split (the key insight)

The recurring "it's blocked despite having a valid key" confusion has **two
distinct causes**, and conflating them wastes hours. Disentangle them with typed
exceptions:

- **`HostBlockedError`** — a proxy/firewall refused to tunnel to the host (CONNECT
  returned "tunnel connection failed", "name or service not known", "connection
  refused", …). The request never reached the provider, so the **API key is
  irrelevant**. Detect it by matching block-marker substrings on the connection
  exception and raise a clearly-labelled error telling the user to run from an
  environment with direct internet access. (Many sandboxes block specific
  government hosts — expected, not a bug.)
- **`ApiError(provider, message, code)`** — the provider *was* reached and reported
  an error (bad key, bad params, rate cap). Carry the provider name and its own
  error code/message so the cause is obvious without re-reading raw JSON.

This single distinction is the most valuable lesson of the data layer: it turns
"why is this failing" into a one-line, actionable answer every time.

## Provider quirks worth handling once

- **HTTP 200 with an error inside.** Some APIs (BEA, BLS) always return 200 and put
  real errors in the JSON body, in more than one shape. Write a `_raise_on_error`
  that normalises the known shapes and validates the payload **before** caching, so
  you never cache a failure.
- **Request-window limits.** Some APIs cap a request (BLS v2: ≤20 years and ≤50
  series). Transparently split long spans into windows and batch series, caching
  per (series, window) so a later single-series call is a cache hit. Aim for
  `ceil(N/maxseries)·ceil(Y/maxyears)` requests, not `N·…`.
- **Missing/again markers.** Providers use sentinels for missing values (`.` in
  FRED, `-` in BLS); coerce to `NaN`. Keep only monthly periods (`M01..M12`; drop
  annual-average `M13`).
- **Bulk fallback.** For every API source, record the flat-file/zip alternative in
  the registry (`bulk_fallback`) so the pipeline survives an API outage or daily
  cap. Note any User-Agent requirement.
- **Interior publication gaps.** If a single interior month is genuinely missing
  (e.g. a skipped CPI release) it can break a month-over-month chain and silently
  zero out every later signal. Interpolate **interior** gaps only
  (`limit_area="inside"`, never fabricating a leading/trailing tail) and document
  the interpolated month in the registry.

## External / author-hosted files

Not everything has an API: author replication files, Shiller's spreadsheet,
Barnichon's help-wanted index, hand-typed event dates from the paper text. Handle
these with `fetch_url_csv` / `fetch_url_bytes` helpers (same cache+provenance) and
a small `external_data.py` loader per file, declared under `external_files` with an
`auto_download` flag. **Degrade gracefully**: if an optional file is absent, run on
the shorter sample with a clear note rather than crashing (e.g. V/U starts in 2000
instead of the 1950s; a figure that needs the file is skipped).

## Country mapping files

A port gets its own `config/sources_<cc>.yaml` that maps each *role* in the base
registry to the national-statistics equivalent (FRED→Eurostat, BEA→ONS,
BLS→e-Stat). Keep the role names identical so the loaders line up; flag anything
still unresolved (e.g. "no national equity index — use an external STOXX file") in
the file itself, where the next person will see it.

## The fetch CLI

Expose `run.py fetch [backbone]` that reads the registry, iterates the declared
sources, and downloads+caches each. Because every pull is cached with provenance,
`fetch` is idempotent and safe to re-run, and downstream steps (`index`, `table`,
`figures`, `all`) run entirely from the cache — so they work anywhere even when the
fetch host is only reachable from the user's own machine.
