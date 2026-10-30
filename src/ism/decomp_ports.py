"""
ism.decomp_ports
================

Country ports of the supply/demand decomposition (the second model), following
the **Bank of Canada variant**:

    Kang, H., Sekkel, R., Taskin, T. & Yang, J. (2026). "Supply and
    Demand-Driven inflation: Decomposition and policy implications."
    Bank of Canada Staff Analytical Paper 2026-33.
    https://doi.org/10.34989/sap-2026-33

The BoC paper applies Shapiro (2022-18) to **quarterly national-accounts
household consumption** instead of monthly BEA PCE: detailed quarterly
household final consumption expenditure, real (chained volumes) and nominal
(current prices), per category. Price is the category's implicit deflator
(nominal / real) and quantity the chained-volume series. The estimation
equations are unchanged — 10-year rolling reduced-form VAR, now W = 40
quarters with p = 4 lags of log price and log quantity (their Eqs. on p. 2)
— and the classification/aggregation (Shapiro Eqs. 8-15) is identical. The
same construction is applied to every country here:

    country   quarterly source                                categories  from
    -------   ---------------------------------------------  ----------  ------
    ca        StatCan 36-10-0124 detailed HCE (SA, 2017$)     ~96 leaves  1961Q1
    uk        ONS Consumer Trends ct.csv (SA, CP + CVM)       144 classes 1985Q1
    fr        INSEE quarterly consumption by product (Excel)  ~40 prods   1949Q1
              (t_conso_val/vol; falls back to A17 ~17 if blocked)
    de        Destatis GENESIS 81000-0120 by purpose (COICOP) ~12+ divs   1991Q1
    it, es    Eurostat namq_10_fcs by durability (SCA)        4 cats      1995Q1
    au        ABS 5206.0 Table 8 HFCE (SA, CP + CVM)          17 cats     1959Q3
    nz        Stats NZ GDP release HFCE by item (SA)          10 divs     1987Q2
    no        SSB 14658 HFCE by COICOP (SA vol; deflator SA'd) 13 divs    1978Q1
    se        SCB NR0103 T14 HFCE by purpose (SA)             13 divs     1981Q1

Every loader returns the SAME `DecompPanels` contract as the US pipeline
(`ism.decomp_pipeline.build_decomp_panels`), so the panels flow unchanged into
`ism.decomp_engine.compute_decomp` — pass
``DecompConfig(var_lags=4, window=40, periods_per_year=4)`` (the BoC baseline,
`QUARTERLY_BASELINE` below) instead of the monthly US defaults.

Frequency conventions (quarterly):
    * inflation      : q/q % change of the implicit price deflator
    * y/y            : running product of 4 quarterly contributions. (BoC sums
                       the last four q/q contributions instead; second-order
                       difference, see docs/DECISIONS.md.)
    * spec="filter"  : Hamilton filter with (h, p) = (8, 4), the quarterly
                       parameters recommended in Hamilton (2018).

Data plumbing lives in the per-provider clients (`ism.statcan`, `ism.ons`,
`ism.insee`, `ism.destatis`); each exposes a `*_hce_panels()` function
returning ``(nominal, volume, labels)`` quarterly frames, and this module only
turns that pair into engine inputs. Nothing here knows about providers.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .decomp_engine import DecompConfig
from .decomp_pipeline import DecompPanels, _hamilton_filter_cycle
from .transforms import monthly_inflation

#: BoC SAP 2026-33 baseline: 4 lags on a 10-year (40-quarter) rolling window.
QUARTERLY_BASELINE = DecompConfig(var_lags=4, window=40, periods_per_year=4)

#: Hamilton-(2018) filter parameters at quarterly frequency (h=8, p=4).
_HAMILTON_Q = dict(h=8, p=4)


# ---------------------------------------------------------------------------
# The one shared construction: (nominal, volume) -> DecompPanels
# ---------------------------------------------------------------------------
def panels_from_nominal_real(
    nominal: pd.DataFrame,
    volume: pd.DataFrame,
    labels: dict[str, str],
    scope: str,
    spec: str = "levels",
    inflation_method: str = "pct",
    min_quarters: int = 8,
) -> DecompPanels:
    """Build engine inputs from quarterly nominal + chained-volume panels.

    price index p_{i,t} = 100 * nominal / volume   (implicit deflator)
    quantity  q_{i,t}   = volume (chained)         (the paper's real index)
    weights   ω_{i,t}   = nominal shares, renormalised over available leaves
    inflation π_{i,t}   = q/q % change of p        (contributions, Eq. 15)

    Non-positive nominal or volume observations (rare adjustment cells) are
    masked before taking logs. Categories with fewer than `min_quarters`
    usable observations are dropped.
    """
    cols = [c for c in nominal.columns if c in volume.columns]
    nom = nominal[cols].astype(float)
    vol = volume[cols].astype(float)

    # guard the logs: a deflator needs strictly positive nominal AND volume
    ok = (nom > 0) & (vol > 0)
    nom = nom.where(ok)
    vol = vol.where(ok)

    keep = [c for c in cols if ok[c].sum() >= min_quarters]
    nom, vol = nom[keep], vol[keep]

    price = 100.0 * nom / vol
    inflation = monthly_inflation(price, method=inflation_method)  # per-period (q/q)

    log_p = np.log(price)
    log_q = np.log(vol)
    if spec == "diff":
        log_p = log_p.diff()
        log_q = log_q.diff()
    elif spec == "filter":
        log_p = _hamilton_filter_cycle(log_p, **_HAMILTON_Q)
        log_q = _hamilton_filter_cycle(log_q, **_HAMILTON_Q)
    elif spec != "levels":
        raise ValueError("spec must be 'levels', 'diff', or 'filter'")

    row = nom.sum(axis=1).replace(0, np.nan)
    weights = nom.div(row, axis=0)

    common = log_p.index
    for df in (log_q, inflation, weights):
        common = common.intersection(df.index)
    out = lambda d: d.loc[common, keep]
    categories = [(k, labels.get(k, k)) for k in keep]
    return DecompPanels(
        log_price=out(log_p),
        log_quantity=out(log_q),
        inflation=out(inflation),
        weights=out(weights),
        categories=categories,
        scope=scope,
    )


# ---------------------------------------------------------------------------
# United Kingdom — ONS Consumer Trends (quarterly HCE by COICOP class)
# ---------------------------------------------------------------------------
def build_uk_panels(client=None, adj: str = "SA", spec: str = "levels",
                    max_depth: int = 2, force: bool = False) -> DecompPanels:
    """UK port: ONS Consumer Trends CP (nominal) + CVM (volume), COICOP leaves.

    144 class-level leaf categories, quarterly from 1985 Q1, seasonally
    adjusted (matching the SA BEA/StatCan inputs of the US/CA models; pass
    adj="NSA" for the unadjusted robustness variant).
    """
    from .ons import OnsClient, uk_hce_panels

    client = client or OnsClient()
    nominal, volume, labels = uk_hce_panels(client, adj=adj,
                                            max_depth=max_depth, force=force)
    panels = panels_from_nominal_real(nominal, volume, labels, scope="uk",
                                      spec=spec)
    i0, i1 = panels.log_price.index[0], panels.log_price.index[-1]
    print(f"[uk-decomp] {len(panels.categories)} COICOP leaves, "
          f"{i0.year}Q{i0.quarter} -> {i1.year}Q{i1.quarter}")
    return panels


# ---------------------------------------------------------------------------
# Canada — StatCan 36-10-0124 detailed HCE (the BoC paper's own dataset)
# ---------------------------------------------------------------------------
def build_ca_panels(client=None, scope: str = "total", spec: str = "levels",
                    force: bool = False) -> DecompPanels:
    """Canada port: StatCan detailed quarterly HCE, SA, current + 2017$ prices.

    The BoC paper's dataset: ~96 leaf categories from 1990Q4 (data from
    1961Q1). `scope` is "total", "goods" or "services" (paper Figs. 2-4),
    using the goods/services tags pinned in config/ca_hce_categories.csv.
    """
    from .statcan import StatCanClient, ca_hce_panels

    client = client or StatCanClient()
    nominal, volume, labels = ca_hce_panels(client, scope=scope, force=force)
    panels = panels_from_nominal_real(nominal, volume, labels,
                                      scope=f"ca_{scope}" if scope != "total" else "ca",
                                      spec=spec)
    print(f"[ca-decomp] scope={scope}: {len(panels.categories)} categories, "
          f"{len(panels.log_price)} quarters")
    return panels


# ---------------------------------------------------------------------------
# France — INSEE quarterly accounts, consumption by product (A17)
# ---------------------------------------------------------------------------
def build_fr_panels(client=None, spec: str = "levels", level: str = "detail",
                    force: bool = False) -> DecompPanels:
    """France port: INSEE quarterly household consumption by product, V + L.

    `level="detail"` (default) uses the ~40-product "Consommation des ménages —
    par produit" Excel tables; it degrades gracefully to the ~17-product A17
    SDMX panel when that backbone is unreachable (host blocked / no `xlrd` / no
    cache — e.g. this sandbox). `level="a17"` forces the coarse panel. SA-WDA,
    quarterly from 1949. See docs/DECISIONS.md and scripts/fetch_insee_conso.py.
    """
    from .insee import InseeClient, fr_hce_panels

    client = client or InseeClient()
    nominal, volume, labels = fr_hce_panels(client, force=force, level=level)
    panels = panels_from_nominal_real(nominal, volume, labels, scope="fr",
                                      spec=spec)
    print(f"[fr-decomp] {len(panels.categories)} products, "
          f"{len(panels.log_price)} quarters")
    return panels


# ---------------------------------------------------------------------------
# Germany — Eurostat namq_10_fcs, quarterly consumption by durability
# ---------------------------------------------------------------------------
def build_de_panels(client=None, spec: str = "levels",
                    force: bool = False) -> DecompPanels:
    """Germany port: Eurostat quarterly consumption by durability, nominal + real.

    Germany's national accounts only break consumption by COICOP *purpose*
    annually; the quarterly split is by *durability* (durable / semi-durable /
    non-durable goods, services). We take that from Eurostat's harmonised
    quarterly national accounts (namq_10_fcs, SCA), which needs no API token and
    is already used for the HICP ISM port. (The old Destatis GENESIS route only
    exposed this annually — see docs/DECISIONS.md.) Four categories, 1991Q1+.
    """
    from .eurostat import EurostatClient, eu_hce_panels

    client = client or EurostatClient()
    nominal, volume, labels = eu_hce_panels(client, geo="DE", force=force)
    panels = panels_from_nominal_real(nominal, volume, labels, scope="de",
                                      spec=spec)
    print(f"[de-decomp] {len(panels.categories)} durability categories, "
          f"{len(panels.log_price)} quarters")
    return panels


# ---------------------------------------------------------------------------
# Japan — e-Stat quarterly SNA household consumption by type (form)
# ---------------------------------------------------------------------------
def build_jp_panels(client=None, spec: str = "levels",
                    force: bool = False) -> DecompPanels:
    """Japan port: e-Stat quarterly SNA HCE by type, SA, nominal + real chained.

    Cabinet Office 四半期別GDP速報 (2020 base): four "form" leaf categories —
    durable / semi-durable / non-durable goods and services — quarterly from
    1994Q1 (see ism.estat.jp_hce_panels). A deliberately COARSE cross-section
    (4 categories, like the coarse France A17 port); read the shares with that
    in mind. Requires a free e-Stat application ID (ESTAT_API_ID in .env); the
    other countries build regardless (graceful degradation).
    """
    from .estat import EstatClient, jp_hce_panels

    client = client or EstatClient()
    nominal, volume, labels = jp_hce_panels(client, force=force)
    panels = panels_from_nominal_real(nominal, volume, labels, scope="jp",
                                      spec=spec)
    print(f"[jp-decomp] {len(panels.categories)} form categories, "
          f"{len(panels.log_price)} quarters")
    return panels



# ---------------------------------------------------------------------------
# Australia, New Zealand, Norway, Sweden -- COICOP-division-level HFCE
# ---------------------------------------------------------------------------
def _port(scope, loader, what, force, spec):
    nominal, volume, labels = loader(force=force)
    panels = panels_from_nominal_real(nominal, volume, labels, scope=scope, spec=spec)
    i0, i1 = panels.log_price.index[0], panels.log_price.index[-1]
    print(f"[{scope}-decomp] {len(panels.categories)} {what}, "
          f"{i0.year}Q{i0.quarter} -> {i1.year}Q{i1.quarter}")
    return panels


def build_it_panels(client=None, spec: str = "levels", force: bool = False) -> DecompPanels:
    """Italy port: Eurostat namq_10_fcs, 4 durability categories, SCA, 1995Q1+.

    Istat publishes household consumption by purpose only annually, so this is
    the same coarse durability split as Germany's (see build_de_panels)."""
    from .eurostat import eu_hce_panels
    return _port("it", lambda force=False: eu_hce_panels(geo="IT", force=force),
                 "durability categories", force, spec)


