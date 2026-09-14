"""
ism.wage_pipeline
=================

Assembles the quarterly country panels the wage engine estimates on, and the
component series behind the Effective Wage Index.

One panel per country, with the columns ``ism.wage_engine`` expects:

    gw       nominal wage growth, annualised % (400 dlog)
    gp       headline consumer price inflation, annualised %
    gp_core  core consumer price inflation, annualised %
    pi_yoy   four-quarter consumer price inflation, %
    grpe     relative energy price vs wages, annualised % (B&B convention)
    grpf     relative food price vs wages, annualised %
    slack    labour-market tightness: NAIRU minus unemployment, pp
    gpty     trend productivity growth, annualised % (8q moving average)
    dmw      growth of the statutory minimum wage, annualised %
    h        transfer impulse: change in government cash transfers to
             households, annualised, as a percent of disposable income
    lambda   institutional indexation intensity (Eq. W3)
    pistar   trend inflation (Eq. W1)
    catchup  realised minus previously expected inflation (Eq. W2)

Country coverage and why it is what it is
-----------------------------------------
    US  1960Q1-   FRED serves everything back to 1959 and the 1970s COLA
                  episode is documented at contract level, so the US carries
                  the historical identification.
    UK  1971Q1-   RPI (ONS CDKO) from 1947 and the LFS unemployment rate from
                  1971. Earnings before 2000 come from the AEI-spliced whole
                  economy series; the 1973-74 threshold agreements are inside
                  the sample.
    FR  1977Q1-   INSEE's SMB (base wage, ex-bonus) starts 1977 and the SMIC
                  goes back to 1951; the quarterly household accounts start
                  1980, so the transfer term is available from 1980.
    DE  1991Q1-   Reunified Germany. West German data exist earlier but splice
                  badly across reunification, and the German story in this
                  paper is a 2015-2024 story (minimum wage, one-off bonuses),
                  so the shorter sample costs little.

Anything a country lacks is simply absent from its panel; the engine includes
only the columns it finds, so a missing minimum wage or a missing vacancy
series narrows a specification rather than breaking a build.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import wage_sources as src
from .wage_engine import (PPY, WageConfig, catchup, indexation_intensity,
                          real_wage_gap, trend_inflation)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config"

COUNTRIES = ("US", "UK", "FR", "DE")
REFERENCE = ("BE", "IT", "ES")
ALL_COUNTRIES = COUNTRIES + REFERENCE
START = {"US": "1960-01-01", "UK": "1963-01-01", "FR": "1960-01-01", "DE": "1960-01-01",
         "BE": "1960-01-01", "IT": "1960-01-01", "ES": "1960-01-01"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def to_quarterly(s: pd.Series, how: str = "mean") -> pd.Series:
    """Monthly (or higher-frequency) series -> quarterly, period-start indexed."""
    if s.empty:
        return s
    r = s.resample("QS")
    out = r.mean() if how == "mean" else (r.last() if how == "last" else r.sum())
    return out.dropna()


def ann_growth(s: pd.Series) -> pd.Series:
    """Annualised log growth in percent: 400 * dlog."""
    return (400.0 * np.log(s.astype(float)).diff()).rename(s.name)


def yoy(s: pd.Series, periods: int = PPY) -> pd.Series:
    """Four-quarter log change in percent."""
    return (100.0 * np.log(s.astype(float)).diff(periods)).rename(s.name)


def splice(new: Optional[pd.Series], old: Optional[pd.Series]) -> Optional[pd.Series]:
    """Extend ``new`` backwards with the growth rates of ``old``.

    The level of ``new`` is authoritative; ``old`` only supplies the shape
    before ``new`` begins. Requires at least four overlapping observations, so
    the ratio used to rescale is an average rather than a single, possibly
    revised, data point.
    """
    if new is None:
        return old.dropna() if old is not None else None
    if old is None:
        return new.dropna()
    new, old = new.dropna(), old.dropna()
    if new.empty:
        return old
    overlap = new.index.intersection(old.index)
    if len(overlap) < 4:
        return new
    ratio = float((new.loc[overlap] / old.loc[overlap]).iloc[:4].mean())
    back = old.loc[old.index < new.index[0]] * ratio
    return pd.concat([back, new]).sort_index()


def _try(fn, *args, **kwargs):
    """Call ``fn``; return None and warn instead of raising.

    A country panel is assembled from a dozen independent providers. One of
    them being down, renamed or rebased should narrow the panel, not kill the
    build -- the missing column then simply does not appear, and
    ``ism.wage_validate`` reports which ones were absent.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - see docstring
        warnings.warn(f"wage_pipeline: {getattr(fn, '__name__', fn)} failed: {exc}")
        return None


def eurostat_best(dataset: str, dim: str, options: Sequence[str], **filters) -> pd.Series:
    """Eurostat series, trying several codes for one dimension and keeping the
    longest result.

    Eurostat rebases its index datasets every few years (HICP moved from
    2015=100 to 2025=100 during 2026) and retires the old unit code without
    warning. Rather than pin a code that will expire, we ask for each candidate
    and keep whichever comes back with the most observations.
    """
    best, best_n = None, -1
    for opt in options:
        s = _try(src.eurostat, dataset, **{dim: opt}, **filters)
        if s is not None and len(s) > best_n:
            best, best_n = s, len(s)
    if best is None:
        raise src.WageFetchError(f"Eurostat {dataset}: none of {dim}={options} returned data")
    return best


