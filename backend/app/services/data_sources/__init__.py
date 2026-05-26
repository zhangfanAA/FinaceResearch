"""Data source reliability layer with adapter + fallback chain pattern.

Provides:
- DataSourceAdapter abstract base class for real-time data
- AkShare, EastMoney concrete adapters for real-time data
- FallbackChain executor with priority ordering and stats tracking
- HistoricalDataAdapter base class for historical data
- HistoricalFallbackChain with capability-aware skip logic
- HistoricalCache with SQLite persistence
"""

from app.services.data_sources.base import AdapterStats, DataSourceAdapter, DataSourceResult
from app.services.data_sources.fallback_chain import FallbackChain
from app.services.data_sources.historical_base import HistoricalDataAdapter, HistoricalDataSourceResult
from app.services.data_sources.historical_cache import HistoricalCache
from app.services.data_sources.historical_fallback_chain import HistoricalAdapterStats, HistoricalFallbackChain

__all__ = [
    "AdapterStats",
    "DataSourceAdapter",
    "DataSourceResult",
    "FallbackChain",
    "HistoricalAdapterStats",
    "HistoricalCache",
    "HistoricalDataAdapter",
    "HistoricalDataSourceResult",
    "HistoricalFallbackChain",
]
