"""
ism.wage_sources
================

Keyless, cached clients for the public series behind the **wage model** (the
site's fifth model). The three older models pull category cross-sections from
BEA/BLS APIs that need registration keys; the wage model instead needs a few
dozen *aggregate* macro series for four countries, and every one of them is
available without a key:

    provider     what it serves here                         auth
    ---------    ------------------------------------------  ----
    fredcsv      any FRED series, as CSV via fredgraph.csv    none
    ons          ONS time series (JSON), UK                   none
    eurostat     Eurostat dissemination API (JSON-stat), EU   none
    insee        INSEE BDM series (CSV export), France        none

Design mirrors :mod:`ism.datasources`: every successful download is written to
``data/raw/<provider>/<id>.<ext>`` with a ``.fetch.json`` sidecar recording the
URL and the UTC fetch time, so a build is auditable and re-running is a no-op
unless ``force=True``.

Why a second module rather than extending ``datasources``?
----------------------------------------------------------
``datasources`` is the *paper replication* layer: its clients are keyed, they
speak the BEA/BLS table dialects, and they are documented against
``config/sources.yaml``. The wage model is a different animal -- a handful of
aggregate series per country, no keys, and a registry of its own
(``config/sources_wage.yaml``). Keeping them apart means neither file has to
carry the other's caveats, and the wage model can be run by anyone who has
cloned the repo, with no registration at all. That matters: the whole point of
the browser twin is that a reader can reproduce the numbers.

A note on FRED without a key
----------------------------
``https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES`` returns the
observations of a single series as CSV and requires no API key. Asking for
several ids in one call returns a **zip**, not a CSV, so this module always
fetches one series per request. It is slower than the keyed JSON API and it
gives no metadata, so ``config/sources_wage.yaml`` carries the units and the
provenance instead.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover - requests is in requirements.txt
    requests = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"

USER_AGENT = "ism-replication/1.0 wage-model (+https://github.com/bzhmacro/ISMI)"
TIMEOUT = 60
RETRIES = 5
BACKOFF = 2.0


class WageFetchError(RuntimeError):
    """A wage-model data pull failed after retries."""


_SESSION = None


def _session():
    global _SESSION
    if requests is None:
        raise RuntimeError("The 'requests' package is required. pip install requests")
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        _SESSION = s
    return _SESSION


def _get(url: str, params: Optional[dict] = None, *, expect: str = "text"):
    """GET with exponential backoff. Returns text or bytes."""
    last = None
    for attempt in range(RETRIES):
        try:
            r = _session().get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise WageFetchError(f"HTTP {r.status_code} from {url}")
            r.raise_for_status()
            return r.content if expect == "bytes" else r.text
        except Exception as exc:  # noqa: BLE001 - retried and re-raised below
            last = exc
            if attempt == RETRIES - 1:
                break
            time.sleep(BACKOFF * (2 ** attempt))
    raise WageFetchError(f"GET failed after {RETRIES} attempts: {url} ({last})")


def _cache_path(provider: str, name: str, ext: str) -> Path:
    p = RAW_DIR / provider
    p.mkdir(parents=True, exist_ok=True)
    safe = name.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-")
    return p / f"{safe}.{ext}"


def _provenance(target: Path, url: str, params: dict) -> None:
    target.with_suffix(target.suffix + ".fetch.json").write_text(
        json.dumps(
            {
                "url": url,
                "params": params,
                "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "file": target.name,
            },
            indent=2,
        )
    )


def _cached_text(provider: str, name: str, ext: str, url: str,
                 params: Optional[dict] = None, force: bool = False) -> str:
    target = _cache_path(provider, name, ext)
    if target.exists() and not force:
        return target.read_text(encoding="utf-8")
    text = _get(url, params)
    target.write_text(text, encoding="utf-8")
    _provenance(target, url, params or {})
    return text


# ---------------------------------------------------------------------------
# FRED (keyless CSV)
# ---------------------------------------------------------------------------
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fred(series_id: str, force: bool = False) -> pd.Series:
    """One FRED series as a float Series indexed by period-start Timestamps.

    FRED writes missing observations as ``"."``; those become NaN and are
    dropped, so the returned index is the set of dates that actually have a
    value. The index is the observation *date* FRED publishes, which for
    monthly series is the first of the month and for quarterly the first of the
    quarter -- deliberately left as-is so downstream resampling is explicit.
    """
    text = _cached_text("fred", series_id, "csv", FRED_CSV, {"id": series_id}, force)
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        raise WageFetchError(f"FRED {series_id}: unexpected CSV shape {df.shape}")
    date_col, val_col = df.columns[0], df.columns[1]
    s = pd.Series(
        pd.to_numeric(df[val_col].replace(".", pd.NA), errors="coerce").values,
        index=pd.to_datetime(df[date_col]),
        name=series_id,
    )
    return s.dropna()


def fred_many(series_ids: Iterable[str], force: bool = False,
              pause: float = 0.15) -> dict[str, pd.Series]:
    """Fetch several FRED series one at a time (multi-id requests return a zip).

    Failures are not fatal: a series that cannot be fetched is omitted and the
    caller decides whether its absence matters. That keeps a build from dying
    because one of 50 state minimum-wage series was renamed.
    """
    out: dict[str, pd.Series] = {}
    for sid in series_ids:
        try:
            out[sid] = fred(sid, force=force)
        except Exception:  # noqa: BLE001 - deliberately non-fatal, see docstring
            continue
        time.sleep(pause)
    return out


# ---------------------------------------------------------------------------
# ONS (keyless JSON)
# ---------------------------------------------------------------------------
ONS_BASE = "https://www.ons.gov.uk"


# ONS will not resolve a bare /timeseries/<id>; the topic path is part of the
# URL. Rather than store a path per series in the registry, we try the handful
# of topics that carry macro series, in order, and cache the one that answers.
ONS_TOPICS = (
    "employmentandlabourmarket/peopleinwork/earningsandworkinghours",
    "economy/inflationandpriceindices",
    "employmentandlabourmarket/peoplenotinwork/unemployment",
    "economy/grossdomesticproductgdp",
    "employmentandlabourmarket/peopleinwork/employmentandemployeetypes",
)


def ons(series_id: str, dataset: str, force: bool = False,
        topic: Optional[str] = None) -> pd.DataFrame:
    """An ONS time series as a tidy frame with monthly/quarterly/annual blocks.

    ONS serves ``/<topic>/timeseries/<id>/<dataset>/data`` as JSON carrying
    three parallel arrays (``months``, ``quarters``, ``years``). We return all
    three, tagged, and let the caller choose -- several UK series (the minimum
    wage, benefit uprating) are only annual while earnings are monthly.
    """
    cache = _cache_path("ons", f"{series_id}_{dataset}", "json")
    if cache.exists() and not force:
        text = cache.read_text(encoding="utf-8")
    else:
        topics = (topic,) if topic else ONS_TOPICS
        text, url, last = None, None, None
        for t in topics:
            url = f"{ONS_BASE}/{t}/timeseries/{series_id.lower()}/{dataset.lower()}/data"
            try:
                text = _get(url)
                break
            except WageFetchError as exc:
                last = exc
        if text is None:
            raise WageFetchError(f"ONS {series_id}/{dataset}: no topic matched ({last})")
        cache.write_text(text, encoding="utf-8")
        _provenance(cache, url, {})
    payload = json.loads(text)
    rows = []
    for freq, key in (("M", "months"), ("Q", "quarters"), ("A", "years")):
        for obs in payload.get(key, []) or []:
            try:
                val = float(obs["value"])
            except (TypeError, ValueError):
                continue
            rows.append({"freq": freq, "date": obs.get("date"), "value": val})
    if not rows:
        raise WageFetchError(f"ONS {series_id}/{dataset}: no observations parsed")
    return pd.DataFrame(rows)


def ons_series(series_id: str, dataset: str, freq: str = "M",
               force: bool = False, topic: Optional[str] = None) -> pd.Series:
    """One frequency of an ONS series, as a Series indexed by period start."""
    df = ons(series_id, dataset, force=force, topic=topic)
    df = df[df["freq"] == freq]
    if df.empty:
        raise WageFetchError(f"ONS {series_id}/{dataset}: no {freq} observations")
    if freq == "M":
        idx = pd.to_datetime(df["date"], format="%Y %b")
    elif freq == "Q":
        # "2022 Q3" -> period start
        idx = pd.PeriodIndex(df["date"].str.replace(" ", ""), freq="Q").to_timestamp()
    else:
        idx = pd.to_datetime(df["date"], format="%Y")
    return pd.Series(df["value"].values, index=idx, name=series_id).sort_index()


# ---------------------------------------------------------------------------
# Eurostat (keyless JSON-stat 2.0)
# ---------------------------------------------------------------------------
ESTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def eurostat(dataset: str, force: bool = False, **filters: Any) -> pd.Series:
    """A single Eurostat series, selected by dimension filters.

    ``filters`` are the dataset's own dimension codes (``geo="DE"``,
    ``na_item="D62"``, ...). The call must pin every dimension down to one
    value except time; if more than one cell comes back we raise, because a
    silently-averaged series is worse than a failure.

    JSON-stat encodes the cube sparsely: ``value`` maps a flat cell index to a
    number, and ``dimension.time.category.index`` maps a time label to its
    position. With all other dimensions of size one, the flat index *is* the
    time position, which is what makes this short.
    """
    params = {"format": "JSON", **{k: v for k, v in filters.items() if v is not None}}
    name = dataset + "_" + "_".join(f"{k}-{v}" for k, v in sorted(params.items()) if k != "format")
    url = f"{ESTAT_BASE}/{dataset}"
    text = _cached_text("eurostat", name, "json", url, params, force)
    payload = json.loads(text)
    if "value" not in payload:
        raise WageFetchError(f"Eurostat {dataset}: no values for {filters}")

    dims = payload["dimension"]
    sizes = {d: len(dims[d]["category"]["index"]) for d in payload["id"]}
    non_time = {d: n for d, n in sizes.items() if d != "time" and n > 1}
    if non_time:
        raise WageFetchError(
            f"Eurostat {dataset}: filters leave >1 value on {list(non_time)}; pin them down"
        )

    time_index = dims["time"]["category"]["index"]
    pos_to_label = {v: k for k, v in time_index.items()}
    obs = {}
    for flat, val in payload["value"].items():
        label = pos_to_label.get(int(flat))
        if label is not None and val is not None:
            obs[label] = float(val)
    if not obs:
        raise WageFetchError(f"Eurostat {dataset}: empty series for {filters}")

    s = pd.Series(obs)
    s.index = _estat_index(s.index)
    return s.sort_index()


def _estat_index(labels: pd.Index) -> pd.DatetimeIndex:
    """Eurostat time labels ('2022', '2022-Q3', '2022-07', '2022-S1') -> dates."""
    out = []
    for lab in labels:
        lab = str(lab)
        if "-Q" in lab:
            out.append(pd.Period(lab.replace("-", ""), freq="Q").to_timestamp())
        elif "-S" in lab:  # bi-annual (minimum wages): S1 -> Jan, S2 -> Jul
            year, half = lab.split("-S")
            out.append(pd.Timestamp(int(year), 1 if half == "1" else 7, 1))
        elif "-" in lab:
            out.append(pd.Period(lab, freq="M").to_timestamp())
        else:
            out.append(pd.Timestamp(int(lab), 1, 1))
    return pd.DatetimeIndex(out)


# ---------------------------------------------------------------------------
# INSEE (keyless CSV export of a BDM series)
# ---------------------------------------------------------------------------
INSEE_SDMX = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM"


def insee_bdm(idbank: str, force: bool = False) -> pd.Series:
    """One INSEE BDM series by idbank, via INSEE's keyless SDMX endpoint.

    ``/series/sdmx/data/SERIES_BDM/<idbank>`` returns structure-specific SDMX-ML
    in which every observation is a self-closing ``<Obs TIME_PERIOD=... 
    OBS_VALUE=.../>`` element, newest first. Period labels are ``YYYY``,
    ``YYYY-MM``, ``YYYY-Qn`` or ``YYYY-Sn``; the same label grammar as Eurostat
    once ``Q``/``S`` are normalised, so ``_estat_index`` does the conversion.

    This is the endpoint ``ism.insee`` already uses for the quarterly national
    accounts, so the wage model adds no new French dependency.
    """
    url = f"{INSEE_SDMX}/{idbank}"
    text = _cached_text("insee", idbank, "xml", url, None, force)
    obs = re.findall(
        r'<Obs\s+TIME_PERIOD="([^"]+)"\s+OBS_VALUE="([^"]*)"', text
    )
    rows = []
    for period, value in obs:
        if value in ("", "NA", "."):
            continue
        try:
            rows.append((period.replace("-T", "-Q"), float(value)))
        except ValueError:
            continue
    if not rows:
        raise WageFetchError(f"INSEE {idbank}: no observations parsed")
    labs, vals = zip(*rows)
    s = pd.Series(vals, index=_estat_index(pd.Index(labs)), name=idbank)
    return s.sort_index()


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------
def load_wage_sources(path: Optional[Path] = None) -> dict[str, Any]:
    """Parse ``config/sources_wage.yaml`` (the wage model's source registry)."""
    import yaml

    p = path or (REPO_ROOT / "config" / "sources_wage.yaml")
    with open(p, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