# ---------------------------------------------------------------------------
# Config tables
# ---------------------------------------------------------------------------
def _read_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(CONFIG / name, comment="#")


def load_coverage(country: str, index: pd.DatetimeIndex,
                  cfg: Optional[WageConfig] = None) -> Tuple[pd.DataFrame, pd.Series]:
    """Eq. (W3) inputs: the indexation coverage panel and lambda_t.

    The CSV records coverage at the dates it is documented; between two
    documented dates coverage is linearly interpolated, and outside the
    documented range it is held flat. Interpolation is a modelling choice, not
    a measurement: institutions change on a date, but the *share of employees*
    affected drifts, because contracts expire on a rolling basis. The one place
    this matters -- the UK's 1974 threshold agreements -- is encoded as a step
    with adjacent zero rows, so it is not smoothed away.
    """
    df = _read_csv("indexation_coverage.csv")
    df = df[df["country"] == country]
    if df.empty:
        return pd.DataFrame(index=index), pd.Series(0.0, index=index, name="lambda")
    wide = (df.pivot_table(index="year", columns="channel", values="coverage", aggfunc="last")
              .sort_index())
    wide.index = pd.to_datetime(wide.index.astype(int).astype(str) + "-01-01")
    # Interpolate between documented dates and hold the last one forward, but
    # do NOT back-fill before a channel's first documented observation: an
    # institution that is not recorded before 1993 did not exist before 1993,
    # and filling it backwards silently invents coverage. This matters: Italy's
    # `benchmark` channel is documented only from the 1993 Protocol, and
    # back-filling it added a flat 0.18 to Italian lambda for 1960-1992 --
    # pushing the scala mobile years over the clip at unity and contradicting
    # this module's own statement that missing channels count as zero.
    full = wide.reindex(wide.index.union(index)).interpolate(method="index").ffill()
    for col in full.columns:
        first = wide[col].first_valid_index()
        if first is not None:
            full.loc[full.index < first, col] = 0.0
    full = full.fillna(0.0)
    cov = full.reindex(index)
    lam = indexation_intensity(cov, (cfg or WageConfig()).elasticities)
    return cov, lam


def load_wedge(country: str, index: pd.DatetimeIndex) -> pd.Series:
    """The price-measure CPI wedge of Eq. (W11), in pp of y/y inflation."""
    df = _read_csv("wage_cpi_wedge.csv")
    df = df[df["country"] == country]
    out = pd.Series(0.0, index=index, name="wedge")
    for _, row in df.iterrows():
        per = str(row["period"])
        if "-Q" in per:
            ts = pd.Period(per.replace("-", ""), freq="Q").to_timestamp()
            if ts in out.index:
                out.loc[ts] = float(row["wedge_pp"])
        else:
            year = int(per)
            mask = out.index.year == year
            out.loc[mask] = float(row["wedge_pp"])
    return out


def load_schemes(country: str, index: pd.DatetimeIndex,
                 kinds: Sequence[str] = ("income", "wage")) -> pd.Series:
    """Discretionary scheme spending, annualised, in the country's currency bn.

    Spread evenly over the quarters a scheme is in force. Only ``income`` and
    ``wage`` kinds are summed by default: ``price`` measures do not add to
    nominal household income (they lower the price level instead) and are
    picked up by ``load_wedge``.
    """
    df = _read_csv("wage_schemes.csv")
    df = df[(df["country"] == country) & (df["kind"].isin(kinds))]
    out = pd.Series(0.0, index=index, name="scheme")
    for _, row in df.iterrows():
        cost = float(row.get("cost_bn") or 0.0)
        if cost <= 0:
            continue
        start = pd.Period(str(row["start"]), freq="M").to_timestamp()
        end = pd.Period(str(row["end"]), freq="M").to_timestamp()
        mask = (out.index >= start.to_period("Q").to_timestamp()) & (out.index <= end)
        n = int(mask.sum())
        if n:
            out.loc[mask] += cost / n * PPY   # annualised rate while in force
    return out


def load_shares(country: str, group: str = "all") -> Dict[str, float]:
    """Income-composition weights s_c for Eq. (W10)."""
    df = _read_csv("wage_income_shares.csv")
    row = df[(df["country"] == country) & (df["group"] == group)]
    if row.empty:
        raise KeyError(f"no income shares for {country}/{group}")
    r = row.iloc[-1]
    return {k: float(r[k]) for k in ("wage", "minwage", "benefit", "handout")}


def load_politics(country: str, index: pd.DatetimeIndex) -> pd.DataFrame:
    df = _read_csv("wage_politics.csv")
    df = df[df["country"] == country]
    out = pd.DataFrame(index=index, columns=["populist", "election"], dtype=float).fillna(0.0)
    for _, row in df.iterrows():
        mask = out.index.year == int(row["year"])
        out.loc[mask, "populist"] = float(row["populist"])
        out.loc[mask, "election"] = float(row["election"])
    return out


# ---------------------------------------------------------------------------
# US
# ---------------------------------------------------------------------------
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]


