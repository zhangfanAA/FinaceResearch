"""DeepSeek web search adapter for the historical data fallback chain.

Implements ``HistoricalDataAdapter`` using DeepSeek's web search API as a
last-resort data source (priority=5).  When all traditional adapters
(Tushare, Baostock, efinance, AkShare) fail, this adapter asks DeepSeek
to search the web for the requested financial data.
"""

from __future__ import annotations

from typing import Any

from app.services.data_sources.historical_base import HistoricalDataAdapter
from app.services.deepseek_search_service import DeepSeekSearchService


class DeepSeekSearchAdapter(HistoricalDataAdapter):
    """HistoricalDataAdapter backed by DeepSeek web search.

    Args:
        service: A configured ``DeepSeekSearchService`` instance.
    """

    def __init__(self, service: DeepSeekSearchService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def priority(self) -> int:
        return 5  # lowest priority, last resort

    def fetch_sector_history(
        self,
        sector_name: str,
        sector_type: str = "industry",
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch sector kline data via DeepSeek web search.

        Note: This is a synchronous wrapper. The underlying service is async,
        but the fallback chain calls adapters synchronously.  We use
        ``asyncio.run`` to bridge the gap.
        """
        import asyncio

        return asyncio.run(self._service.search_sector_history(sector_name, days))

    def fetch_index_history(
        self,
        code: str,
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch index kline data via DeepSeek web search."""
        import asyncio

        return asyncio.run(self._service.search_index_history(code, days))

    def fetch_fund_nav_history(
        self,
        code: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Fetch fund NAV history via DeepSeek web search."""
        import asyncio

        return asyncio.run(self._service.search_fund_nav_history(code, days))

    def health_check(self) -> dict[str, Any]:
        """Return health status based on circuit breaker and rate limiter state."""
        status = self._service.get_status()
        is_healthy = not status["circuit_breaker"]["is_open"]
        return {
            "ok": is_healthy,
            "latency_ms": 0,
            "error": "Circuit breaker open" if not is_healthy else None,
            "api_usage": status["rate_limiter"],
        }
