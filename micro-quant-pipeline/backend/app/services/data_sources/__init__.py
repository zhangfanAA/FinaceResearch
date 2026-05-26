"""Data source reliability layer with adapter + fallback chain pattern.

Provides:
- DataSourceAdapter abstract base class
- AkShare, EastMoney, and Mock concrete adapters
- FallbackChain executor with priority ordering and stats tracking
"""

from app.services.data_sources.base import AdapterStats, DataSourceAdapter, DataSourceResult
from app.services.data_sources.fallback_chain import FallbackChain

__all__ = [
    "AdapterStats",
    "DataSourceAdapter",
    "DataSourceResult",
    "FallbackChain",
]