def effective_us_minimum_wage(force: bool = False) -> pd.Series:
    """An employment-weighted effective US minimum wage.

    The federal floor has been $7.25 since July 2009, so a series that uses it
    alone says the American wage floor has been frozen for seventeen years.
    That is false for most American workers: the binding minimum is the higher
    of the federal and the state rate, and by 2026 roughly three fifths of US
    employment is in a state with a higher one.

    We therefore compute

        MW_t = sum_s (E_{s,t} / E_t) * max(MW^federal_t, MW^state_{s,t})

    with state minimum wages from FRED's ``STTMINWG<ST>`` series and state
    employment from ``<ST>NA`` (total nonfarm, thousands). States whose series
    are unavailable fall back to the federal rate, which biases the index
    *down*, never up.

    This is the single most consequential data construction in the US part of
    the paper, and it is the reason the US minimum-wage channel in Eq. (W3) is
    not identically zero after 2009.
    """
    fed = src.fred("FEDMINNFRWG", force=force).resample("MS").ffill()
    mws = src.fred_many([f"STTMINWG{s}" for s in US_STATES], force=force)
    emp = src.fred_many([f"{s}NA" for s in US_STATES], force=force)
    idx = fed.index
    num = pd.Series(0.0, index=idx)
    den = pd.Series(0.0, index=idx)
    for st in US_STATES:
        e = emp.get(f"{st}NA")
        if e is None:
            continue
        e = e.reindex(idx).ffill()
        m = mws.get(f"STTMINWG{st}")
        if m is None:
            binding = fed
        else:
            binding = np.maximum(fed, m.resample("MS").ffill().reindex(idx).ffill().fillna(0.0))
        num = num.add(binding * e, fill_value=0.0)
        den = den.add(e, fill_value=0.0)
    eff = (num / den).replace([np.inf, -np.inf], np.nan)
    eff = eff.where(eff >= fed, fed)   # never below the federal floor
    return eff.rename("effective_minimum_wage").dropna()


def build_us(force: bool = False, effective_mw: bool = True) -> Dict[str, pd.Series]:
    f = lambda sid: src.fred(sid, force=force)  # noqa: E731
    cpi = to_quarterly(f("CPIAUCSL"))
    core = to_quarterly(f("CPILFESL"))
    energy = to_quarterly(f("CPIENGSL"))
    food = to_quarterly(f("CPIUFDSL"))

    # Wages: ECI wages & salaries is the mix-controlled series every wage
    # equation in the literature uses, but FRED carries it only from 2001. We
    # extend it back with average hourly earnings of production and
    # nonsupervisory workers (1964-) and, before that, nonfarm business
    # compensation per hour (1947-). The splice is documented in DECISIONS.md;
    # it is a growth-rate splice, so the level is ECI's throughout.
    eci = to_quarterly(f("ECIWAG"), "last")
    ahe = to_quarterly(f("AHETPI"))
    comp = f("COMPNFB")
    wage = splice(splice(eci, ahe), comp)

    unrate = to_quarterly(f("UNRATE"))
    nairu = to_quarterly(f("NROU"))
    pty = f("OPHNFB")
    transfers = to_quarterly(f("A063RC1"))
    dpi = to_quarterly(f("DPI"))

    mw = None
    if effective_mw:
        mw = _try(effective_us_minimum_wage, force)
    if mw is None:
        mw = f("FEDMINNFRWG")
    mw = to_quarterly(mw)

    cpi_w = _try(f, "CWUR0000SA0")          # CPI-W: the statutory COLA index
    return dict(cpi=cpi, core=core, energy=energy, food=food, wage=wage,
                unrate=unrate, nairu=nairu, pty=to_quarterly(pty, "last"),
                transfers=transfers, dpi=dpi, minwage=mw,
                cpi_w=cpi_w if cpi_w is not None else _try(f, "CPIAUCSL"),
                exp1=to_quarterly(_try(f, "EXPINF1YR")) if True else None,
                exp10=to_quarterly(_try(f, "EXPINF10YR")))


# ---------------------------------------------------------------------------
# UK, France, Germany
# ---------------------------------------------------------------------------
# The three European panels share a shape: a long OECD-sourced backbone mirrored
# on FRED (hourly earnings from the late 1950s/early 1960s, quarterly CPI from
# 1955, harmonised unemployment) spliced forward onto the current national
# source (ONS, INSEE, Eurostat), which is more timely and is the series the
# national statistician actually maintains. The OECD Main Economic Indicators
# series stop in 2025Q1 -- they are a legacy vintage on FRED -- so using them
# alone would leave the whole 2025-26 period missing, and using only the
# national source would cut the sample at 1988 (UK CPI), 1990 (French CPI) or
# 2008 (the euro-area labour cost index). The splice is on growth rates with
# the modern series authoritative for the level; see `splice`.

