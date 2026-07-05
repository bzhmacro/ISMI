"""
ism.destatis
============

Client + parser for Destatis **GENESIS-Online** (www-genesis.destatis.de), the
Germany analogue of our FRED/BEA/INSEE clients, feeding the German port of the
supply/demand decomposition (`ism.decomp_ports.build_de_panels`, documented in
config/sources_decomp.yaml).

Dataset
-------
Table **81000-0120** (national accounts, quarterly): household final
consumption expenditure by purpose (Verwendungszwecke, COICOP divisions),
nominal (jeweilige Preise) and price-adjusted (preisbereinigt, chain index
2020=100), from 1991. The chain index is a perfectly fine "volume" input for
the decomposition -- log-quantity is scale-free -- while weights always come
from the additive nominal panel.

Access
------
The GENESIS REST/2020 interface requires a (free) registered account:

    base:      https://www-genesis.destatis.de/genesisWS/rest/2020/
    check:     helloworld/logincheck            (username/password params)
    download:  data/tablefile?name=81000-0120&area=all&format=ffcsv&...

Since the 2024 API changes, authentication uses an **API token passed as the
username with an empty password**. Set it in your environment:

    DESTATIS_API_TOKEN=<token from your GENESIS account settings>

and run `python scripts/fetch_destatis.py` once; afterwards everything here is
cache-first from data/raw/destatis/81000-0120.ffcsv.csv (this project's build
sandbox blocks the host, so the download must happen on your machine).

The ffcsv parser below is deliberately defensive: GENESIS has shipped several
flat-file layouts (German "Zeit/…_Merkmal_…/…_Auspraegung_…" columns, English
"time/…_variable_…" columns, wide value columns "CODE__Label__Unit", long
"value" + "value_variable_label" columns; times as "1. Quartal 1991" or
"1991Q1" or split year/quarter columns). It detects each piece generically and
raises actionable errors -- including a loud one if the table turns out to be
annual-only, in which case the honest fallback is to keep Germany out of the
quarterly decomposition.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .datasources import REPO_ROOT, _request, _write_provenance, ApiError

GENESIS_BASE = "https://www-genesis.destatis.de/genesisWS/rest/2020/"
RAW_DESTATIS = REPO_ROOT / "data" / "raw" / "destatis"

#: GENESIS table: quarterly household consumption by purpose, nominal + real.
DE_HCE_TABLE = "81000-0120"

_NO_TOKEN_MSG = ("no API token: set DESTATIS_API_TOKEN (or DESTATIS_API_KEY) "
                 "in .env — free account at https://www-genesis.destatis.de — "
                 "then run scripts/fetch_destatis.py")

# -- time parsing -------------------------------------------------------------
_Q_FULL_DE = re.compile(r"([1-4])\.\s*Quartal\s*(\d{4})")     # "1. Quartal 1991"
_Q_FULL_EN = re.compile(r"(\d{4})\s*[-.]?\s*Q\s*([1-4])")     # "1991Q1", "1991-Q1"
_Q_ONLY = re.compile(r"(?:^|\D)([1-4])\.\s*Quartal|^Q\s*([1-4])$|QUART0?([1-4])")
_YEAR_ONLY = re.compile(r"^\s*(\d{4})\s*$")

#: markers for the price-basis of a measure/dimension label
_CURRENT_RE = re.compile(r"jeweilig|current\s+price", re.IGNORECASE)
_VOLUME_RE = re.compile(r"preisbereinigt|kettenindex|chain", re.IGNORECASE)
_RATE_RE = re.compile(r"ver[äa]nderung|change|rate", re.IGNORECASE)
_TOTAL_RE = re.compile(r"insgesamt|^total\b", re.IGNORECASE)


def _parse_quarter(text: str) -> Optional[pd.Timestamp]:
    """'1. Quartal 1991' / '1991Q1' / '1991-Q1' -> quarter-start Timestamp."""
    s = str(text)
    m = _Q_FULL_DE.search(s)
    if m:
        return pd.Timestamp(int(m.group(2)), 3 * int(m.group(1)) - 2, 1)
    m = _Q_FULL_EN.search(s)
    if m:
        return pd.Timestamp(int(m.group(1)), 3 * int(m.group(2)) - 2, 1)
    return None


def _quarter_number(text: str) -> Optional[int]:
    m = _Q_ONLY.search(str(text))
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _to_float(s: pd.Series) -> pd.Series:
    """GENESIS numbers -> float. Handles ',' decimals and the missing markers
    ('...', '.', '-', 'x', '/'), which become NaN."""
    t = s.astype(str).str.strip()
    t = t.replace({"...": None, ".": None, "-": None, "x": None, "/": None, "": None})
    # if there are commas but no dots, they are decimal commas (German locale)
    has_comma = t.dropna().str.contains(",").any() if t.notna().any() else False
    has_dot = t.dropna().str.contains(r"\.").any() if t.notna().any() else False
    if has_comma and not has_dot:
        t = t.str.replace(",", ".", regex=False)
    elif has_comma and has_dot:  # thousands dots + decimal comma
        t = t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


# -----------------------------------------------------------------------------
# The defensive ffcsv parser
# -----------------------------------------------------------------------------
def parse_ffcsv(text: str) -> pd.DataFrame:
    """Parse a GENESIS 'ffcsv' flat file into a tidy quarterly frame.

    Returns columns: date (quarter-start Timestamp; NaT if the row carries no
    quarter information), code, label (purpose dimension), basis ('current' |
    'volume' | 'other'), value (float).

    Raises ApiError with a specific message when a required piece (time,
    value, purpose, price basis) cannot be identified.
    """
    df = pd.read_csv(io.StringIO(text.lstrip("﻿")), sep=";", dtype=str)
    if df.shape[1] < 3:
        raise ApiError("DESTATIS", f"not an ffcsv flat file (only {df.shape[1]} "
                       f"';'-separated columns): {text[:120]!r}")
    cols = list(df.columns)

    # ---- 1. time -----------------------------------------------------------
    # a column whose values embed a full quarter spec wins outright
    time_col = next((c for c in cols
                     if df[c].dropna().map(lambda x: _parse_quarter(x) is not None).mean() > 0.8
                     and len(df[c].dropna())), None)
    if time_col is not None:
        dates = df[time_col].map(_parse_quarter)
    else:
        # otherwise: a year column (Zeit/time) + a quarter column somewhere else
        year_col = next((c for c in cols
                         if re.fullmatch(r"(?i)zeit|time", str(c))
                         and df[c].dropna().str.match(_YEAR_ONLY).mean() > 0.8), None)
        if year_col is None:
            year_col = next((c for c in cols
                             if df[c].notna().any()
                             and df[c].dropna().str.match(_YEAR_ONLY).mean() > 0.8), None)
        q_col = next((c for c in cols if c != year_col
                      and df[c].dropna().map(lambda x: _quarter_number(x) is not None).mean() > 0.8
                      and len(df[c].dropna())), None)
        if year_col is None:
            raise ApiError("DESTATIS", "ffcsv: could not identify a time column "
                           f"(columns: {cols})")
        if q_col is None:
            # annual-only table: keep NaT dates; de_hce_panels raises loudly
            dates = pd.Series(pd.NaT, index=df.index)
            dates_year = df[year_col].str.extract(_YEAR_ONLY)[0]
            df["_year_only"] = dates_year
        else:
            y = df[year_col].str.extract(_YEAR_ONLY)[0].astype(float)
            q = df[q_col].map(_quarter_number)
            dates = pd.Series([pd.Timestamp(int(yy), 3 * int(qq) - 2, 1)
                               if pd.notna(yy) and qq else pd.NaT
                               for yy, qq in zip(y, q)], index=df.index)

    # ---- 2. dimension (code, label) pairs -----------------------------------
    # German layout: N_Merkmal_Code/-Label + N_Auspraegung_Code/-Label
    # English layout: N_variable_code/-label + N_variable_attribute_code/-label
    dim_pairs = []  # (attribute_code_col, attribute_label_col, variable_label)
    for c in cols:
        m = re.match(r"(?i)^(\d+)_(auspraegung|variable_attribute)_?code$", str(c))
        if not m:
            continue
        lab = next((x for x in cols if re.match(
            rf"(?i)^{m.group(1)}_(auspraegung|variable_attribute)_?label$", str(x))), c)
        var_lab_col = next((x for x in cols if re.match(
            rf"(?i)^{m.group(1)}_(merkmal|variable)_?label$", str(x))), None)
        var_lab = str(df[var_lab_col].dropna().iloc[0]) if var_lab_col is not None \
            and df[var_lab_col].notna().any() else ""
        dim_pairs.append((c, lab, var_lab))

    # ---- 3. value + measure --------------------------------------------------
    value_col = next((c for c in cols if re.fullmatch(r"(?i)value|wert", str(c))), None)
    long_measure_col = next((c for c in cols if re.fullmatch(
        r"(?i)value_variable_label|wert_label", str(c))), None)

    frames = []
    if value_col is not None:
        # LONG layout: one value column; the measure lives in value_variable_label
        # or in a dimension whose labels look like a price basis.
        measure = df[long_measure_col] if long_measure_col is not None else None
        basis_dim = None
        if measure is None:
            for code_c, lab_c, _v in dim_pairs:
                labs = df[lab_c].dropna().unique()
                if any(_CURRENT_RE.search(str(x)) or _VOLUME_RE.search(str(x))
                       for x in labs):
                    basis_dim = (code_c, lab_c)
                    measure = df[lab_c]
                    break
        if measure is None:
            raise ApiError("DESTATIS", "ffcsv: found a 'value' column but no "
                           "measure/price-basis column next to it "
                           f"(columns: {cols})")
        sub = pd.DataFrame({"date": dates, "measure": measure,
                            "value": _to_float(df[value_col])})
        purpose_pairs = [p for p in dim_pairs if basis_dim is None
                         or p[0] != basis_dim[0]]
        frames.append((sub, purpose_pairs))
    else:
        # WIDE layout: one column per measure, named "CODE__Label__Unit" (or at
        # least mostly numeric and not a code/label/time column).
        known = {p[0] for p in dim_pairs} | {p[1] for p in dim_pairs}
        candidates = [c for c in cols if "__" in str(c) and c not in known]
        if not candidates:
            candidates = [c for c in cols if c not in known
                          and not re.search(r"(?i)code|label|zeit|time|qualit",
                                            str(c))
                          and _to_float(df[c]).notna().mean() > 0.5]
        if not candidates:
            raise ApiError("DESTATIS", "ffcsv: could not identify any value "
                           f"column (columns: {cols})")
        for c in candidates:
            sub = pd.DataFrame({"date": dates, "measure": str(c),
                                "value": _to_float(df[c])})
            frames.append((sub, dim_pairs))

    # ---- 4. purpose dimension -------------------------------------------------
    out = []
    for sub, purpose_pairs in frames:
        if not purpose_pairs:
            raise ApiError("DESTATIS", "ffcsv: no purpose (Verwendungszweck) "
                           f"dimension found (columns: {cols})")
        # the purpose dimension = the code/label pair with the most categories
        # that is not itself the price basis
        def n_distinct(p):
            return df[p[1]].nunique(dropna=True)
        purpose_pairs = [p for p in purpose_pairs
                         if not df[p[1]].dropna().map(
                             lambda x: bool(_CURRENT_RE.search(str(x))
                                            or _VOLUME_RE.search(str(x)))).all()]
        code_c, lab_c, _v = max(purpose_pairs, key=n_distinct)
        sub = sub.assign(code=df[code_c].where(df[code_c].notna(), df[lab_c]),
                         label=df[lab_c])
        out.append(sub)
    tidy = pd.concat(out, ignore_index=True)

    # ---- 5. classify the measure into a price basis ----------------------------
    def classify(m: str) -> str:
        s = str(m)
        if _RATE_RE.search(s) and not _VOLUME_RE.search(s):
            return "other"
        if _VOLUME_RE.search(s):
            return "volume"
        if _CURRENT_RE.search(s):
            return "current"
        return "other"

    tidy["basis"] = tidy["measure"].map(classify)
    return tidy[["date", "code", "label", "basis", "measure", "value"]]


# -----------------------------------------------------------------------------
# Client
# -----------------------------------------------------------------------------
class DestatisClient:
    """Minimal GENESIS-Online REST/2020 client (cache-first + provenance).

    Auth (2024+): the API token is sent as `username` with an empty password.
    All heavy lifting is cache-first: `tablefile()` returns the cached ffcsv
    path if data/raw/destatis/<table>.ffcsv.csv exists, and only needs the
    token (and network access to www-genesis.destatis.de) on a cache miss.
    """

    def __init__(self, token: Optional[str] = None,
                 cache_dir: Path = RAW_DESTATIS, base: str = GENESIS_BASE):
        # Accept either DESTATIS_API_TOKEN or DESTATIS_API_KEY (the GENESIS
        # account settings label it "Token"; some users store it as *_KEY).
        self.token = (token if token is not None
                      else os.environ.get("DESTATIS_API_TOKEN")
                      or os.environ.get("DESTATIS_API_KEY"))
        self.base = base
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- internals -------------------------------------------------------------
    def _auth(self) -> dict:
        """Auth HTTP-header fields (GENESIS Webservices v5.0, 2025).

        Since mid-2025 the REST/2020 interface takes credentials as HTTP *header*
        fields (not query params) and only via POST. A personal token is sent in
        the ``username`` field; the password is omitted when a token is used.
        """
        if not self.token:
            raise ApiError("DESTATIS", _NO_TOKEN_MSG)
        return {"username": self.token}

    @staticmethod
    def _raise_on_json_error(text: str) -> Optional[dict]:
        """GENESIS errors come back as JSON with Code/Content -- surface them
        verbatim. Returns the parsed payload for JSON responses, None else."""
        head = text.lstrip("﻿ \n\r\t")
        if not head.startswith("{"):
            return None
        try:
            payload = json.loads(head)
        except ValueError:
            return None
        status = payload.get("Status")
        if isinstance(status, dict):
            code = str(status.get("Code", ""))
            content = str(status.get("Content", ""))
            # GENESIS uses Code 0 / Type "Information" for success wrappers
            if code not in ("0", "22") and content:
                raise ApiError("DESTATIS", content, code=code)
        if "Code" in payload and "Content" in payload and "Object" not in payload:
            raise ApiError("DESTATIS", str(payload.get("Content")),
                           code=str(payload.get("Code")))
        return payload

    # -- API -------------------------------------------------------------------
    def logincheck(self) -> str:
        """helloworld/logincheck -- verifies the token; returns the API's
        own message (raises ApiError on an explicit error payload)."""
        resp = _request("POST", self.base + "helloworld/logincheck",
                        provider="DESTATIS", headers=self._auth(),
                        data={"language": "en"}, timeout=60)
        payload = self._raise_on_json_error(resp.text)
        if isinstance(payload, dict):
            return str(payload.get("Status") or payload)
        return resp.text[:300]

    def tablefile(self, name: str = DE_HCE_TABLE, force: bool = False) -> Path:
        """Download (or reuse) the ffcsv flat file for a GENESIS table.

        Cache: data/raw/destatis/<name>.ffcsv.csv (+ .fetch.json sidecar).
        Errors are actionable: missing token -> how to get one; API errors
        (table not found, no permission, ...) -> the API's message verbatim.
        """
        cache = self.cache_dir / f"{name}.ffcsv.csv"
        if cache.exists() and not force:
            # Self-heal a stale/corrupted cache: an older client wrote the raw
            # ZIP (or a ZIP decoded-as-text) instead of the ffcsv — both begin
            # with the 'PK' magic, which valid ffcsv never does. Re-download it.
            if cache.read_bytes()[:2] != b"PK":
                return cache
        # POST: credentials in the HTTP header (self._auth()), the functional
        # parameters in the form-urlencoded request body (GENESIS v5.0, 2025).
        body = {
            "name": name,
            "area": "all",
            "format": "ffcsv",
            "compress": "false",
            "language": "en",
        }
        resp = _request("POST", self.base + "data/tablefile",
                        provider="DESTATIS", headers=self._auth(),
                        data=body, timeout=300)
        raw = resp.content
        # Since the 2025 relaunch data/tablefile returns a ZIP archive holding a
        # single '<name>_..._flat.csv' (even with compress=false); older
        # deployments returned the raw ffcsv text. Handle both.
        if raw[:2] == b"PK":                       # ZIP magic
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                members = zf.namelist()
                csvs = [m for m in members if m.lower().endswith(".csv")] or members
                if not csvs:
                    raise ApiError("DESTATIS", f"empty archive for table {name}")
                text = zf.read(csvs[0]).decode("utf-8-sig", errors="replace")
        else:
            text = resp.text
            self._raise_on_json_error(text)        # JSON here == an error message
        if ";" not in text.split("\n", 1)[0]:
            raise ApiError("DESTATIS", f"unexpected (non-ffcsv) response for "
                           f"table {name}: {text[:200]!r}")
        cache.write_text(text, encoding="utf-8")
        _write_provenance(cache, self.base + "data/tablefile", body)
        return cache

    def table_tidy(self, name: str = DE_HCE_TABLE, force: bool = False) -> pd.DataFrame:
        """Parsed tidy frame (see `parse_ffcsv`) for a cached/downloaded table."""
        path = self.tablefile(name, force=force)
        return parse_ffcsv(path.read_text(encoding="utf-8"))


# -----------------------------------------------------------------------------
# Panels for the supply/demand decomposition (ism.decomp_ports.build_de_panels)
# -----------------------------------------------------------------------------
def de_hce_panels(client: Optional[DestatisClient] = None, force: bool = False):
    """Quarterly (nominal, volume, labels) household-consumption panels.

    nominal: current-price expenditure by COICOP purpose (jeweilige Preise);
    volume: the price-adjusted chain index (preisbereinigt, 2020=100) -- a
    chain index is fine as the quantity input (log-quantity is scale-free);
    weights must always be computed from `nominal`. The all-purposes total
    (Insgesamt) is excluded from the category panel.

    Raises a loud, actionable ApiError if the cached/downloaded table carries
    no quarterly rows (annual-only) or misses one of the two price bases.
    """
    client = client or DestatisClient()
    tidy = client.table_tidy(DE_HCE_TABLE, force=force)

    q = tidy[tidy["date"].notna()]
    if q.empty:
        raise ApiError(
            "DESTATIS",
            f"table {DE_HCE_TABLE} returned no quarterly observations -- it "
            "appears to be ANNUAL-only (or the time column failed to parse). "
            "If the table is genuinely annual, keep Germany out of the "
            "quarterly decomposition (see scripts/fetch_destatis.py output).")

    found = sorted(q["measure"].astype(str).unique())
    def pivot(basis: str) -> pd.DataFrame:
        sub = q[q["basis"] == basis]
        return sub.pivot_table(index="date", columns="code", values="value",
                               aggfunc="first").sort_index()

    nominal, volume = pivot("current"), pivot("volume")
    if nominal.empty or volume.empty:
        raise ApiError(
            "DESTATIS",
            f"table {DE_HCE_TABLE}: could not find both price bases "
            f"(current prices + price-adjusted). Measures found: {found}")

    lab = (q.dropna(subset=["label"]).drop_duplicates("code")
             .set_index("code")["label"].to_dict())
    keep = [c for c in nominal.columns if c in volume.columns
            and not _TOTAL_RE.search(str(lab.get(c, c)))]
    labels = {c: str(lab.get(c, c)) for c in keep}
    return nominal[keep], volume[keep], labels
