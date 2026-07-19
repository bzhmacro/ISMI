"""
ism.insee
=========

Client + parser for the INSEE BDM SDMX API (bdm.insee.fr), the France analogue
of our FRED/BEA/StatCan/ONS clients. This is the data backbone for the French
port of the supply/demand decomposition (see `ism.decomp_ports.build_fr_panels`
and config/sources_decomp.yaml).

Dataset
-------
Quarterly national accounts (Comptes nationaux trimestriels, base 2020),
dataflow **CNT-2020-OPERATIONS**, operation **P3M** = household final
consumption expenditure by product, at the A17 aggregation level:

  * VALORISATION = "V" : values at current prices (nominal, EUR millions)
  * VALORISATION = "L" : volumes chained at previous-year prices (EUR millions)

Quarterly from 1949 Q1, seasonally and working-day adjusted (CVS-CJO), no API
key required. 18 A17 product series exist for P3M: the 17 A17 "leaves"
(AZ, C1..C5, DE, FZ, GZ, HZ, IZ, JZ, KZ, LZ, MN, OQ, RU) plus PCHTR (the
tourism balance / territorial correction, which can be negative and is
excluded from the category panel but included in the total).

SDMX key structure (discovered from the FR1 datastructure; positions 2..13):

    FREQ . INDICATEUR . SECT-INST . COMPTE . OPERATION . CNA_PRODUIT .
    NATURE . REF_AREA . VALORISATION . UNIT_MEASURE . CORRECTION . SERIE_ARRETEE

so the one request that carries everything this module needs is

    https://bdm.insee.fr/series/sdmx/data/CNT-2020-OPERATIONS/T....P3M.......

(FREQ=T, OPERATION=P3M, all other dimensions wildcarded). Each <Series>
element carries CNA_PRODUIT ("A17-AZ", ...), VALORISATION, IDBANK, TITLE_FR /
TITLE_EN and <Obs TIME_PERIOD="1949-Q1" OBS_VALUE="..."/> children.

Caching
-------
Cache-first, like every other client in this repo: the parsed tidy CSV
(data/raw/insee/fr_cnt_p3m_a17.csv), a metadata sidecar (.meta.json with
idbanks, titles and labels) and a provenance sidecar (.csv.fetch.json). When
the cache is missing the client fetches and parses the SDMX-ML itself (also
keeping the raw XML) -- run that from a machine with access to bdm.insee.fr
(this project's build sandbox blocks the host; the shipped cache was fetched
and checksum-validated from the live API).

NOTE: chained previous-year-price volumes are not additive across products;
that is fine here -- the decomposition only needs each category's implicit
deflator (V/L) and volume, and weights come from the additive nominal panel.

Two cross-sections
------------------
* **A17 (~17 products)** -- the SDMX/BDM path above (`p3m_a17`, `fr_hce_panels_a17`).
* **Detail (~40 products)** -- INSEE only publishes the finer quarterly product
  breakdown as the "Consommation des ménages -- par produit" *Excel* tables
  (t_conso_val.xls = values, t_conso_vol.xls = chained volumes), NOT in SDMX. We
  scrape and cache those (`conso_detail`, `fr_hce_panels_detail`); needs `xlrd`.
  `fr_hce_panels(level="detail")` (the default) uses the ~40-product panel and
  degrades gracefully to A17 when the Excel backbone is unreachable (host blocked,
  no `xlrd`, or no cache). Refresh with `scripts/fetch_insee_conso.py`.
"""

from __future__ import annotations

import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import pandas as pd

from .datasources import (REPO_ROOT, _request, _write_provenance, ApiError,
                          HostBlockedError)

INSEE_SDMX_BASE = "https://bdm.insee.fr/series/sdmx"
RAW_INSEE = REPO_ROOT / "data" / "raw" / "insee"

#: Dataflow + key for "household consumption by A17 product, quarterly".
CNT_FLOW = "CNT-2020-OPERATIONS"
#: FREQ=T, OPERATION=P3M (5th dimension), everything else wildcarded.
CNT_P3M_KEY = "T....P3M......."