def build_uk(force: bool = False) -> Dict[str, pd.Series]:
    o = lambda sid, ds, fq="M": src.ons_series(sid, ds, fq, force=force)  # noqa: E731
    f = lambda sid: src.fred(sid, force=force)                            # noqa: E731

    rpi = to_quarterly(o("CDKO", "MM23"))            # RPI index, 1947-
    cpi_new = to_quarterly(_try(o, "D7BT", "MM23"))  # CPI index, 1988-
    cpi = splice(cpi_new, rpi) if cpi_new is not None else rpi
    core = splice(to_quarterly(_try(o, "DKC9", "MM23")), _try(f, "GBRCPICORQINMEI"))
    energy = to_quarterly(_try(o, "D7CB", "MM23"))

    # AWE regular pay (2000-) on top of the OECD hourly earnings index (1963-).
    awe = to_quarterly(_try(o, "KAB9", "EMP"))
    wage = splice(awe, _try(f, "LCEAMN01GBQ661S")) if awe is not None \
        else f("LCEAMN01GBQ661S")

    unrate = to_quarterly(o("MGSX", "LMS"))          # LFS rate, 1971-
    vac = to_quarterly(_try(o, "AP2Y", "UNEM"))
    unemp = to_quarterly(_try(o, "MGSC", "LMS"))
    pty = _try(f, "ULQELP01GBQ661S")

    mw = _read_csv("wage_minwage.csv")
    mw = mw[mw["country"] == "UK"]
    mw_s = pd.Series(mw["rate"].astype(float).values,
                     index=pd.PeriodIndex(mw["effective"], freq="M").to_timestamp())
    mw_q = mw_s.resample("QS").last().ffill()

    # Household social benefits received in cash and household disposable
    # income, UK Economic Accounts. The UK left the Eurostat sector-account
    # collection after 2019, so these come from ONS directly.
    d62 = to_quarterly(_try(o, "RVFJ", "UKEA", "Q"), "last")
    b6g = to_quarterly(_try(o, "QWND", "UKEA", "Q"), "last")

    return dict(cpi=cpi, core=core, energy=energy, wage=wage, unrate=unrate,
                vacancies=vac, unemployed=unemp, minwage=mw_q, pty=pty,
                transfers=d62, dpi=b6g, cpi_m=o("CDKO", "MM23"),
                earnings_m=_try(o, "KAB9", "EMP"))


FR_IDBANK = {
    "smic": "000822484",   # SMIC brut horaire, monthly, EUR, 1951- (verified
                           # against the INSEE SDMX series title and the
                           # published step of EUR 12.31 on 1 June 2026)
    "smb_yoy": "010562675",  # SMB, year-on-year % change, all non-agricultural
                             # sectors, quarterly (SALAIRES-ACEMO-2017)
}


def build_fr(force: bool = False) -> Dict[str, pd.Series]:
    """France: the euro-area template, with INSEE supplying the SMIC.

    An earlier version of this function pulled the French CPI and base-wage
    index from INSEE BDM idbanks. Two of the three idbanks were wrong -- one
    resolved to a business-climate survey and two to series INSEE has since
    stopped (the base-2015 CPI, retired when the index was rebased to 2025) --
    which is why the French real wage appeared to fall 11% between 2019 and
    2022 instead of about 4%. Guessing an identifier from a series name is not
    a data source. Everything except the SMIC now comes through the harmonised
    Eurostat/OECD path the other European countries use, and the SMIC idbank is
    verified against the series title returned by INSEE's own SDMX endpoint and
    against the published rate.
    """
    out = build_euro("FR", force, fred_wage="LCEAMN01FRQ661S",
                     fred_cpi="FRACPIALLQINMEI", fred_une="LRHUTTTTFRQ156S")
    smic = _try(src.insee_bdm, FR_IDBANK["smic"], force)
    if smic is not None:
        out["minwage"] = to_quarterly(smic, "last")
    # The base wage index (SMB) excludes bonuses and is France's negotiated-wage
    # analogue. INSEE publishes the all-sector aggregate only as a growth rate,
    # so it is carried as an alternative measure of gw rather than as a level.
    out["wage_smb_yoy"] = _try(src.insee_bdm, FR_IDBANK["smb_yoy"], force)
    return out


def build_de(force: bool = False) -> Dict[str, pd.Series]:
    e = lambda ds, **kw: _try(src.eurostat, ds, **kw)  # noqa: E731
    f = lambda sid: src.fred(sid, force=force)         # noqa: E731

    hicp = _try(eurostat_best, "prc_hicp_midx", "unit", ["I15", "I05", "I96"],
                geo="DE", coicop="CP00")
    cpi = splice(to_quarterly(hicp) if hicp is not None else None,
                 _try(f, "DEUCPIALLQINMEI"))
    energy = _try(eurostat_best, "prc_hicp_midx", "unit", ["I15", "I05", "I96"],
                  geo="DE", coicop="NRG")
    food = _try(eurostat_best, "prc_hicp_midx", "unit", ["I15", "I05", "I96"],
                geo="DE", coicop="FOOD")
    core = splice(_try(eurostat_best, "prc_hicp_midx", "unit", ["I15", "I05", "I96"],
                       geo="DE", coicop="TOT_X_NRG_FOOD"),
                  _try(f, "DEUCPICORQINMEI"))

    # Compensation per employee from the national accounts (1991-, reunified),
    # extended back with the OECD hourly earnings index. Destatis's
    # Tarifverdienstindex would be the negotiated-wage analogue -- and it is the
    # series that separates the Inflationsausgleichspraemie from base pay -- but
    # Genesis-Online serves it only behind a session API, so it cannot go in a
    # keyless pipeline. The consequence is stated in the paper: German measured
    # wage growth in 2023-24 includes the tax-free bonus, which is exactly the
    # measurement problem the paper is about.
    d1 = e("namq_10_a10", geo="DE", na_item="D1", nace_r2="TOTAL",
           unit="CP_MNAC", s_adj="SA")
    emp = e("namq_10_a10_e", geo="DE", na_item="EMP_DC", nace_r2="TOTAL",
            unit="THS_PER", s_adj="SCA")
    cpe = (d1 / emp).dropna() if (d1 is not None and emp is not None) else None
    wage = splice(cpe, _try(f, "LCEAMN01DEQ661N")) if cpe is not None \
        else _try(f, "LCEAMN01DEQ661N")

    une = splice(e("une_rt_q", geo="DE", unit="PC_ACT", s_adj="SA",
                   age="Y15-74", sex="T"), _try(f, "LRHUTTTTDEQ156S"))
    pty = _try(f, "ULQELP01DEQ661S")
    d62 = e("nasq_10_nf_tr", geo="DE", na_item="D62", sector="S14_S15",
            direct="RECV", unit="CP_MNAC", s_adj="SCA")
    b6g = e("nasq_10_nf_tr", geo="DE", na_item="B6G", sector="S14_S15",
            direct="PAID", unit="CP_MNAC", s_adj="SCA")
    mw = e("earn_mw_cur", geo="DE", currency="NAC")

    return dict(cpi=cpi, core=core,
                energy=to_quarterly(energy) if energy is not None else None,
                food=to_quarterly(food) if food is not None else None,
                wage=wage, unrate=une, transfers=d62, dpi=b6g, pty=pty,
                minwage=mw.resample("QS").ffill() if mw is not None else None)


