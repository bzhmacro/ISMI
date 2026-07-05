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
"""

from __future__ import annotations

import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import pandas as pd

from .datasources import REPO_ROOT, _request, _write_provenance, ApiError

INSEE_SDMX_BASE = "https://bdm.insee.fr/series/sdmx"
RAW_INSEE = REPO_ROOT / "data" / "raw" / "insee"

#: Dataflow + key for "household consumption by A17 product, quarterly".
CNT_FLOW = "CNT-2020-OPERATIONS"
#: FREQ=T, OPERATION=P3M (5th dimension), everything else wildcarded.
CNT_P3M_KEY = "T....P3M......."

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


# ---------------------------------------------------------------------------
# Panels for the supply/demand decomposition (ism.decomp_ports.build_fr_panels)
# ---------------------------------------------------------------------------
def _pivot(df: pd.DataFrame, valo: str, codes: list[str]) -> pd.DataFrame:
    sub = df[df["valorisation"] == valo].copy()
    sub["code"] = sub["cna_produit"].str.replace("A17-", "", regex=False)
    wide = sub.pivot_table(index="date", columns="code", values="value",
                           aggfunc="first").sort_index()
    return wide[[c for c in codes if c in wide.columns]]


def fr_hce_panels(client: Optional[InseeClient] = None, force: bool = False):
    """Quarterly (nominal, volume, labels) household-consumption panels.

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
