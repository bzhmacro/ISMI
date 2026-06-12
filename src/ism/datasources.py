"""
ism.datasources
================

Thin, well-documented clients for the open data providers the paper relies on:
FRED (St. Louis Fed), BEA (Bureau of Economic Analysis), and BLS (Bureau of
Labor Statistics). Plus loaders for externally-hosted series (Shiller S&P,
Barnichon vacancies, Kanzig oil shock) that are documented in config/sources.yaml.

Design goals
------------
* **Reproducibility first.** Every successful download is cached to
  data/raw/<provider>/<id>.json (or .csv) alongside a `<id>.fetch.json` sidecar
  recording the exact URL, parameters, and UTC fetch time. Re-running is a
  no-op unless `force=True`, so the full data state can be rebuilt and audited
  later from sources.yaml + the sidecars.
* **Environment-agnostic.** Keys come from environment variables / .env. The
  same code runs in CI, a notebook, or a laptop. (Note: this project's sandbox
  blocks BEA/FRED hosts, so `fetch` is meant to run in the user's environment.)
* **Readable over clever.** Each provider is a small class with one job.

Nothing here is specific to the US: pointing the pipeline at another country is
a matter of swapping series IDs in sources.yaml and providing an equivalent
category price/expenditure source.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    import requests
except ImportError:  # requests is in requirements.txt; give a clear message.
    requests = None  # type: ignore


# ----------------------------------------------------------------------------
# Paths & provenance
# ----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _write_provenance(target: Path, url: str, params: dict) -> None:
    """Write a sidecar recording how a raw file was obtained."""
    sidecar = target.with_suffix(target.suffix + ".fetch.json")
    _secret = ("key", "userid", "registrationkey", "token")
    redacted = {k: ("<redacted>" if any(s in k.lower() for s in _secret) else v) for k, v in params.items()}
    sidecar.write_text(
        json.dumps(
            {"url": url, "params": redacted, "fetched_utc": _utcnow(), "file": target.name},
            indent=2,
        )
    )


def _require_requests():
    if requests is None:
        raise RuntimeError("The 'requests' package is required. pip install requests")


# ----------------------------------------------------------------------------
# Shared, robust HTTP layer
# ----------------------------------------------------------------------------
# The recurring "blocked despite having keys" problem has two distinct causes,
# and this layer disentangles them so failures are actionable:
#
#   1. NETWORK BLOCK. A sandbox / corporate proxy refuses to tunnel to the host
#      (e.g. CONNECT returns "403 Tunnel connection failed"). No key or retry
#      helps; the host simply isn't reachable from here. We raise a clearly
#      labelled `HostBlockedError` so this is never mistaken for a bad key.
#
#   2. TRANSIENT FAILURE. Rate limits (HTTP 429), gateway errors (5xx), or
#      dropped connections. These are retried with exponential backoff, honoring
#      a `Retry-After` header when the server sends one.
#
# All three providers share one pooled `requests.Session`, which reuses TCP
# connections (faster, fewer "connection reset" flakes) and lets us set a real
# User-Agent — some government endpoints answer slowly or oddly to the default
# urllib/requests agent.

DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 6
DEFAULT_BACKOFF = 2.0  # seconds; doubled each attempt (caps via Retry-After)
USER_AGENT = "ism-replication/1.0 (+https://doi.org/10.24148/wp2026-10)"


class FetchError(RuntimeError):
    """Base class for all data-fetch failures raised by this module."""


class HostBlockedError(FetchError):
    """The host could not be reached because a proxy/firewall blocked the tunnel.

    This is a *network reachability* problem, not an authentication problem:
    the request never reached the provider, so the API key is irrelevant. In a
    sandbox this is expected for some hosts (e.g. BEA); run `fetch` from an
    environment with direct internet access.
    """


class ApiError(FetchError):
    """The provider was reached but reported an error (bad key, bad params, ...).

    Carries the provider name and, where available, the provider's own error
    code/message so the cause is obvious without re-reading raw JSON.
    """

    def __init__(self, provider: str, message: str, code: Optional[str] = None):
        self.provider = provider
        self.code = code
        super().__init__(f"[{provider}] {message}" + (f" (code {code})" if code else ""))


# Substrings that mark a proxy/firewall tunnel refusal rather than a real HTTP
# response from the provider.
_BLOCK_MARKERS = (
    "tunnel connection failed",
    "proxy",
    "forbidden",
    "name or service not known",
    "failed to establish a new connection",
    "connection refused",
)


_SESSION: "requests.Session | None" = None


def _session() -> "requests.Session":
    """Return a process-wide pooled session with a sensible User-Agent."""
    global _SESSION
    _require_requests()
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        _SESSION = s
    return _SESSION


def _looks_like_block(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _BLOCK_MARKERS)


def _request(
    method: str,
    url: str,
    *,
    provider: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
) -> "requests.Response":
    """Perform an HTTP request with retries, rate-limit and block handling.

    Retries on 429 and 5xx (honoring Retry-After) and on transient connection
    errors. Raises `HostBlockedError` when the failure is a proxy/firewall
    tunnel refusal, and `ApiError` for non-retryable HTTP error statuses.
    """
    sess = _session()
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = sess.request(
                method, url, params=params, json=json_body, timeout=timeout
            )
        except Exception as exc:  # network-layer failure (no HTTP response)
            last_exc = exc
            if _looks_like_block(exc):
                raise HostBlockedError(
                    f"[{provider}] host unreachable: a proxy/firewall blocked the "
                    f"connection to this endpoint ({url.split('?')[0]}). This is a "
                    f"network restriction, not a bad API key. Run from an "
                    f"environment with direct internet access. Original error: {exc}"
                ) from exc
            # Transient connection error: back off and retry.
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise FetchError(
                f"[{provider}] connection failed after {retries + 1} attempts: {exc}"
            ) from exc

        # Rate limited / transient server error -> retry with backoff.
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        wait = max(wait, float(ra))
                    except ValueError:
                        pass
                time.sleep(wait)
                continue
            raise ApiError(
                provider,
                f"HTTP {resp.status_code} after {retries + 1} attempts: "
                f"{resp.text[:200]}",
                code=str(resp.status_code),
            )

        # Other 4xx: not retryable (bad key, bad params). Surface immediately.
        if 400 <= resp.status_code < 500:
            raise ApiError(
                provider,
                f"HTTP {resp.status_code}: {resp.text[:300]}",
                code=str(resp.status_code),
            )

        return resp

    # Unreachable, but keep the type checker happy.
    raise FetchError(f"[{provider}] request failed: {last_exc}")


# ----------------------------------------------------------------------------
# FRED
# ----------------------------------------------------------------------------
@dataclass
class FredClient:
    """Minimal FRED API client returning a monthly pandas Series.

    Parameters
    ----------
    api_key: FRED API key (defaults to env FRED_API_KEY).
    cache_dir: where raw JSON is cached.
    """

    api_key: Optional[str] = None
    cache_dir: Path = RAW_DIR / "fred"
    base: str = "https://api.stlouisfed.org/fred/series/observations"

    def __post_init__(self):
        self.api_key = self.api_key or os.environ.get("FRED_API_KEY")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _check_key(self):
        if not self.api_key:
            raise ApiError("FRED", "no API key: set FRED_API_KEY in your environment / .env")

    def series(self, series_id: str, force: bool = False, **api_params: Any) -> pd.Series:
        """Fetch one FRED series as a monthly-indexed float Series.

        Cached to data/raw/fred/<series_id>.json. Values of '.' (FRED's missing
        marker) become NaN. The returned index is the observation date.

        Extra keyword arguments (e.g. ``units="chg"``, ``frequency="m"``,
        ``observation_start="1959-01-01"``) are passed straight through to the
        FRED API. Note they are *not* reflected in the cache filename, so use
        ``force=True`` when changing them for an already-cached series.
        """
        cache = self.cache_dir / f"{series_id}.json"
        if cache.exists() and not force:
            payload = json.loads(cache.read_text())
        else:
            self._check_key()
            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                **api_params,
            }
            resp = _request("GET", self.base, provider="FRED", params=params)
            payload = resp.json()
            # FRED returns 400 on real errors (handled in _request), but guard
            # against an unexpected error-shaped 200 too.
            if "error_message" in payload:
                raise ApiError("FRED", payload["error_message"],
                               code=str(payload.get("error_code")))
            if "observations" not in payload:
                raise ApiError("FRED", f"unexpected response for '{series_id}': "
                               f"{json.dumps(payload)[:200]}")
            cache.write_text(json.dumps(payload))
            _write_provenance(cache, self.base, params)

        obs = payload["observations"]
        idx = pd.to_datetime([o["date"] for o in obs])
        vals = pd.to_numeric(
            pd.Series([o["value"] for o in obs]).replace(".", pd.NA), errors="coerce"
        )
        s = pd.Series(vals.to_numpy(), index=idx, name=series_id)
        return s


# ----------------------------------------------------------------------------
# BEA
# ----------------------------------------------------------------------------
@dataclass
class BeaClient:
    """Minimal BEA API client for the NIUnderlyingDetail dataset.

    Returns the raw 'Data' rows for a given monthly table (e.g. U20404 = the
    PCE price-index underlying-detail table 2.4.4U). Parsing into a category
    panel happens in ism.pipeline so this client stays generic.
    """

    api_key: Optional[str] = None
    cache_dir: Path = RAW_DIR / "bea"
    # Canonical BEA API host (see https://apps.bea.gov/API/docs/index.htm).
    base: str = "https://apps.bea.gov/api/data/"

    def __post_init__(self):
        self.api_key = self.api_key or os.environ.get("BEA_API_KEY")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _check_key(self):
        if not self.api_key:
            raise ApiError("BEA", "no API key: set BEA_API_KEY in your environment / .env")

    @staticmethod
    def _raise_on_bea_error(payload: dict) -> dict:
        """BEA always returns HTTP 200; real errors live inside the JSON.

        Two shapes appear in the wild:
          {"BEAAPI": {"Error": {"APIErrorDescription": "..."}}}
          {"BEAAPI": {"Results": {"Error": {"@APIErrorDescription": "..."}}}}
        Plus a {"Results": {"Error": ...}} variant. Normalise and raise.
        """
        api = payload.get("BEAAPI", payload)
        err = api.get("Error")
        if isinstance(err, dict):
            msg = (err.get("APIErrorDescription") or err.get("@APIErrorDescription")
                   or err.get("ErrorDetail", {}).get("Description") or json.dumps(err))
            raise ApiError("BEA", msg, code=str(err.get("APIErrorCode")
                                               or err.get("@APIErrorCode") or ""))
        results = api.get("Results")
        if isinstance(results, dict) and isinstance(results.get("Error"), dict):
            e = results["Error"]
            raise ApiError("BEA", e.get("@APIErrorDescription")
                           or e.get("APIErrorDescription") or json.dumps(e),
                           code=str(e.get("@APIErrorCode") or ""))
        if not (isinstance(results, dict) and "Data" in results):
            raise ApiError("BEA", f"no Data in response: {json.dumps(payload)[:250]}")
        return results

    def table(
        self,
        table_name: str,
        dataset: str = "NIUnderlyingDetail",
        frequency: str = "M",
        year: str = "ALL",
        force: bool = False,
    ) -> pd.DataFrame:
        """Fetch a BEA table as a tidy DataFrame of its 'Data' rows.

        Columns include (BEA's names): SeriesCode, LineNumber, LineDescription,
        TimePeriod, DataValue, METRIC_NAME, etc. These are exactly what the
        pipeline needs to (a) select the 4th-level leaf categories and (b) build
        the price / nominal panels.
        """
        cache = self.cache_dir / f"{dataset}_{table_name}_{frequency}.json"
        if cache.exists() and not force:
            payload = json.loads(cache.read_text())
            results = self._raise_on_bea_error(payload)
        else:
            self._check_key()
            params = {
                "UserID": self.api_key,
                "method": "GetData",
                "datasetname": dataset,
                "TableName": table_name,
                "Frequency": frequency,
                "Year": year,
                "ResultFormat": "json",
            }
            resp = _request("GET", self.base, provider="BEA", params=params, timeout=120)
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ApiError("BEA", f"non-JSON response: {resp.text[:200]}") from exc
            results = self._raise_on_bea_error(payload)  # validate before caching
            cache.write_text(json.dumps(payload))
            _write_provenance(cache, self.base, params)

        rows = results["Data"]
        df = pd.DataFrame(rows)
        # DataValue arrives as a string with thousands separators.
        df["DataValue"] = pd.to_numeric(
            df["DataValue"].astype(str).str.replace(",", "", regex=False), errors="coerce"
        )
        return df


# ----------------------------------------------------------------------------
# BLS
# ----------------------------------------------------------------------------
@dataclass
class BlsClient:
    """Minimal BLS API v2 client (POST). Useful for CPI-based ports / checks."""

    api_key: Optional[str] = None
    cache_dir: Path = RAW_DIR / "bls"
    base: str = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    # BLS API v2 caps one request at 20 years and 50 series.
    MAX_YEARS_PER_REQUEST: int = 20

    def __post_init__(self):
        self.api_key = self.api_key or os.environ.get("BLS_API_KEY")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _check_status(self, payload: dict) -> dict:
        """BLS returns HTTP 200 with a status field; raise unless it succeeded."""
        status = payload.get("status")
        if status != "REQUEST_SUCCEEDED":
            msgs = "; ".join(payload.get("message", [])) or "unknown error"
            raise ApiError("BLS", f"{status or 'no status'}: {msgs}")
        return payload

    def _fetch_window(self, series_id: str, start_year: int, end_year: int,
                      force: bool) -> dict:
        """Fetch a <=20yr window for one series (cached per window)."""
        cache = self.cache_dir / f"{series_id}_{start_year}_{end_year}.json"
        if cache.exists() and not force:
            payload = json.loads(cache.read_text())
            return self._check_status(payload)
        body = {
            "seriesid": [series_id],
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        if self.api_key:  # v2 features (longer history) require a key
            body["registrationkey"] = self.api_key
        resp = _request("POST", self.base, provider="BLS", json_body=body)
        payload = resp.json()
        self._check_status(payload)  # validate before caching
        cache.write_text(json.dumps(payload))
        _write_provenance(cache, self.base,
                          {"series_id": series_id, "registrationkey": "key"})
        return payload

    def series(self, series_id: str, start_year: int, end_year: int,
               force: bool = False) -> pd.Series:
        """Fetch a BLS monthly series, transparently chunking long ranges.

        BLS v2 rejects requests spanning more than 20 years, so we split the
        [start_year, end_year] span into <=20-year windows, fetch (and cache)
        each, then stitch them into one monthly Series.
        """
        recs: list[tuple[str, float]] = []
        lo = start_year
        while lo <= end_year:
            hi = min(lo + self.MAX_YEARS_PER_REQUEST - 1, end_year)
            payload = self._fetch_window(series_id, lo, hi, force)
            data = payload["Results"]["series"][0]["data"]
            recs += [
                (f"{d['year']}-{d['period'][1:]}-01", self._parse_value(d["value"]))
                for d in data
                if d["period"].startswith("M")  # monthly periods M01..M12
            ]
            lo = hi + 1
        recs = sorted(set(recs))
        idx = pd.to_datetime([r[0] for r in recs])
        return pd.Series([r[1] for r in recs], index=idx, name=series_id)

    # BLS API v2 caps one request at 50 series ids.
    MAX_SERIES_PER_REQUEST: int = 50

    @staticmethod
    def _windows(start_year: int, end_year: int, span: int) -> list[tuple[int, int]]:
        """Split [start_year, end_year] into <=`span`-year (lo, hi) windows."""
        out, lo = [], start_year
        while lo <= end_year:
            hi = min(lo + span - 1, end_year)
            out.append((lo, hi))
            lo = hi + 1
        return out

    @staticmethod
    def _parse_value(v: str) -> float:
        """Convert a BLS value string to float. BLS uses '-' for missing months."""
        try:
            return float(v)
        except ValueError:
            return float("nan")

    def _records(self, payload: dict) -> list[tuple[str, float]]:
        data = payload["Results"]["series"][0]["data"]
        return [
            (f"{d['year']}-{d['period'][1:]}-01", self._parse_value(d["value"]))
            for d in data
            if d["period"].startswith("M")
        ]

    def fetch_many(
        self,
        series_ids: list[str],
        start_year: int,
        end_year: int,
        force: bool = False,
    ) -> dict[str, pd.Series]:
        """Fetch many BLS series with the fewest possible HTTP calls.

        Batches up to 50 series ids per POST and splits the year span into
        <=20-year windows, so N series over Y years cost
        ``ceil(N/50) * ceil(Y/20)`` requests instead of N*ceil(Y/20).

        Each series/window is cached in the *same* file format as
        :meth:`series`, so a later single-series ``series()`` call is a cache
        hit. Within a batch, only the series missing from cache are requested
        (unless ``force=True``). Returns ``{series_id: monthly pd.Series}``.
        """
        series_ids = list(dict.fromkeys(series_ids))  # dedupe, keep order
        collected: dict[str, list[tuple[str, float]]] = {s: [] for s in series_ids}

        for lo, hi in self._windows(start_year, end_year, self.MAX_YEARS_PER_REQUEST):
            for i in range(0, len(series_ids), self.MAX_SERIES_PER_REQUEST):
                batch = series_ids[i:i + self.MAX_SERIES_PER_REQUEST]
                payloads: dict[str, dict] = {}
                need: list[str] = []
                for sid in batch:
                    cache = self.cache_dir / f"{sid}_{lo}_{hi}.json"
                    if cache.exists() and not force:
                        payloads[sid] = self._check_status(json.loads(cache.read_text()))
                    else:
                        need.append(sid)

                if need:
                    body = {"seriesid": need, "startyear": str(lo), "endyear": str(hi)}
                    if self.api_key:
                        body["registrationkey"] = self.api_key
                    resp = _request("POST", self.base, provider="BLS", json_body=body)
                    payload = resp.json()
                    self._check_status(payload)
                    # Split the multi-series response into per-series single-series
                    # payloads so the cache layout matches `series()`.
                    for sdata in payload["Results"]["series"]:
                        sid = sdata["seriesID"]
                        single = {
                            "status": payload["status"],
                            "responseTime": payload.get("responseTime"),
                            "message": payload.get("message", []),
                            "Results": {"series": [sdata]},
                        }
                        cache = self.cache_dir / f"{sid}_{lo}_{hi}.json"
                        cache.write_text(json.dumps(single))
                        _write_provenance(cache, self.base,
                                          {"series_id": sid, "registrationkey": "key"})
                        payloads[sid] = single

                for sid in batch:
                    p = payloads.get(sid)
                    if p is not None:
                        collected[sid] += self._records(p)

        result: dict[str, pd.Series] = {}
        for sid in series_ids:
            recs = sorted(set(collected[sid]))
            idx = pd.to_datetime([r[0] for r in recs])
            result[sid] = pd.Series([r[1] for r in recs], index=idx, name=sid)
        return result


# ----------------------------------------------------------------------------
# External (non-API) sources documented in sources.yaml
# ----------------------------------------------------------------------------
def fetch_url_csv(url: str, name: str, force: bool = False, **read_csv_kwargs) -> pd.DataFrame:
    """Download a flat file (CSV/TXT) and cache it with provenance.

    Used for Barnichon HWI, etc. For binary spreadsheets (Shiller .xls) use
    `fetch_url_bytes` and parse with pandas.read_excel.
    """
    cache_dir = RAW_DIR / "external"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / name
    if not cache.exists() or force:
        resp = _request("GET", url, provider="external", timeout=120)
        cache.write_bytes(resp.content)
        _write_provenance(cache, url, {})
    return pd.read_csv(cache, **read_csv_kwargs)


def fetch_url_bytes(url: str, name: str, force: bool = False) -> Path:
    """Download any file (e.g. Shiller ie_data.xls) and return its cached path."""
    cache_dir = RAW_DIR / "external"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / name
    if not cache.exists() or force:
        resp = _request("GET", url, provider="external", timeout=120)
        cache.write_bytes(resp.content)
        _write_provenance(cache, url, {})
    return cache


# ----------------------------------------------------------------------------
# sources.yaml loader
# ----------------------------------------------------------------------------
def load_sources(path: Optional[Path] = None) -> dict[str, Any]:
    """Load config/sources.yaml as a dict."""
    import yaml

    path = path or (REPO_ROOT / "config" / "sources.yaml")
    return yaml.safe_load(Path(path).read_text())
