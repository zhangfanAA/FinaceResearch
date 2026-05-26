"""Historical data service with multi-source fallback and caching.

This is the central service for all historical financial data fetches.
It initializes the fallback chain with all configured adapters (ordered by
priority), uses a SQLite cache to avoid redundant API calls, and provides
health-check / status reporting for the data source status endpoint.

Usage:
    from app.services.historical_data_service import historical_data_service

    data = historical_data_service.get_sector_history("白酒", "industry", days=60)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import DEFAULT_CONFIG_PATH, Config, HistoricalDataConfig
from app.services.data_sources.akshare_historical_adapter import AkShareHistoricalAdapter
from app.services.data_sources.baostock_adapter import BaostockAdapter
from app.services.data_sources.deepseek_search_adapter import DeepSeekSearchAdapter
from app.services.data_sources.efinance_adapter import EfinanceAdapter
from app.services.data_sources.historical_base import HistoricalDataAdapter, HistoricalDataSourceResult
from app.services.data_sources.historical_cache import HistoricalCache
from app.services.data_sources.historical_fallback_chain import HistoricalFallbackChain
from app.services.data_sources.tushare_adapter import TushareAdapter
from app.services.deepseek_search_service import DeepSeekSearchService

logger = logging.getLogger(__name__)

# All known adapter classes keyed by name.
# "deepseek" is handled separately because it requires a service instance.
_ADAPTER_REGISTRY: dict[str, type[HistoricalDataAdapter]] = {
    "tushare": TushareAdapter,
    "baostock": BaostockAdapter,
    "efinance": EfinanceAdapter,
    "akshare": AkShareHistoricalAdapter,
}


class HistoricalDataService:
    """Service layer for historical financial data with multi-source fallback.

    Initializes adapters based on config priority, wraps them in a
    ``HistoricalFallbackChain``, and adds a ``HistoricalCache`` layer.
    Supports selecting a specific data source via ``active_source``.
    """

    _KNOWN_SOURCES = set(_ADAPTER_REGISTRY.keys()) | {"deepseek"}

    def __init__(
        self,
        config: Config,
        deepseek_search_service: DeepSeekSearchService | None = None,
    ) -> None:
        hd_config = config.historical_data
        self._cache_ttl = hd_config.cache_ttl_hours
        self._cache = HistoricalCache(db_path=hd_config.cache_db_path)
        self._active_source = hd_config.active_source or "auto"
        self._config_path = str(DEFAULT_CONFIG_PATH)

        # Build adapters in config priority order
        adapters: list[HistoricalDataAdapter] = []
        for name in hd_config.adapter_priority:
            # DeepSeek adapter requires a service instance
            if name == "deepseek":
                if deepseek_search_service is not None:
                    adapter = DeepSeekSearchAdapter(deepseek_search_service)
                    adapters.append(adapter)
                    logger.info(
                        "Registered historical data adapter: %s (priority=%d)",
                        name, adapter.priority,
                    )
                else:
                    logger.info("DeepSeek search adapter skipped (no service instance)")
                continue

            adapter_cls = _ADAPTER_REGISTRY.get(name)
            if adapter_cls is None:
                logger.warning("Unknown historical data adapter: %s, skipping", name)
                continue
            try:
                if name == "tushare":
                    adapter = adapter_cls(token=hd_config.tushare_token)
                else:
                    adapter = adapter_cls()
                adapters.append(adapter)
                logger.info("Registered historical data adapter: %s (priority=%d)", name, adapter.priority)
            except Exception as exc:
                logger.warning("Failed to initialize adapter %s: %s", name, exc)

        if not adapters:
            logger.warning("No historical data adapters registered -- all fetches will fail")

        self._chain = HistoricalFallbackChain(adapters)

    @property
    def chain(self) -> HistoricalFallbackChain:
        """Expose the fallback chain for status reporting."""
        return self._chain

    def get_active_source(self) -> str:
        """Return the currently active data source ('auto' or a specific adapter name)."""
        return self._active_source

    def set_active_source(self, source: str) -> None:
        """Set the active data source and persist to config.yaml.

        Args:
            source: "auto" or one of the known adapter names.

        Raises:
            ValueError: If source is not a known adapter name and not "auto".
        """
        if source != "auto" and source not in self._KNOWN_SOURCES:
            raise ValueError(
                f"Unknown data source '{source}'. "
                f"Available: {sorted(self._KNOWN_SOURCES)}"
            )
        self._active_source = source
        self._persist_active_source(source)
        logger.info("Historical data active_source set to: %s", source)

    def get_available_sources(self) -> list[str]:
        """Return list of registered adapter names."""
        return [a.name for a in self._chain.adapters]

    def _persist_active_source(self, source: str) -> None:
        """Write active_source to config.yaml."""
        import yaml
        from pathlib import Path

        config_path = Path(self._config_path)
        try:
            with config_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            hd = raw.setdefault("historical_data", {})
            hd["active_source"] = source
            with config_path.open("w", encoding="utf-8") as f:
                yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info("Persisted active_source=%s to %s", source, config_path)
        except Exception as exc:
            logger.error("Failed to persist active_source to config.yaml: %s", exc)

    def _execute(self, method: str, *args: Any, **kwargs: Any):
        """Execute a fetch method respecting the active_source setting.

        If active_source is "auto", use the full fallback chain.
        If active_source is a specific adapter name, try that adapter first.
        When the selected adapter fails, fall back to the full chain so that
        lower-priority adapters (e.g. DeepSeek) can still serve the request.
        """
        if self._active_source == "auto":
            return self._chain.execute(method, *args, **kwargs)

        # Try the user-selected adapter first
        try:
            result = self._chain.execute_single(self._active_source, method, *args, **kwargs)
            if result.data is not None:
                return result
        except ValueError as exc:
            logger.warning(
                "Selected adapter %s failed for %s: %s -- falling back to full chain",
                self._active_source, method, exc,
            )

        # Selected adapter failed or returned empty -- try the full chain
        logger.info(
            "Falling back to full chain for %s (selected adapter %s failed)",
            method, self._active_source,
        )
        return self._chain.execute(method, *args, **kwargs)

    def get_sector_history(
        self,
        sector_name: str,
        sector_type: str = "industry",
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical sector kline data with caching and fallback.

        Args:
            sector_name: e.g. "白酒", "半导体"
            sector_type: "industry" or "concept"
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]

        Raises:
            ValueError: If all adapters fail or return no data.
        """
        # Check cache
        cached = self._cache.get("any", "fetch_sector_history",
                                 sector_name=sector_name, sector_type=sector_type, days=days)
        if cached is not None:
            return cached

        result = self._execute("fetch_sector_history", sector_name, sector_type, days)
        if result.data is None:
            raise ValueError(f"Failed to fetch sector history for {sector_name}: {result.error}")

        # Cache the result
        self._cache.set(
            result.source, "fetch_sector_history",
            result.data, ttl_hours=self._cache_ttl,
            sector_name=sector_name, sector_type=sector_type, days=days,
        )

        return result.data

    def get_index_history(
        self,
        code: str,
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical index kline data with caching and fallback.

        Args:
            code: e.g. "000001" (上证指数)
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]

        Raises:
            ValueError: If all adapters fail or return no data.
        """
        cached = self._cache.get("any", "fetch_index_history", code=code, days=days)
        if cached is not None:
            return cached

        result = self._execute("fetch_index_history", code, days)
        if result.data is None:
            raise ValueError(f"Failed to fetch index history for {code}: {result.error}")

        self._cache.set(
            result.source, "fetch_index_history",
            result.data, ttl_hours=self._cache_ttl,
            code=code, days=days,
        )

        return result.data

    def get_fund_nav_history(
        self,
        code: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Fetch historical fund NAV data with caching and fallback.

        Args:
            code: fund code, e.g. "000510"
            days: number of days of history

        Returns:
            List of dicts: [{date, nav, acc_nav, daily_return}]

        Raises:
            ValueError: If all adapters fail or return no data.
        """
        cached = self._cache.get("any", "fetch_fund_nav_history", code=code, days=days)
        if cached is not None:
            return cached

        result = self._execute("fetch_fund_nav_history", code, days)
        if result.data is None:
            raise ValueError(f"Failed to fetch fund NAV history for {code}: {result.error}")

        self._cache.set(
            result.source, "fetch_fund_nav_history",
            result.data, ttl_hours=self._cache_ttl,
            code=code, days=days,
        )

        return result.data

    def get_data_source_status(self) -> dict[str, Any]:
        """Return per-adapter health and stats for the data source status endpoint.

        Returns:
            Dict with keys for each adapter plus ``_meta``:
            - stats: success/failure/skip counts and latency
            - health: ok/latency_ms/error from health_check
            - _meta.active_source: the currently active source
            - _meta.available_sources: list of registered adapter names
        """
        chain_status = self._chain.get_status()
        result: dict[str, Any] = {}

        for adapter in self._chain.adapters:
            name = adapter.name
            entry: dict[str, Any] = {
                "priority": adapter.priority,
                "stats": chain_status.get(name, {}),
            }
            # Run health check (best-effort, don't let it crash status reporting)
            try:
                entry["health"] = adapter.health_check()
            except Exception as exc:
                entry["health"] = {"ok": False, "latency_ms": 0, "error": str(exc)}

            result[name] = entry

        result["_meta"] = {
            "active_source": self._active_source,
            "available_sources": [a.name for a in self._chain.adapters],
        }

        return result


def create_historical_data_service(
    config: Config,
    deepseek_search_service: DeepSeekSearchService | None = None,
) -> HistoricalDataService:
    """Factory function to create a HistoricalDataService from config.

    Args:
        config: Application configuration.
        deepseek_search_service: Optional DeepSeek search service instance.
            If provided and ``deepseek`` is in the adapter priority list,
            it will be registered as the lowest-priority fallback adapter.
    """
    return HistoricalDataService(config, deepseek_search_service=deepseek_search_service)
