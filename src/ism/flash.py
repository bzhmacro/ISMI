"""
ism.flash
=========

Preliminary ("flash") inflation prints for the euro-area gauges, published by
the national statistics offices about two weeks before the final HICP that the
category panels are built from.

A flash print is NOT a category panel: it is the headline plus, at best, four
or five special aggregates. So it never enters the momentum, trimmed-mean or
category-level breakdown computations. It is used for exactly two things:

  1. a provisional headline marker after the last final month on every chart
     that draws the headline, and
  2. a provisional month on the Breakdown page's special-aggregate grouping
     (food incl. alcohol & tobacco / energy / non-energy industrial goods /
     services), drawn hatched.

When the final print lands, the backbone's last final month catches up with the
flash month and the exporter stops attaching it -- the flash is replaced, never
merged.

Sources (all keyless except none needed):

  fr  INSEE BDM SDMX: provisional values (OBS_STATUS "P") are loaded into the
      regular series on flash day. CPI aggregates (food, tobacco, energy,
      manufactured products, services) as indices, so monthly AND annual
      changes are exact; HICP all-items index likewise.
  de  Destatis flash press release (HTML; GENESIS is not updated until the
      final). Annual rates only, CPI basis: overall, services, goods, energy,
      food; HICP annual and monthly rate from the release text.
  es  INE Tempus API: "Preview" values in the HICP/CPI tables on flash day.
      Headline HICP monthly and annual change.
  it  Istat flash press release + PDF (pypdf): HICP headline and Table 5, the
      HICP special aggregates themselves, monthly and annual -- the only flash
      whose components are on the HICP basis.

Components are national-CPI aggregates for France and Germany, mapped onto the
HICP special aggregates; Italy's are the HICP aggregates; the page says which.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from typing import Optional

from .datasources import _request

UA = {"User-Agent": "Mozilla/5.0 (ISM replication; +https://github.com/bzhmacro/ISMI)"}
AGGS = ("FOOD", "NRG", "IGD_NNRG", "SERV")

# ---------------------------------------------------------------------------
# France -- INSEE
# ---------------------------------------------------------------------------
INSEE_SERIES = {             # IDBANK -> role (CPI base 2025 unless noted)
    "011812231": "HICP",     # HICP all items (IPCH-2025)
    "011814630": "CPI",      # CPI all items
    "011813717": "food",     # food (alimentation)
    "011814110": "tobacco",
    "011813864": "NRG",      # energy
    "011813780": "IGD_NNRG", # manufactured products
    "011813906": "SERV",     # services
}


def _insee_series() -> dict:
    ids = "+".join(INSEE_SERIES)
    url = f"https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{ids}?lastNObservations=14"
    x = _request("GET", url, provider="INSEE", timeout=90).text
    out = {}
    for attrs, body in re.findall(r"<Series ([^>]*)>(.*?)</Series>", x, re.S):
        idb = re.search(r'IDBANK="(\d+)"', attrs).group(1)
        obs = {}
        for o in re.findall(r"<Obs ([^>]*)/>", body):
            t = re.search(r'TIME_PERIOD="([^"]+)"', o).group(1)
            v = float(re.search(r'OBS_VALUE="([^"]+)"', o).group(1))
            st = (re.search(r'OBS_STATUS="(\w)"', o) or [None, ""])[1]
            obs[t] = (v, st)
        out[INSEE_SERIES[idb]] = obs
    return out


def _changes(obs: dict, t: str) -> dict:
    y, m = map(int, t.split("-"))
    prev = f"{y - (m == 1)}-{12 if m == 1 else m - 1:02d}"
    last_y = f"{y - 1}-{m:02d}"
    v = obs[t][0]
    out = {}
    if prev in obs:
        out["mom"] = round(100 * (v / obs[prev][0] - 1), 3)
    if last_y in obs:
        out["yoy"] = round(100 * (v / obs[last_y][0] - 1), 3)
    return out


def fetch_fr(food_tobacco_split: Optional[tuple] = None) -> Optional[dict]:
    """INSEE provisional month, or None when the latest month is final."""
    s = _insee_series()
    hicp = s.get("HICP") or {}
    prov = [t for t, (_, st) in hicp.items() if st == "P"]
    if not prov:
        return None
    t = max(prov)
    comps = {}
    for agg in ("NRG", "IGD_NNRG", "SERV"):
        if t in s.get(agg, {}):
            comps[agg] = _changes(s[agg], t)
    if t in s.get("food", {}) and t in s.get("tobacco", {}):
        f, tb = _changes(s["food"], t), _changes(s["tobacco"], t)
        wf, wt = food_tobacco_split or (0.9, 0.1)
        comps["FOOD"] = {k: round((wf * f[k] + wt * tb[k]) / (wf + wt), 3)
                         for k in f if k in tb}
    return {
        "date": t,
        "headline": _changes(hicp, t),
        "components": comps,
        "components_basis": "INSEE CPI groupings (food+tobacco, energy, "
                            "manufactured products, services)",
        "source": "INSEE, provisional estimate (BDM series, status P)",
        "url": "https://www.insee.fr/en/statistiques/serie/011812231",
    }


# ---------------------------------------------------------------------------
# Germany -- Destatis flash press release
# ---------------------------------------------------------------------------
DESTATIS_CPI_PAGE = ("https://www.destatis.de/EN/Themes/Economy/Prices/"
                     "Consumer-Price-Index/_node.html")
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def _num(s: str) -> Optional[float]:
    s = s.replace(",", "").replace("+", "").replace("−", "-").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_destatis_flash(page: str) -> Optional[dict]:
    """Parse a Destatis flash release ('Inflation rate of +x% expected ...')."""
    title = html.unescape(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
    m = re.search(r"expected in ([A-Za-z]+) (\d{4})", title)
    if not m:
        return None                                   # a final release, not a flash
    t = f"{m.group(2)}-{_MONTHS[m.group(1).lower()]:02d}"
    tb = re.findall(r"<table.*?</table>", page, re.S)
    rows = {}
    if tb:
        for r in re.findall(r"<tr.*?</tr>", tb[0], re.S):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)]
            if len(cells) >= 3:
                name = re.sub(r"\d+$", "", cells[0]).strip().lower()
                rows[name] = (_num(cells[1]), _num(cells[-1]))     # weight, latest yoy
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    # "Harmonised index of consumer prices, September 2026: +3.3% on the same
    #  month a year earlier (provisional) +0.6% on the previous month ..."
    headline = {}
    hi = re.search(r"Harmonised index of consumer prices, [A-Za-z]+ \d{4}:(.{0,200})", text)
    if hi:
        seg = hi.group(1)
        for val, what in re.findall(r"([+\u2212-]?\d+[.,]\d)\s*%\s*on the (same month a year earlier|previous month)", seg):
            headline["yoy" if what.startswith("same") else "mom"] = _num(val.replace(",", "."))
    comps = {}
    g, e, f = rows.get("goods"), rows.get("energy"), rows.get("food")
    if rows.get("services"):
        comps["SERV"] = {"yoy": rows["services"][1]}
    if e:
        comps["NRG"] = {"yoy": e[1]}
    if f:
        comps["FOOD"] = {"yoy": f[1]}
    if g and e and f and None not in (g + e + f):
        w = g[0] - e[0] - f[0]
        if w > 0:
            comps["IGD_NNRG"] = {"yoy": round((g[0] * g[1] - e[0] * e[1] - f[0] * f[1]) / w, 3)}
    if not headline and not comps:
        return None
    return {"date": t, "headline": headline, "components": comps,
            "components_basis": "Destatis CPI flash: services, energy, food; "
                                "non-energy goods = goods less energy and food "
                                "(annual rates only)"}


def fetch_de() -> Optional[dict]:
    node = _request("GET", DESTATIS_CPI_PAGE, provider="Destatis", headers=UA,
                    timeout=60).text
    links = sorted(set(re.findall(r'href="(EN/Press/\d{4}/\d{2}/PE\d{2}_\d+_611\.html)', node)),
                   key=lambda u: int(re.search(r"PE\d{2}_(\d+)_", u).group(1)), reverse=True)
    for href in links[:3]:
        url = "https://www.destatis.de/" + href
        page = _request("GET", url, provider="Destatis", headers=UA, timeout=60).text
        rec = parse_destatis_flash(page)
        if rec:
            rec.update(source="Destatis flash estimate (press release)", url=url)
            return rec
        return None          # newest CPI release is a final -> no pending flash
    return None


# ---------------------------------------------------------------------------
# Spain -- INE Tempus
# ---------------------------------------------------------------------------
INE_HICP_TABLE = 76102       # HICP national indices: overall and by ECOICOP group


def fetch_es() -> Optional[dict]:
    url = f"https://servicios.ine.es/wstempus/js/EN/DATOS_TABLA/{INE_HICP_TABLE}?nult=2&tip=A"
    data = _request("GET", url, provider="INE", timeout=90).json()
    head, t = {}, None
    for s in data if isinstance(data, list) else []:
        name = s.get("Nombre", "")
        if not name.startswith("National Total. Overall index."):
            continue
        for o in s.get("Data", []):
            if o.get("T3_TipoDato") != "Preview":
                continue
            t = f"{o['Anyo']}-{int(str(o['T3_Periodo']).lstrip('M')):02d}"
            if "Monthly change" in name:
                head["mom"] = o["Valor"]
            elif "Annual change" in name:
                head["yoy"] = o["Valor"]
    if not head or t is None:
        return None
    return {"date": t, "headline": head, "components": {},
            "components_basis": "INE's flash gives the headline only",
            "source": "INE, flash estimate (Tempus API, 'Preview')",
            "url": "https://www.ine.es/dyngs/INEbase/en/operacion.htm?c=Estadistica_C&cid=1254736176803"}


# ---------------------------------------------------------------------------
# Italy -- Istat flash press release + PDF
# ---------------------------------------------------------------------------
ISTAT_TAG_PAGE = "https://www.istat.it/en/?tag=consumer-prices"
_SIGNED = r"([+\-\u2212]?\d+[.,]\d|0[.,]0)"
#: Table 5 of the flash PDF: the HICP special aggregates themselves.
ISTAT_AGG_ROWS = {"Food, alcohol and tobacco": "FOOD", "Energy": "NRG",
                  "Non-energy industrial goods": "IGD_NNRG", "Services": "SERV"}


def parse_istat_flash_pdf(text: str) -> dict:
    """HICP headline + Table 5 special aggregates from the flash PDF's text.

    Table rows read: weight, index, m/m (this month), m/m (previous),
    y/y (this month), y/y (previous)."""
    out = {"headline": {}, "components": {}}
    num = lambda v: float(v.replace(",", ".").replace("\u2212", "-"))
    m = re.search(r"Italian harmoni[sz]ed index of consumer prices \(HICP\)\s+"
                  r"(\d+[.,]\d)\s+" + _SIGNED + r"\s+" + _SIGNED, text)
    if m:
        out["headline"] = {"mom": num(m.group(2)), "yoy": num(m.group(3))}
    i = text.find("BY SPECIAL AGGREGATES")
    seg = text[i:i + 4000] if i >= 0 else ""
    for label, agg in ISTAT_AGG_ROWS.items():
        r = re.search(r"^\s*" + re.escape(label) + r":?\s+[\d,.]+\s+\d+[.,]\d\s+"
                      + _SIGNED + r"\s+" + _SIGNED + r"\s+" + _SIGNED, seg, re.M)
        if r:
            out["components"][agg] = {"mom": num(r.group(1)), "yoy": num(r.group(3))}
    return out


def fetch_it() -> Optional[dict]:
    tag = _request("GET", ISTAT_TAG_PAGE, provider="Istat", headers=UA, timeout=60).text
    rel = set(re.findall(r'https://www\.istat\.it/en/press-release/'
                         r'consumer-prices-provisional-data-([a-z]+)-(\d{4})/', tag))
    if not rel:
        return None
    month, year = max(rel, key=lambda r: (int(r[1]), _MONTHS[r[0]]))
    t = f"{year}-{_MONTHS[month]:02d}"
    url = f"https://www.istat.it/en/press-release/consumer-prices-provisional-data-{month}-{year}/"
    page = _request("GET", url, provider="Istat", headers=UA, timeout=60).text
    pdf = re.search(r'href="(https://www\.istat\.it/wp-content/uploads/[^"]+Prov[^"]*\.pdf)"', page)
    rec = {"headline": {}, "components": {}}
    if pdf:
        import io
        from pypdf import PdfReader
        raw = _request("GET", pdf.group(1), provider="Istat", headers=UA, timeout=90).content
        text = "\n".join(pg.extract_text(extraction_mode="layout")
                         for pg in PdfReader(io.BytesIO(raw)).pages)
        rec = parse_istat_flash_pdf(text)
    if not rec["headline"]:                       # fall back on the release text
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
        m = re.search(r"\(HICP\) recorded a month-on-month change of " + _SIGNED +
                      r"%.*?year-on-year (?:increase|decrease|change) of " + _SIGNED, txt)
        if m:
            rec["headline"] = {"mom": float(m.group(1)), "yoy": float(m.group(2))}
    if not rec["headline"]:
        return None
    return {"date": t, **rec,
            "components_basis": "Istat HICP special aggregates (flash Table 5) -- "
                                "same basis as the final HICP",
            "source": "Istat, preliminary estimate (press release)", "url": url}


FETCHERS = {"fr": fetch_fr, "de": fetch_de, "es": fetch_es, "it": fetch_it}


def fetch_flash(geo: str, **kw) -> Optional[dict]:
    """Latest preliminary print for a gauge, or None. Never raises."""
    fn = FETCHERS.get(geo)
    if fn is None:
        return None
    try:
        rec = fn(**kw) if kw else fn()
    except Exception as exc:                          # noqa: BLE001
        print(f"  [{geo}] flash unavailable: {type(exc).__name__}: {exc}")
        return None
    if rec:
        rec["fetched_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    return rec