def build_euro(geo: str, force: bool = False,
               fred_wage: Optional[str] = None,
               fred_cpi: Optional[str] = None,
               fred_une: Optional[str] = None) -> Dict[str, pd.Series]:
    """A euro-area country panel from Eurostat, back-extended with OECD series.

    Used for the reference countries that carry the identifying variation in
    lambda -- Belgium (automatic indexation of both wages and benefits, still
    in force), Italy (the scala mobile and its dismantling) and Spain (the
    collapse and partial return of wage-guarantee clauses). Germany goes
    through its own builder only because its compensation-per-employee splice
    needs the extra care of a reunification break.
    """
    e = lambda ds, **kw: _try(src.eurostat, ds, **kw)  # noqa: E731
    f = lambda sid: _try(src.fred, sid, force=force)   # noqa: E731
    U = ["I15", "I05", "I96"]

    cpi = splice(to_quarterly(_try(eurostat_best, "prc_hicp_midx", "unit", U,
                                   geo=geo, coicop="CP00")), f(fred_cpi) if fred_cpi else None)
    core = splice(to_quarterly(_try(eurostat_best, "prc_hicp_midx", "unit", U,
                                    geo=geo, coicop="TOT_X_NRG_FOOD")), None)
    energy = to_quarterly(_try(eurostat_best, "prc_hicp_midx", "unit", U, geo=geo, coicop="NRG"))
    food = to_quarterly(_try(eurostat_best, "prc_hicp_midx", "unit", U, geo=geo, coicop="FOOD"))

    # Eurostat's seasonal-adjustment coverage is uneven across countries: the
    # same table is served SCA for one member state, SA for another and NSA
    # only for a third. Sweeping the codes is not laziness, it is the only way
    # to write one function that works for the whole panel.
    d1 = _try(eurostat_best, "namq_10_a10", "s_adj", ["SCA", "SA", "NSA"],
              geo=geo, na_item="D1", nace_r2="TOTAL", unit="CP_MNAC")
    emp = _try(eurostat_best, "namq_10_a10_e", "s_adj", ["SCA", "SA", "NSA"],
               geo=geo, na_item="EMP_DC", nace_r2="TOTAL", unit="THS_PER")
    cpe = (d1 / emp).dropna() if (d1 is not None and emp is not None) else None
    if cpe is None or len(cpe) < 20:
        # Last resort: the labour cost index, wages and salaries. Shorter
        # (2000-) but harmonised, and it is what the ECB's own euro-area wage
        # equations fall back on when national accounts are unavailable.
        cpe = _try(eurostat_best, "lc_lci_r2_q", "unit", ["I20", "I16", "I12"],
                   geo=geo, nace_r2="B-S", lcstruct="D11", s_adj="NSA")
    wage = splice(cpe, f(fred_wage) if fred_wage else None)

    une = splice(_try(eurostat_best, "une_rt_q", "s_adj", ["SA", "NSA"],
                      geo=geo, unit="PC_ACT", age="Y15-74", sex="T"),
                 f(fred_une) if fred_une else None)
    d62 = _try(eurostat_best, "nasq_10_nf_tr", "s_adj", ["SCA", "SA", "NSA"],
               geo=geo, na_item="D62", sector="S14_S15", direct="RECV", unit="CP_MNAC")
    b6g = _try(eurostat_best, "nasq_10_nf_tr", "s_adj", ["SCA", "SA", "NSA"],
               geo=geo, na_item="B6G", sector="S14_S15", direct="PAID", unit="CP_MNAC")
    mw = e("earn_mw_cur", geo=geo, currency="NAC")

    return dict(cpi=cpi, core=core, energy=energy, food=food, wage=wage,
                unrate=une, transfers=d62, dpi=b6g,
                minwage=mw.resample("QS").ffill() if mw is not None else None)