def build_es_panels(client=None, spec: str = "levels", force: bool = False) -> DecompPanels:
    """Spain port: Eurostat namq_10_fcs, 4 durability categories, SCA, 1995Q1+.

    INE's quarterly accounts publish no consumption-by-purpose split; same
    coarse durability cross-section as Germany and Italy."""
    from .eurostat import eu_hce_panels
    return _port("es", lambda force=False: eu_hce_panels(geo="ES", force=force),
                 "durability categories", force, spec)


def build_au_panels(client=None, spec: str = "levels", force: bool = False) -> DecompPanels:
    """Australia port: ABS 5206.0 Table 8, 17 HFCE categories, SA, CP + CVM, 1959Q3+."""
    from .abs_au import au_hce_panels
    return _port("au", au_hce_panels, "HFCE categories", force, spec)


def build_nz_panels(client=None, spec: str = "levels", force: bool = False) -> DecompPanels:
    """New Zealand port: Stats NZ GDP release, 10 COICOP divisions, SA, 1987Q2+.

    Health and education are suppressed (CONFIDENTIAL) in the SA series."""
    from .statsnz import nz_hce_panels
    return _port("nz", nz_hce_panels, "COICOP divisions", force, spec)


def build_no_panels(client=None, spec: str = "levels", force: bool = False) -> DecompPanels:
    """Norway port: SSB table 14658, 13 COICOP divisions, 1978Q1+.

    Volume is SSB's seasonally adjusted series; the deflator is SSB's unadjusted
    one with a rolling quarterly seasonal removed (SSB publishes no SA current
    prices) -- see ism.nordic.no_hce_panels and docs/DECISIONS.md.
    """
    from .nordic import no_hce_panels
    return _port("no", no_hce_panels, "COICOP divisions", force, spec)


def build_se_panels(client=None, spec: str = "levels", force: bool = False) -> DecompPanels:
    """Sweden port: SCB NR0103 T14, 13 COICOP divisions, SA, CP + constant, 1981Q1+."""
    from .nordic import se_hce_panels
    return _port("se", se_hce_panels, "COICOP divisions", force, spec)


#: Registry used by scripts/export_decomp_data.py and scripts/build_decomp.py.
PORTS = {
    "ca": build_ca_panels,
    "uk": build_uk_panels,
    "fr": build_fr_panels,
    "de": build_de_panels,
    "jp": build_jp_panels,
    "it": build_it_panels,
    "es": build_es_panels,
    "au": build_au_panels,
    "nz": build_nz_panels,
    "no": build_no_panels,
    "se": build_se_panels,
}
