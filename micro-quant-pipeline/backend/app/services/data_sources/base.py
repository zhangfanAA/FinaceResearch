"""Abstract base class and result types for data source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DataSourceResult:
    """Unified result envelope returned by every adapter method."""

    data: list | dict | None
    source: str  # "akshare", "eastmoney", "mock"
    is_mock: bool = False
    latency_ms: float = 0
    error: str | None = None


@dataclass
class AdapterStats:
    """Per-adapter success/failure statistics."""

    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0
    last_error: str | None = None
    last_success_at: str | None = None


class DataSourceAdapter(ABC):
    """Base class that every concrete data source adapter must implement.

    Attributes:
        name: Human-readable adapter identifier, e.g. "akshare", "eastmoney".
        priority: Lower value = tried first.  Use 99 for last-resort mock.
    """

    name: str
    priority: int

    @abstractmethod
    def fetch_stock_realtime(self, codes: list[str]) -> DataSourceResult:
        """Fetch real-time stock quotes for the given codes."""

    @abstractmethod
    def fetch_sector_list(self, sector_type: str) -> DataSourceResult:
        """Fetch sector board rankings (industry or concept)."""

    @abstractmethod
    def fetch_fund_nav(self, codes: list[str]) -> DataSourceResult:
        """Fetch fund NAV data for the given codes."""