BUILDERS = {
    "US": build_us,
    "UK": build_uk,
    "FR": build_fr,
    "DE": build_de,
    # Reference countries. They are not the paper's subject, but they are where
    # lambda actually varies -- Belgium sits at 0.96 for the whole sample while
    # Germany sits near 0.07, in the same currency union facing the same energy
    # shock. Without them the indexation interaction is identified only off the
    # US time series, where lambda never exceeds 0.13.
    "BE": lambda force=False: build_euro("BE", force, None,
                                         "BELCPIALLQINMEI", "LRHUTTTTBEQ156S"),
    "IT": lambda force=False: build_euro("IT", force, "LCEAMN01ITQ661N",
                                         "ITACPIALLQINMEI", "LRHUTTTTITQ156S"),
    "ES": lambda force=False: build_euro("ES", force, "LCEAMN01ESQ661N",
                                         "ESPCPIALLQINMEI", "LRHUTTTTESQ156S"),
}


# ---------------------------------------------------------------------------
# Panel assembly
# ---------------------------------------------------------------------------
def _tightness(raw: Dict[str, pd.Series]) -> Dict[str, pd.Series]:
    """Labour-market tightness measures, positive when the market is tight.

    Returns up to two series.

    ``slack`` is the **unemployment gap**: a slow-moving reference rate minus
    the actual rate. Where a published NAIRU exists (the CBO's, for the US,
    back to 1949) we use it; elsewhere the reference is a five-year *trailing*
    moving average of the unemployment rate, which uses no future information
    and so can be computed in real time and in the browser. This is the default
    because it exists for every country over the whole sample.

    ``slack_vu`` is the **vacancy-to-unemployment ratio**, standardised --
    Bernanke & Blanchard's preferred measure, and the better one over the
    post-2020 period when unemployment stopped being a sufficient statistic for
    tightness. It exists only from 2001 for the UK and (via JOLTS) the US, so
    it is offered as an alternative rather than imposed as the default: making
    it the default would cut the UK sample from 1963 to 2001 and throw away the
    threshold-agreement episode, which is the UK's whole contribution here.
    """
    out: Dict[str, pd.Series] = {}
    u = raw.get("unrate")
    if u is not None and len(u) > 20:
        if raw.get("nairu") is not None:
            ref = raw["nairu"].reindex(u.index).interpolate()
        else:
            ref = u.rolling(20, min_periods=8).mean()
        out["slack"] = (ref - u).dropna().rename("slack")
    if raw.get("vacancies") is not None and raw.get("unemployed") is not None:
        vu = (raw["vacancies"] / raw["unemployed"]).dropna()
        if len(vu) > 20:
            out["slack_vu"] = ((vu - vu.mean()) / vu.std()).rename("slack_vu")
    return out