# ---------------------------------------------------------------------------
# Detailed quarterly "Consommation des ménages — par produit" Excel release.
# ---------------------------------------------------------------------------
# The SDMX/BDM quarterly consumption is published ONLY at A17 (~17 products).
# The finer ~40-product quarterly panel lives in the "Consommation des ménages"
# *Insee Résultats* release as two Excel tables (values + chained volumes):
#     .../fichier/{release}/t_conso_val.xls   (V — current-price values, EUR m)
#     .../fichier/{release}/t_conso_vol.xls   (L — previous-year-chained volumes)
# The release id changes every quarter; discover the latest from the landing
# page (Statistiques > Consommation des ménages, Insee Résultats) and bump
# CONSO_RELEASE. This backbone is NOT in SDMX, so unlike the A17 path we scrape
# the two .xls files (needs `xlrd`; run from a machine that can reach insee.fr —
# this sandbox blocks the host). Everything downstream (deflator, weights) is
# identical to the A17 port; only the cross-section is finer.
CONSO_RELEASE = "8958309"          # Insee Résultats, published 2026-04 (2026 Q1)
CONSO_FILE_URL = "https://www.insee.fr/fr/statistiques/fichier/{release}/{name}"
CONSO_FILES = {"V": "t_conso_val.xls", "L": "t_conso_vol.xls"}
_STEM_DETAIL = "fr_cnt_conso_detail"   # cache stem under data/raw/insee/

#: Label fragments marking non-leaf rows (grand total / section headers) that
#: must be dropped so the ~40 products don't double-count in the weights. The
#: "par produit" tables are essentially a flat product list plus a total line;
#: matching is accent/'-insensitive and case-insensitive (see _is_total_row).
_CONSO_TOTAL_MARKERS = (
    "consommation des menages", "consommation finale", "depense de consommation",
    "depenses de consommation", "total", "ensemble",
)

#: The 17 A17 leaf products (household consumption). PCHTR (tourism balance)
#: is deliberately not a "leaf": it is a signed adjustment item, not a product.
A17_LEAVES = ["AZ", "C1", "C2", "C3", "C4", "C5", "DE", "FZ", "GZ",
              "HZ", "IZ", "JZ", "KZ", "LZ", "MN", "OQ", "RU"]

_STEM = "fr_cnt_p3m_a17"  # cache file stem under data/raw/insee/


def _quarter_stamp(period: str) -> pd.Timestamp:
    """'1949-Q1' -> Timestamp('1949-01-01') (quarter start)."""
    y, q = period.split("-Q")
    return pd.Timestamp(int(y), 3 * int(q) - 2, 1)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sdmx_series(xml_text: str) -> list[dict]:
    """Parse SDMX-ML StructureSpecificData into a list of series dicts.

    Each dict holds the <Series> attributes plus 'obs': [(TIME_PERIOD,
    OBS_VALUE), ...]. Namespace-agnostic (INSEE uses a structure-specific
    namespace per dataflow).
    """
    root = ET.fromstring(xml_text)
    out = []
    for el in root.iter():
        if _localname(el.tag) != "Series":
            continue
        rec = dict(el.attrib)
        rec["obs"] = [(o.get("TIME_PERIOD"), o.get("OBS_VALUE"))
                      for o in el if _localname(o.tag) == "Obs"]
        out.append(rec)
    return out


def _strip_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(s))
                   if not unicodedata.combining(c))


def _norm(s: str) -> str:
    """lower-case, accent-stripped, whitespace-collapsed — for label matching."""
    return " ".join(_strip_accents(s).lower().split())


def _is_total_row(label: str) -> bool:
    n = _norm(label)
    return any(m in n for m in _CONSO_TOTAL_MARKERS)


_PERIOD_RE = __import__("re").compile(
    r"(?P<y>(19|20)\d{2})\s*[-_/ ]?\s*[tqTQ]\s*(?P<q>[1-4])"
    r"|[tqTQ]\s*(?P<q2>[1-4])\s*[-_/ ]?\s*(?P<y2>(19|20)\d{2})"
)


def _period_from_cell(cell) -> Optional[str]:
    """Parse one header cell into canonical 'YYYY-Qn', or None if not a period.

    Handles '2024-T1', '2024 T1', 'T1 2024', '2024Q1', '2024-1', etc. Pure
    years (no quarter) return None here — two-row year/quarter headers are
    stitched together in `_detect_header`."""
    if cell is None:
        return None
    s = str(cell).strip()
    m = _PERIOD_RE.search(s)
    if not m:
        return None
    y = m.group("y") or m.group("y2")
    q = m.group("q") or m.group("q2")
    if y and q:
        return f"{int(y)}-Q{int(q)}"
    return None


