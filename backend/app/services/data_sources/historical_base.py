"""Abstract base class for historical financial data adapters.

Defines the interface that all historical data source adapters must implement.
Adapters provide historical kline/OHLCV data for sectors, indices, and fund NAVs.

Each adapter declares a ``priority`` (lower = tried first) and raises
``NotImplementedError`` for methods it does not support. The fallback chain
uses this to skip unsupported capabilities without counting them as failures.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class HistoricalDataSourceResult:
    """Unified result envelope for historical data adapter methods."""

    data: list[dict[str, Any]] | None
    source: str  # adapter name, e.g. "tushare", "baostock"
    latency_ms: float = 0.0
    error: str | None = None


class HistoricalDataAdapter(ABC):
    """Base class for historical data source adapters.

    Subclasses must implement ``name`` and ``priority`` properties.
    They should override only the ``fetch_*`` methods they support;
    the default implementations raise ``NotImplementedError`` so the
    fallback chain can skip them immediately.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter identifier, e.g. 'tushare', 'baostock'."""

    @property
    @abstractmethod
    def priority(self) -> int:
        """Lower value = tried first in the fallback chain."""

    def fetch_sector_history(
        self,
        sector_name: str,
        sector_type: str = "industry",
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical kline data for a sector board.

        Args:
            sector_name: e.g. "白酒", "半导体"
            sector_type: "industry" or "concept"
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]

        Raises:
            NotImplementedError: If this adapter does not support sector history.
        """
        raise NotImplementedError(f"{self.name} does not support sector_history")

    def fetch_index_history(
        self,
        code: str,
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical kline data for a stock index.

        Args:
            code: e.g. "000001" (上证指数), "399001" (深证成指)
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]

        Raises:
            NotImplementedError: If this adapter does not support index history.
        """
        raise NotImplementedError(f"{self.name} does not support index_history")

    def fetch_fund_nav_history(
        self,
        code: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Fetch historical NAV data for a fund.

        Args:
            code: e.g. "000510"
            days: number of days of history

        Returns:
            List of dicts: [{date, nav, acc_nav, daily_return}]

        Raises:
            NotImplementedError: If this adapter does not support fund NAV history.
        """
        raise NotImplementedError(f"{self.name} does not support fund_nav_history")

    def health_check(self) -> dict[str, Any]:
        """Perform a lightweight health check against this data source.

        Returns:
            Dict with keys: ok (bool), latency_ms (float), error (str | None)
        """
        t0 = time.monotonic()
        try:
            # Default: try fetching a well-known index (上证指数) with minimal days
            data = self.fetch_index_history("000001", days=5)
            elapsed = (time.monotonic() - t0) * 1000
            if data:
                return {"ok": True, "latency_ms": round(elapsed, 2), "error": None}
            return {"ok": False, "latency_ms": round(elapsed, 2), "error": "Empty result"}
        except NotImplementedError:
            # Adapter doesn't support index_history -- try sector_history instead
            try:
                data = self.fetch_sector_history("白酒", "industry", days=5)
                elapsed = (time.monotonic() - t0) * 1000
                if data:
                    return {"ok": True, "latency_ms": round(elapsed, 2), "error": None}
                return {"ok": False, "latency_ms": round(elapsed, 2), "error": "Empty result"}
            except NotImplementedError:
                elapsed = (time.monotonic() - t0) * 1000
                return {"ok": False, "latency_ms": round(elapsed, 2), "error": "No supported methods"}
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                return {"ok": False, "latency_ms": round(elapsed, 2), "error": str(exc)}
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return {"ok": False, "latency_ms": round(elapsed, 2), "error": str(exc)}