def build_panel(country: str, cfg: Optional[WageConfig] = None,
                force: bool = False) -> pd.DataFrame:
    """Assemble one country's quarterly panel."""
    cfg = cfg or WageConfig()
    raw = BUILDERS[country](force=force)
    raw = {k: v for k, v in raw.items() if v is not None and len(v) > 0}

    cpi, wage = raw["cpi"], raw["wage"]
    df = pd.DataFrame(index=cpi.index.union(wage.index).sort_values())
    df = df[df.index >= START[country]]

    # Growth rates are FOUR-QUARTER (year-on-year) log changes, not annualised
    # quarterly ones.
    #
    # Bernanke & Blanchard can use annualised quarterly growth because their
    # wage measure is the Employment Cost Index, a fixed-weight quarterly index
    # built for exactly that purpose. Outside the United States there is no ECI:
    # the available series are compensation per employee from the national
    # accounts, OECD hourly earnings, and average weekly earnings, all of which
    # carry enough quarter-to-quarter measurement noise that their annualised
    # quarterly growth is close to white. Estimated on those, a wage equation
    # returns a NEGATIVE sum of own-lag coefficients -- the signature of
    # differencing noise, not of wage dynamics.
    #
    # Year-on-year growth is what the ECB wage tracker, the negotiated-wage
    # indicators and the national statistical releases all publish, and it is
    # what the catch-up term is naturally measured in. The cost is overlapping
    # observations and hence serially correlated residuals, so the reported
    # standard errors understate uncertainty; this is stated in the methodology
    # and is why the paper leans on coefficient sums and sign tests rather than
    # on individual t-statistics.
    #
    # The annualised quarterly variants are kept alongside as `gp_q` / `gw_q`
    # so the specification choice can be inspected rather than taken on trust.
    df["gp"] = yoy(cpi).reindex(df.index)
    df["gp_q"] = ann_growth(cpi).reindex(df.index)
    df["pi_yoy"] = df["gp"]
    df["gw"] = yoy(wage).reindex(df.index)
    df["gw_q"] = ann_growth(wage).reindex(df.index)
    if "core" in raw:
        df["gp_core"] = yoy(raw["core"]).reindex(df.index)

    # Relative energy and food prices are measured against WAGES, not against
    # the headline index: Bernanke & Blanchard's grpe/grpf are real product
    # wages, and getting this wrong is the commonest replication error.
    for key, col in (("energy", "grpe"), ("food", "grpf")):
        if key in raw:
            rel = (raw[key] / wage.reindex(raw[key].index).ffill()).dropna()
            df[col] = yoy(rel).reindex(df.index)

    for name, series in _tightness(raw).items():
        df[name] = series.reindex(df.index)

    if "pty" in raw:
        df["gpty"] = yoy(raw["pty"]).rolling(8, min_periods=4).mean().reindex(df.index)

    if "minwage" in raw:
        # Zero, not missing, before a country has a statutory minimum wage.
        # Germany introduced one only in 2015 and Italy still has none; leaving
        # those quarters missing would silently truncate the German wage
        # equation to 32 observations. "No floor" is information, and its
        # growth contribution is exactly zero.
        df["dmw"] = yoy(raw["minwage"]).reindex(df.index).fillna(0.0)
        df["minwage"] = raw["minwage"].reindex(df.index).ffill()
    else:
        df["dmw"] = 0.0

    # The transfer impulse: the change in cash transfers, annualised, as a
    # percent of last quarter's disposable income. In these units phi_e in the
    # fiscal rule reads directly as "percentage points of household income
    # handed out per percentage point of excess inflation".
    # The transfer impulse, in percentage points of household disposable income
    # over four quarters:
    #
    #     h_t = 100 * (T_t / Y_t  -  T_{t-4} / Y_{t-4})
    #
    # A ratio-of-levels difference rather than a deflated flow, because the
    # seven national accounts in this panel are published in six different
    # currencies, three different base years and (for the UK) a different
    # vintage discipline. A share is unit-free, so a units error in one
    # country's source cannot silently rescale its coefficient -- which is what
    # happened when this was first written as a level change.
    if "transfers" in raw and "dpi" in raw:
        T = raw["transfers"].reindex(df.index)
        Y = raw["dpi"].reindex(df.index)
        share = (T / Y).replace([np.inf, -np.inf], np.nan)
        df["transfer_share"] = 100.0 * share
        df["h"] = 100.0 * share.diff(PPY)

    # The DISCRETIONARY part of the transfer impulse. Total transfers are
    # dominated by automatic stabilisers -- unemployment insurance rises in
    # recessions, when inflation is falling -- so `h` enters a price equation
    # with a spurious negative sign. We remove the cyclical component by
    # projecting h on the contemporaneous and four lagged changes in the
    # unemployment rate and keeping the residual. What is left is the part of
    # the transfer impulse that policy chose rather than the cycle delivered.
    if "h" in df and "unrate" in raw:
        du = raw["unrate"].reindex(df.index).diff()
        Z = pd.concat([du.shift(k).rename(f"du{k}") for k in range(0, 5)], axis=1)
        Z.insert(0, "const", 1.0)
        ok = Z.notna().all(axis=1) & df["h"].notna()
        if int(ok.sum()) > 20:
            b = np.linalg.lstsq(Z[ok].to_numpy(), df.loc[ok, "h"].to_numpy(), rcond=None)[0]
            fitted = pd.Series(Z.to_numpy() @ b, index=df.index).where(Z.notna().all(axis=1))
            df["h_disc"] = df["h"] - fitted
        else:
            df["h_disc"] = df["h"]

    cov, lam = load_coverage(country, df.index, cfg)
    for c in cov.columns:
        df[f"cov_{c}"] = cov[c]
    df["lambda"] = lam
    df["wedge"] = load_wedge(country, df.index)
    df["scheme"] = load_schemes(country, df.index)
    pol = load_politics(country, df.index)
    df["populist"] = pol["populist"]
    df["election"] = pol["election"]

    df["pistar"] = trend_inflation(df["gp"].ffill(), cfg.anchor_q).reindex(df.index)
    df["catchup"] = real_wage_gap(wage, cpi).reindex(df.index)
    df["catchup_bb"] = catchup(df["pi_yoy"], df["pistar"])
    df["real_wage"] = (100.0 * np.log(wage / cpi.reindex(wage.index))).reindex(df.index)
    df["pigap"] = df["gp"] - df["pistar"]

    if "wage_smb_yoy" in raw:
        df["gw_alt"] = raw["wage_smb_yoy"].reindex(df.index)
    if "exp1" in raw:
        df["exp1"] = raw["exp1"].reindex(df.index)
    if "exp10" in raw:
        df["exp10"] = raw["exp10"].reindex(df.index)

    # ---- Effective Wage Index components (Eq. W10) --------------------
    # Each is a level index, 100 in the base quarter, so the share-weighted sum
    # is itself an index and the contribution of each source to its growth is
    # readable straight off the chart.
    base = pd.Timestamp("2019-10-01")
    def _rebase(x: Optional[pd.Series]) -> Optional[pd.Series]:
        if x is None:
            return None
        x = x.reindex(df.index).ffill()
        anchor = x.loc[:base].dropna()
        if anchor.empty:
            return None
        return 100.0 * x / float(anchor.iloc[-1])

    df["lvl_wage"] = _rebase(wage)
    df["lvl_price"] = _rebase(cpi)
    if "minwage" in raw:
        df["lvl_minwage"] = _rebase(raw["minwage"])
    else:
        # No statutory floor: the "floor" component tracks the market wage, so
        # that a country without a minimum wage is not implicitly assigned a
        # frozen one.
        df["lvl_minwage"] = df["lvl_wage"]

    ben = _try(benefit_index, country, raw, df.index)
    df["lvl_benefit"] = ben if ben is not None else df["lvl_price"]

    # Handouts are a flow, not a level: the component index is one plus the
    # annualised scheme amount as a share of household disposable income, so it
    # sits at 100 in every quarter with no scheme and jumps only while one is
    # paying out. A one-off payment therefore adds to income growth in the year
    # it is made and subtracts from it the year after -- which is exactly what
    # a one-off does, and exactly what an aggregate wage index cannot show.
    if "dpi" in raw and df["scheme"].abs().sum() > 0:
        Y = raw["dpi"].reindex(df.index).ffill()
        scale = 1000.0 if country != "US" else 1.0   # EUR/GBP m vs USD bn
        df["lvl_handout"] = 100.0 * (1.0 + (df["scheme"] * scale / Y).fillna(0.0))
    else:
        df["lvl_handout"] = 100.0

    df["country"] = country
    return df


