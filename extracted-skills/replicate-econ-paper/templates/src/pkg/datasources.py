"""
pkg.datasources  (TEMPLATE)
===========================

Thin, well-documented clients for open data providers, plus the shared HTTP
layer that makes fetching reproducible and failures actionable.

Design goals
------------
* Reproducibility first. Every successful download is cached to
  data/raw/<provider>/<id>.json alongside a `<id>.fetch.json` sidecar recording
  the exact URL, params (secrets redacted), and UTC fetch time. Re-running is a
  no-op unless force=True, so the whole data state rebuilds from sources.yaml +
  the sidecars.
* Environment-agnostic. Keys come from env vars / .env.
* Readable over clever. Each provider is a small class with one job.

Copy this file, keep the shared layer, and add/trim provider clients to match
your registry. The single most useful idea here is the HostBlockedError vs
ApiError split (see below) -- it turns "why is this failing" into a one-line
answer every time.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    import requests
except ImportError:  # requests is a dependency; give a clear message.
    requests = None  # type: ignore

# ---------------------------------------------------------------------------
# Paths & provenance
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _write_provenance(target: Path, url: str, params: dict) -> None:
    """Write a sidecar recording how a raw file was obtained (secrets redacted)."""
    sidecar = target.with_suffix(target.suffix + ".fetch.json")
    secret = ("key", "userid", "registrationkey", "token", "api_key")
    redacted = {k: ("<redacted>" if any(s in k.lower() for s in secret) else v)
                for k, v in params.items()}
    sidecar.write_text(json.dumps(
        {"url": url, "params": redacted, "fetched_utc": _utcnow(), "file": target.name},
        indent=2,
    ))


def _require_requests():
    if requests is None:
        raise RuntimeError("The 'requests' package is required. pip install requests")


# ---------------------------------------------------------------------------
# Shared, robust HTTP layer
# ---------------------------------------------------------------------------
# Two distinct failure causes that are easy to conflate:
#   1. NETWORK BLOCK -- a proxy/firewall refuses to tunnel to the host. No key or
#      retry helps; the request never reached the provider. -> HostBlockedError.
#   2. TRANSIENT FAILURE -- 429 / 5xx / dropped connections. Retried with backoff
#      honoring Retry-After.
# A pooled Session reuses TCP connections and sets a real User-Agent (some gov
# endpoints answer oddly to the default urllib agent).

DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 6
DEFAULT_BACKOFF = 2.0
USER_AGENT = "econ-replication/1.0 (+https://doi.org/REPLACE)"


class FetchError(RuntimeError):
    """Base class for all data-fetch failures."""


class HostBlockedError(FetchError):
    """A proxy/firewall blocked the tunnel: a network-reachability problem, NOT a
    bad key. Run from an environment with direct internet access."""


class ApiError(FetchError):
    """The provider was reached but reported an error (bad key/params/cap)."""

    def __init__(self, provider: str, message: str, code: Optional[str] = None):
        self.provider, self.code = provider, code
        super().__init__(f"[{provider}] {message}" + (f" (code {code})" if code else ""))


_BLOCK_MARKERS = (
    "tunnel connection failed", "proxy", "forbidden",
    "name or service not known", "failed to establish a new connection",
    "connection refused",
)

_SESSION: "requests.Session | None" = None


def _session() -> "requests.Session":
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


def _request(method: str, url: str, *, provider: str, params=None, json_body=None,
             timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES,
             backoff=DEFAULT_BACKOFF) -> "requests.Response":
    """HTTP with retries, rate-limit handling, and the block/api split."""
    sess = _session()
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = sess.request(method, url, params=params, json=json_body, timeout=timeout)
        except Exception as exc:  # network-layer failure (no HTTP response)
            last_exc = exc
            if _looks_like_block(exc):
                raise HostBlockedError(
                    f"[{provider}] host unreachable: a proxy/firewall blocked the "
                    f"connection to {url.split('?')[0]}. This is a network "
                    f"restriction, not a bad API key. Run from an environment with "
                    f"direct internet access. Original error: {exc}") from exc
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise FetchError(f"[{provider}] connection failed after "
                             f"{retries + 1} attempts: {exc}") from exc

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
            raise ApiError(provider, f"HTTP {resp.status_code} after "
                           f"{retries + 1} attempts: {resp.text[:200]}",
                           code=str(resp.status_code))

        if 400 <= resp.status_code < 500:  # bad key/params -- not retryable
            raise ApiError(provider, f"HTTP {resp.status_code}: {resp.text[:300]}",
                           code=str(resp.status_code))
        return resp
    raise FetchError(f"[{provider}] request failed: {last_exc}")


# ---------------------------------------------------------------------------
# Example provider client: FRED  (copy this shape for BEA / BLS / Eurostat / …)
# ---------------------------------------------------------------------------
@dataclass
class FredClient:
    """Minimal FRED client returning a monthly pandas Series, cached with provenance."""

    api_key: Optional[str] = None
    cache_dir: Path = RAW_DIR / "fred"
    base: str = "https://api.stlouisfed.org/fred/series/observations"

    def __post_init__(self):
        self.api_key = self.api_key or os.environ.get("FRED_API_KEY")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _check_key(self):
        if not self.api_key:
            raise ApiError("FRED", "no API key: set FRED_API_KEY in your env / .env")

    def series(self, series_id: str, force: bool = False, **api_params: Any) -> pd.Series:
        """Fetch one FRED series as a monthly-indexed float Series.

        Cached to data/raw/fred/<series_id>.json. FRED's '.' missing marker -> NaN.
        Extra api_params (units=, frequency=, observation_start=) pass through but
        are NOT in the cache filename -- use force=True when changing them.
        """
        cache = self.cache_dir / f"{series_id}.json"
        if cache.exists() and not force:
            payload = json.loads(cache.read_text())
        else:
            self._check_key()
            params = {"series_id": series_id, "api_key": self.api_key,
                      "file_type": "json", **api_params}
            payload = _request("GET", self.base, provider="FRED", params=params).json()
            if "error_message" in payload:  # guard an error-shaped 200
                raise ApiError("FRED", payload["error_message"],
                               code=str(payload.get("error_code")))
            if "observations" not in payload:
                raise ApiError("FRED", f"unexpected response for '{series_id}'")
            cache.write_text(json.dumps(payload))
            _write_provenance(cache, self.base, params)

        obs = payload["observations"]
        idx = pd.to_datetime([o["date"] for o in obs])
        vals = pd.to_numeric(pd.Series([o["value"] for o in obs]).replace(".", pd.NA),
                             errors="coerce")
        return pd.Series(vals.to_numpy(), index=idx, name=series_id)


# ---------------------------------------------------------------------------
# External (non-API) sources
# ---------------------------------------------------------------------------
def fetch_url_bytes(url: str, name: str, force: bool = False) -> Path:
    """Download any file (e.g. an author spreadsheet) and return its cached path."""
    cache_dir = RAW_DIR / "external"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / name
    if not cache.exists() or force:
        resp = _request("GET", url, provider="external", timeout=120)
        cache.write_bytes(resp.content)
        _write_provenance(cache, url, {})
    return cache


# ---------------------------------------------------------------------------
# sources.yaml loader
# ---------------------------------------------------------------------------
def load_sources(path: Optional[Path] = None) -> dict[str, Any]:
    """Load config/sources.yaml as a dict."""
    import yaml
    path = path or (REPO_ROOT / "config" / "sources.yaml")
    return yaml.safe_load(Path(path).read_text())
