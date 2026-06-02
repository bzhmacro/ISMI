"""ism -- replication of Lansing & Shapiro (2026), "Measuring Inflation Shock
Momentum" (FRBSF WP 2026-10).

Public API:
    from ism.engine import ISMConfig, compute_ism
    from ism.transforms import monthly_inflation, yoy_inflation
"""

__all__ = ["engine", "transforms", "datasources", "pipeline", "validate"]
__version__ = "0.1.0"