def build_all(cfg: Optional[WageConfig] = None, force: bool = False,
              countries: Sequence[str] = ALL_COUNTRIES) -> Dict[str, pd.DataFrame]:
    return {c: build_panel(c, cfg, force) for c in countries}


# ---------------------------------------------------------------------------
# Statutory uprating rules (implemented, then validated against the published
# decisions in config/wage_uprating.csv)
# ---------------------------------------------------------------------------
def uprating_us(cpi_w: pd.Series) -> pd.Series:
    """Social Security Act s.215(i): the COLA is the increase in the third-
    quarter average CPI-W over the highest previous third-quarter average,
    floored at zero, effective for December and paid the following January."""
    q3 = cpi_w[cpi_w.index.month.isin([7, 8, 9])].resample("YS").mean().dropna()
    high = q3.cummax().shift(1)
    pct = (100.0 * (q3 / high - 1.0)).clip(lower=0.0).dropna()
    pct.index = pd.to_datetime((pct.index.year + 1).astype(str) + "-01-01")
    return pct.rename("cola")


def uprating_uk(cpi: pd.Series, earnings: Optional[pd.Series] = None,
                triple_lock: bool = True) -> pd.Series:
    """SSAA 1992 s.150: September CPI, applied the following April. For the
    State Pension the triple lock takes the highest of September CPI, the
    May-July average of total-pay earnings growth, and 2.5%."""
    sep = cpi.pct_change(12).mul(100.0)
    sep = sep[sep.index.month == 9].dropna()
    out = sep.copy()
    if triple_lock and earnings is not None:
        eg = earnings.pct_change(12).mul(100.0)
        summer = eg[eg.index.month.isin([5, 6, 7])].resample("YS").mean()
        for ts in out.index:
            e = summer.get(pd.Timestamp(ts.year, 1, 1), np.nan)
            out.loc[ts] = max(out.loc[ts], 2.5, e if np.isfinite(e) else -np.inf)
    out.index = pd.to_datetime((out.index.year + 1).astype(str) + "-04-01")
    return out.rename("uprating")


def uprating_fr(cpi_xtob: pd.Series) -> pd.Series:
    """CSS art. L161-25: the average of the twelve most recent monthly CPI
    (excluding tobacco) indices over the same average a year earlier, applied
    on 1 January and floored at zero."""
    avg12 = cpi_xtob.rolling(12).mean()
    ref = avg12[avg12.index.month == 10].dropna()   # the penultimate month rule
    pct = (100.0 * (ref / ref.shift(1) - 1.0)).clip(lower=0.0).dropna()
    pct.index = pd.to_datetime((pct.index.year + 1).astype(str) + "-01-01")
    return pct.rename("revalorisation")


def uprating_de(wage: pd.Series) -> pd.Series:
    """Rentenanpassungsformel, in the form that has applied since the 48%
    Niveauschutzklausel began to bind in 2024: the adjustment follows gross
    wage growth (the Lohnkomponente) with the dampening factors suspended,
    effective 1 July. Before 2024 this overstates the adjustment by the
    sustainability and contribution-rate factors, which is stated rather than
    modelled -- the two factors need contributor and pensioner counts that no
    keyless source publishes quarterly."""
    g = wage.pct_change(PPY).mul(100.0)
    ann = g[g.index.month == 1].dropna()
    ann.index = pd.to_datetime(ann.index.year.astype(str) + "-07-01")
    return ann.rename("rentenanpassung")


def benefit_index(country: str, raw: Dict[str, pd.Series],
                  index: pd.DatetimeIndex) -> pd.Series:
    """A level index of indexed social benefits, built from the statutory rule.

    Starts at 100 in the first period and compounds each statutory uprating on
    the date it reaches recipients. This is the ``benefit`` component of the
    Effective Wage Index: it is deliberately *not* a spending aggregate, which
    would move with caseloads, but the entitlement of a representative
    recipient -- the thing the uprating rule actually sets.
    """
    if country == "US":
        pct = uprating_us(raw.get("cpi_w", raw["cpi"]))
    elif country == "UK" and "cpi_m" in raw:
        pct = uprating_uk(raw["cpi_m"], raw.get("earnings_m"))
    elif country == "FR" and ("cpi_xtob_m" in raw or "cpi_m" in raw):
        pct = uprating_fr(raw.get("cpi_xtob_m", raw.get("cpi_m")))
    else:
        # Germany and the reference countries: wage-linked pension formulas.
        # Belgium and Italy index benefits to prices, but to the *health index*
        # (Belgium) or a forecast index (Italy), neither of which is in this
        # pipeline, so they are treated as wage-linked and the approximation is
        # recorded in docs/DECISIONS.md.
        pct = uprating_de(raw["wage"])
    lvl = pd.Series(np.nan, index=index, dtype=float)
    lvl.iloc[0] = 100.0
    factor = 100.0
    for ts, p in pct.items():
        q = pd.Timestamp(ts).to_period("Q").to_timestamp()
        if q in lvl.index:
            factor *= (1.0 + float(p) / 100.0)
            lvl.loc[q] = factor
    return lvl.ffill().rename("benefit")