def _year_from_cell(cell) -> Optional[int]:
    s = str(cell).strip()
    m = __import__("re").fullmatch(r"(19|20)\d{2}(\.0)?", s)
    return int(float(s)) if m else None


def _detect_header(grid: "pd.DataFrame"):
    """Locate the period header in a raw INSEE t_conso grid.

    Returns (label_col, period_by_col) where `period_by_col` maps a column index
    to a canonical 'YYYY-Qn'. Supports a single header row ('2024-T1' cells) and
    a two-row header (a year row spanning four quarter columns 'T1'..'T4').
    Raises ValueError if no quarterly header can be found (the caller then dumps
    a diagnostic)."""
    import re
    nrows, ncols = grid.shape

    # 1) single-row header: the row with the most parseable 'YYYY-Qn' cells.
    best_row, best_map = None, {}
    for r in range(min(nrows, 25)):
        m = {c: p for c in range(ncols)
             if (p := _period_from_cell(grid.iat[r, c])) is not None}
        if len(m) > len(best_map):
            best_row, best_map = r, m
    if best_map and len(best_map) >= 3:
        label_col = _detect_label_col(grid, best_row)
        return label_col, best_map

    # 2) two-row header: a 'quarter' row (T1..T4 repeating) under a 'year' row.
    for r in range(1, min(nrows, 25)):
        qcols = {}
        for c in range(ncols):
            mq = re.fullmatch(r"\s*[tqTQ]\s*([1-4])\s*", str(grid.iat[r, c]))
            if mq:
                qcols[c] = int(mq.group(1))
        if len(qcols) >= 4:
            # carry the year from the row above, forward-filling across columns
            years, cur = {}, None
            for c in range(ncols):
                y = _year_from_cell(grid.iat[r - 1, c])
                if y is not None:
                    cur = y
                if c in qcols and cur is not None:
                    years[c] = cur
            pmap = {c: f"{years[c]}-Q{qcols[c]}" for c in qcols if c in years}
            if len(pmap) >= 4:
                return _detect_label_col(grid, r), pmap

    raise ValueError("no quarterly period header found in INSEE t_conso grid")


def _detect_label_col(grid: "pd.DataFrame", header_row: int) -> int:
    """The product-label column: the left-most column that is mostly text in the
    rows below the header."""
    nrows, ncols = grid.shape
    best_col, best_score = 0, -1.0
    for c in range(min(ncols, 4)):
        vals = grid.iloc[header_row + 1:, c]
        txt = sum(1 for v in vals if isinstance(v, str) and v.strip()
                  and _period_from_cell(v) is None
                  and not _is_number(v))
        score = txt / max(len(vals), 1)
        if score > best_score:
            best_col, best_score = c, score
    return best_col


def _is_number(v) -> bool:
    try:
        float(str(v).replace(" ", "").replace(" ", "").replace(",", "."))
        return True
    except (TypeError, ValueError):
        return False


def _to_float(v):
    if v is None:
        return None
    s = (str(v).replace(" ", "").replace("\xa0", "").replace(" ", "")
         .replace(",", "."))
    if s in ("", "-", "nd", "n/a", "..", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_conso_xls(path, valo: str) -> list[dict]:
    """Parse one INSEE 't_conso_{val,vol}.xls' into tidy product rows.

    Returns a list of dicts {product, label, valorisation, period, value}. The
    parser is layout-tolerant (auto-detects the period header row/orientation
    and the product-label column) because the exact sheet geometry can shift
    between releases; it drops the grand-total / section rows (`_is_total_row`)
    so only the ~40 product leaves remain. Requires `xlrd` for the legacy .xls.
    """
    import pandas as pd
    sheets = pd.read_excel(path, sheet_name=None, header=None, engine="xlrd")
    # pick the sheet with the most numeric cells (the data sheet)
    def _numscore(g):
        return int(sum(_is_number(g.iat[i, j])
                       for i in range(min(g.shape[0], 60))
                       for j in range(min(g.shape[1], 60))))
    grid = max(sheets.values(), key=_numscore)
    rows = _rows_from_grid(grid, valo)
    if not rows:
        raise ApiError("INSEE", f"parsed 0 product rows from {path} — the "
                       f"t_conso layout may have changed; run "
                       f"scripts/fetch_insee_conso.py --diagnose to inspect it.")
    return rows


def _rows_from_grid(grid: "pd.DataFrame", valo: str) -> list[dict]:
    """Grid -> tidy product rows (the file-independent core of parse_conso_xls).

    Split out so the auto-detection can be unit-tested on a synthetic grid
    without a binary .xls. Drops total/header rows and non-data rows."""
    label_col, pmap = _detect_header(grid)
    rows, seen = [], {}
    for r in range(grid.shape[0]):
        label = grid.iat[r, label_col]
        if not (isinstance(label, str) and label.strip()):
            continue
        label = label.strip()
        if _period_from_cell(label) is not None or _is_number(label):
            continue
        if _is_total_row(label):
            continue
        # a data row needs at least one numeric value in the period columns
        vals = {p: _to_float(grid.iat[r, c]) for c, p in pmap.items()}
        if not any(v is not None for v in vals.values()):
            continue
        base = _slug(label)
        code = base if base not in seen else f"{base}_{seen[base]}"
        seen[base] = seen.get(base, 0) + 1
        for period, value in vals.items():
            if value is not None:
                rows.append({"product": code, "label": label,
                             "valorisation": valo, "period": period,
                             "value": value})
    return rows


def _slug(label: str) -> str:
    import re
    s = _strip_accents(label).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or "produit"


class InseeClient:
    """Minimal INSEE BDM SDMX client (cache-first + provenance).

    `p3m_a17()` returns the tidy quarterly household-consumption-by-product
    frame; `labels()` the {A17 code: label} map (French by default -- INSEE's
    own labels; English variants are stored alongside in the meta sidecar).
    """

    def __init__(self, cache_dir: Path = RAW_INSEE):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._tidy: Optional[pd.DataFrame] = None
        self._meta: Optional[dict] = None

    # -- paths ---------------------------------------------------------------
    @property
    def _csv(self) -> Path:
        return self.cache_dir / f"{_STEM}.csv"

    @property
    def _meta_path(self) -> Path:
        return self.cache_dir / f"{_STEM}.meta.json"

    # -- fetch + parse (runs on a machine that can reach bdm.insee.fr) --------
    def _fetch(self) -> None:
        url = f"{INSEE_SDMX_BASE}/data/{CNT_FLOW}/{CNT_P3M_KEY}"
        resp = _request("GET", url, provider="INSEE", timeout=180)
        xml_text = resp.text
        series = [s for s in parse_sdmx_series(xml_text)
                  if str(s.get("CNA_PRODUIT", "")).startswith("A17-")]
        if not series:
            raise ApiError("INSEE", f"no A17 P3M series in response from {url} "
                                    f"(got {len(xml_text)} bytes)")
        # keep the raw XML for auditability
        (self.cache_dir / f"{_STEM}.xml").write_text(xml_text, encoding="utf-8")

        def midseg(title: str) -> str:
            parts = [p.strip() for p in str(title).split(" - ")]
            return parts[1] if len(parts) >= 2 else str(title)

        meta, rows = {}, []
        for s in series:
            code, valo = s["CNA_PRODUIT"], s["VALORISATION"]
            obs = sorted(s["obs"])
            meta[f"{code}.{valo}"] = {
                "cna_produit": code, "valorisation": valo,
                "idbank": s.get("IDBANK"),
                "start": obs[0][0], "end": obs[-1][0], "n": len(obs),
                "unit_mult": int(s.get("UNIT_MULT", 6)),
                "last_update": s.get("LAST_UPDATE"),
                "title_fr": s.get("TITLE_FR"), "title_en": s.get("TITLE_EN"),
                "label_fr": midseg(s.get("TITLE_FR")),
                "label_en": midseg(s.get("TITLE_EN")),
            }
            rows += [(code, valo, s.get("IDBANK"), t, v) for t, v in obs]
        tidy = pd.DataFrame(rows, columns=["cna_produit", "valorisation",
                                           "idbank", "period", "value"])
        tidy.sort_values(["cna_produit", "valorisation", "period"], inplace=True)
        tidy.to_csv(self._csv, index=False)
        self._meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        _write_provenance(self._csv, url, {})

    # -- public API ------------------------------------------------------------
    def p3m_a17(self, force: bool = False) -> pd.DataFrame:
        """Tidy quarterly P3M-by-A17 frame (cache-first).

        Columns: cna_produit ('A17-AZ', ...), valorisation ('V' | 'L'),
        idbank, period ('1949-Q1'), value (float, EUR millions), date
        (quarter-start Timestamp).
        """
        if self._tidy is not None and not force:
            return self._tidy
        if force or not self._csv.exists():
            self._fetch()
        df = pd.read_csv(self._csv, dtype={"idbank": str})
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = df["period"].map(_quarter_stamp)
        self._tidy = df
        return df

    def meta(self) -> dict:
        """Per-series metadata (idbank, titles, labels) from the sidecar."""
        if self._meta is None:
            if not self._meta_path.exists():
                self.p3m_a17()  # populates the cache (or raises clearly)
            self._meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        return self._meta

    def labels(self, lang: str = "fr") -> dict[str, str]:
        """{A17 short code ('AZ', ...): product label}. INSEE labels; lang='en'
        switches to INSEE's English titles."""
        key = "label_en" if lang == "en" else "label_fr"
        out = {}
        for m in self.meta().values():
            code = m["cna_produit"].replace("A17-", "")
            out[code] = m[key]
        return out

    # -- detailed ~40-product Excel port (t_conso_val / t_conso_vol) ----------
    @property
    def _detail_csv(self) -> Path:
        return self.cache_dir / f"{_STEM_DETAIL}.csv"

    def _fetch_detail(self, release: str = CONSO_RELEASE) -> None:
        """Download + parse the two t_conso .xls files into one tidy CSV.

        Runs from a machine that can reach insee.fr; caches the raw .xls (for
        auditability) and the parsed long frame. Raises HostBlockedError with a
        clear message when the host is firewalled (this project's sandbox)."""
        all_rows: list[dict] = []
        for valo, name in CONSO_FILES.items():
            url = CONSO_FILE_URL.format(release=release, name=name)
            resp = _request("GET", url, provider="INSEE", timeout=180)
            raw = self.cache_dir / name
            raw.write_bytes(resp.content)
            all_rows.extend(parse_conso_xls(raw, valo))
        tidy = pd.DataFrame(all_rows)
        tidy.sort_values(["valorisation", "product", "period"], inplace=True)
        tidy.to_csv(self._detail_csv, index=False)
        _write_provenance(self._detail_csv,
                          CONSO_FILE_URL.format(release=release, name="t_conso_*.xls"),
                          {"release": release})

    def conso_detail(self, force: bool = False,
                     release: str = CONSO_RELEASE) -> pd.DataFrame:
        """Tidy quarterly detailed-product consumption frame (cache-first).

        Columns: product (slug), label, valorisation ('V'|'L'), period
        ('YYYY-Qn'), value (EUR m), date (quarter-start Timestamp)."""
        if force or not self._detail_csv.exists():
            self._fetch_detail(release=release)
        df = pd.read_csv(self._detail_csv)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = df["period"].map(_quarter_stamp)
        return df

    def detail_labels(self) -> dict[str, str]:
        """{product slug: INSEE product label} for the detailed port."""
        df = self.conso_detail()
        return dict(zip(df["product"], df["label"]))


# ---------------------------------------------------------------------------
# Panels for the supply/demand decomposition (ism.decomp_ports.build_fr_panels)
# ---------------------------------------------------------------------------
def _pivot(df: pd.DataFrame, valo: str, codes: list[str]) -> pd.DataFrame:
    sub = df[df["valorisation"] == valo].copy()
    sub["code"] = sub["cna_produit"].str.replace("A17-", "", regex=False)
    wide = sub.pivot_table(index="date", columns="code", values="value",
                           aggfunc="first").sort_index()
    return wide[[c for c in codes if c in wide.columns]]


def fr_hce_panels_a17(client: Optional[InseeClient] = None, force: bool = False):
    """A17 (~17-product) quarterly (nominal, volume, labels) panels.

    The France analogue of BEA 2.4.5U/2.4.3U for the decomposition: `nominal`
    is P3M at current prices (V, EUR m) and `volume` the chained
    previous-year-price volumes (L, EUR m), for the 17 A17 leaf products,
    quarterly from 1949 Q1, CVS-CJO. Labels are INSEE's French product labels
    (English available via client.labels('en')). Deflator construction happens
    in ism.decomp_ports.panels_from_nominal_real.
    """
    client = client or InseeClient()
    df = client.p3m_a17(force=force)
    nominal = _pivot(df, "V", A17_LEAVES)
    volume = _pivot(df, "L", A17_LEAVES)
    labels = {k: v for k, v in client.labels("fr").items() if k in A17_LEAVES}
    return nominal, volume, labels


def _pivot_detail(df: pd.DataFrame, valo: str) -> pd.DataFrame:
    sub = df[df["valorisation"] == valo]
    return sub.pivot_table(index="date", columns="product", values="value",
                           aggfunc="first").sort_index()


def fr_hce_panels_detail(client: Optional[InseeClient] = None, force: bool = False):
    """Detailed (~40-product) quarterly (nominal, volume, labels) panels.

    Reads INSEE's quarterly "Consommation des ménages — par produit" Excel
    tables (t_conso_val = V, t_conso_vol = L). Same contract as the A17 panel,
    only a finer cross-section (~40 products vs 17). Self-fetches + caches on a
    machine that can reach insee.fr; raises HostBlockedError otherwise.
    """
    client = client or InseeClient()
    df = client.conso_detail(force=force)
    nominal = _pivot_detail(df, "V")
    volume = _pivot_detail(df, "L")
    cols = [c for c in nominal.columns if c in volume.columns]
    labels = client.detail_labels()
    return nominal[cols], volume[cols], {c: labels.get(c, c) for c in cols}


def fr_hce_panels(client: Optional[InseeClient] = None, force: bool = False,
                  level: str = "detail"):
    """Quarterly (nominal, volume, labels) household-consumption panels.

    `level="detail"` (default) uses the ~40-product INSEE Excel tables; if that
    backbone is unreachable (host blocked / `xlrd` missing / layout change / no
    cache), it **degrades gracefully to the A17 SDMX panel** (~17 products) so
    the pipeline still builds. `level="a17"` forces the coarse SDMX panel.
    """
    client = client or InseeClient()
    if level == "a17":
        return fr_hce_panels_a17(client, force=force)
    if level != "detail":
        raise ValueError("level must be 'detail' or 'a17'")
    try:
        return fr_hce_panels_detail(client, force=force)
    except (HostBlockedError, ApiError, ValueError, FileNotFoundError,
            ImportError, OSError) as exc:
        import warnings
        warnings.warn(
            f"[fr] detailed ~40-product panel unavailable ({type(exc).__name__}: "
            f"{exc}); falling back to the A17 (~17-product) SDMX panel. Run "
            f"scripts/fetch_insee_conso.py from a machine with insee.fr access "
            f"(and `pip install xlrd`) to enable the finer cross-section.",
            RuntimeWarning, stacklevel=2)
        return fr_hce_panels_a17(client, force=force)


def validate_conso_vs_a17(client: Optional[InseeClient] = None,
                          n_quarters: int = 8) -> pd.DataFrame:
    """Cross-check: sum of detailed products vs the A17 total, recent quarters.

    Nominal (V) is additive, so Σ(detailed products) should track the A17 sum
    closely each quarter (small gaps from rounding / a residual 'other' line).
    Returns a per-quarter frame [detail_sum, a17_sum, pct_gap] for the last
    `n_quarters` — the sanity signal to trust the scrape before wiring it in.
    """
    client = client or InseeClient()
    det = client.conso_detail()
    det_v = det[det["valorisation"] == "V"].groupby("date")["value"].sum()
    a17 = client.p3m_a17()
    a17_v = (a17[a17["valorisation"] == "V"]
             .groupby("date")["value"].sum())            # 17 leaves + PCHTR
    idx = det_v.index.intersection(a17_v.index)[-n_quarters:]
    out = pd.DataFrame({"detail_sum": det_v.reindex(idx),
                        "a17_sum": a17_v.reindex(idx)})
    out["pct_gap"] = 100.0 * (out["detail_sum"] / out["a17_sum"] - 1.0)
    return out


def fr_hce_deflator_yoy(client: Optional[InseeClient] = None,
                        force: bool = False) -> pd.Series:
    """Y/y % change of the total-P3M implicit deflator (context series).

    The dataflow carries no pre-aggregated P3M total at FREQ=T, so the total is
    the sum over all 18 A17 series (17 leaves + PCHTR, the tourism balance) --
    exact for current prices, an approximation for the chained volumes (chained
    volumes are non-additive; documented, and immaterial for a y/y context
    series).
    """
    client = client or InseeClient()
    df = client.p3m_a17(force=force)
    tot_v = df[df["valorisation"] == "V"].groupby("date")["value"].sum()
    tot_l = df[df["valorisation"] == "L"].groupby("date")["value"].sum()
    defl = (100.0 * tot_v / tot_l).sort_index()
    return (100.0 * (defl / defl.shift(4) - 1.0)).rename("fr_hce_deflator_yoy")
