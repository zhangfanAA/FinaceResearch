"""Historical data fallback chain with capability-aware skip logic.

Iterates historical data adapters sorted by priority. When an adapter raises
``NotImplementedError`` (capability gap), it is skipped immediately with no
retry. For all other exceptions, each adapter is retried up to 2 times before
moving to the next adapter in the chain.

Returns the first successful result and logs which adapter was used.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.services.data_sources.historical_base import (
    HistoricalDataAdapter,
    HistoricalDataSourceResult,
)

logger = logging.getLogger(__name__)

# Maximum retry attempts per adapter (in addition to the initial call).
_MAX_RETRIES_PER_ADAPTER = 2


@dataclass
class HistoricalAdapterStats:
    """Per-adapter success/failure statistics for historical data fetches."""

    success_count: int = 0
    failure_count: int = 0
    skip_count: int = 0  # NotImplementedError (capability gap)
    avg_latency_ms: float = 0.0
    last_error: str | None = None
    last_success_at: str | None = None


class HistoricalFallbackChain:
    """Execute historical data fetch methods across adapters in priority order.

    For each adapter:
    - If the method raises ``NotImplementedError``, skip immediately (capability gap).
    - Otherwise, retry up to ``_MAX_RETRIES_PER_ADAPTER`` times on transient failures.
    - Return the first successful result.

    If every adapter fails, returns a ``HistoricalDataSourceResult`` with
    ``data=None`` and an error summary.
    """

    def __init__(self, adapters: list[HistoricalDataAdapter]) -> None:
        self.adapters = sorted(adapters, key=lambda a: a.priority)
        self.stats: dict[str, HistoricalAdapterStats] = {}
        for adapter in self.adapters:
            self.stats.setdefault(adapter.name, HistoricalAdapterStats())

    def execute(
        self,
        method: str,
        *args: Any,
        **kwargs: Any,
    ) -> HistoricalDataSourceResult:
        """Execute *method* on each adapter until one succeeds.

        Args:
            method: One of ``"fetch_sector_history"``, ``"fetch_index_history"``,
                    ``"fetch_fund_nav_history"``.
            *args, **kwargs: Forwarded to the adapter method.

        Returns:
            The first ``HistoricalDataSourceResult`` with ``data`` not None/empty.
            If all fail, returns an error envelope.
        """
        errors: list[str] = []

        for adapter in self.adapters:
            fn = getattr(adapter, method, None)
            if fn is None:
                continue

            # Check if the adapter actually supports this method by inspecting
            # whether it overrides the base class default (which raises NotImplementedError).
            # We do this by attempting the call -- if NotImplementedError is raised
            # on the first attempt, we skip without retry.
            last_error: str | None = None

            for attempt in range(1 + _MAX_RETRIES_PER_ADAPTER):
                try:
                    result_data = fn(*args, **kwargs)
                    if result_data is not None and len(result_data) > 0:
                        # Success
                        self._update_stats(adapter.name, success=True)
                        logger.info(
                            "Historical data fetched via %s.%s (attempt %d)",
                            adapter.name, method, attempt + 1,
                        )
                        return HistoricalDataSourceResult(
                            data=result_data,
                            source=adapter.name,
                        )
                    # Empty result -- treat as failure but retry
                    last_error = f"Empty result from {adapter.name}.{method}"
                    if attempt < _MAX_RETRIES_PER_ADAPTER:
                        logger.info(
                            "Adapter %s returned empty result on attempt %d/%d for %s, retrying",
                            adapter.name, attempt + 1, 1 + _MAX_RETRIES_PER_ADAPTER, method,
                        )
                except NotImplementedError:
                    # Capability gap -- skip this adapter immediately, no retry
                    logger.info(
                        "Adapter %s does not support %s (NotImplementedError), skipping",
                        adapter.name, method,
                    )
                    self._update_stats(adapter.name, success=False, skipped=True)
                    last_error = None  # Don't count as error
                    break
                except Exception as exc:
                    last_error = str(exc)
                    logger.warning(
                        "Adapter %s raised on attempt %d/%d for %s: %s",
                        adapter.name, attempt + 1, 1 + _MAX_RETRIES_PER_ADAPTER, method, exc,
                    )

            # All retries for this adapter exhausted (or capability skip)
            if last_error is not None:
                self._update_stats(adapter.name, success=False, error=last_error)
                errors.append(f"[{adapter.name}] {last_error}")

        # All adapters failed
        error_summary = "; ".join(errors) if errors else "All adapters failed or skipped"
        logger.error("HistoricalFallbackChain exhausted for %s: %s", method, error_summary)
        return HistoricalDataSourceResult(
            data=None,
            source="none",
            error=error_summary,
        )

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Return serialized stats for every registered adapter."""
        return {name: asdict(stats) for name, stats in self.stats.items()}

    def get_adapter(self, name: str) -> HistoricalDataAdapter | None:
        """Return the adapter with the given name, or None if not found."""
        for adapter in self.adapters:
            if adapter.name == name:
                return adapter
        return None

    def execute_single(
        self,
        adapter_name: str,
        method: str,
        *args: Any,
        **kwargs: Any,
    ) -> HistoricalDataSourceResult:
        """Execute *method* on a single named adapter (no fallback).

        Args:
            adapter_name: The adapter to use, e.g. "baostock".
            method: One of ``"fetch_sector_history"``, ``"fetch_index_history"``,
                    ``"fetch_fund_nav_history"``.
            *args, **kwargs: Forwarded to the adapter method.

        Returns:
            The ``HistoricalDataSourceResult`` from that adapter.

        Raises:
            ValueError: If the adapter is not found or does not support the method.
        """
        adapter = self.get_adapter(adapter_name)
        if adapter is None:
            raise ValueError(
                f"Unknown data source '{adapter_name}'. "
                f"Available: {[a.name for a in self.adapters]}"
            )

        fn = getattr(adapter, method, None)
        if fn is None:
            raise ValueError(f"Adapter '{adapter_name}' has no method '{method}'")

        for attempt in range(1 + _MAX_RETRIES_PER_ADAPTER):
            try:
                result_data = fn(*args, **kwargs)
                if result_data is not None and len(result_data) > 0:
                    self._update_stats(adapter.name, success=True)
                    logger.info(
                        "Historical data fetched via %s.%s (single-adapter, attempt %d)",
                        adapter.name, method, attempt + 1,
                    )
                    return HistoricalDataSourceResult(
                        data=result_data,
                        source=adapter.name,
                    )
                # Empty result -- retry
                last_error = f"Empty result from {adapter.name}.{method}"
                if attempt < _MAX_RETRIES_PER_ADAPTER:
                    logger.info(
                        "Adapter %s returned empty result on attempt %d/%d for %s, retrying",
                        adapter.name, attempt + 1, 1 + _MAX_RETRIES_PER_ADAPTER, method,
                    )
            except NotImplementedError:
                self._update_stats(adapter.name, success=False, skipped=True)
                raise ValueError(
                    f"Adapter '{adapter_name}' does not support '{method}'"
                ) from None
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Adapter %s raised on attempt %d/%d for %s: %s",
                    adapter.name, attempt + 1, 1 + _MAX_RETRIES_PER_ADAPTER, method, exc,
                )

        # All retries exhausted
        self._update_stats(adapter.name, success=False, error=last_error)
        raise ValueError(
            f"Adapter '{adapter_name}' failed for '{method}': {last_error}"
        )

    # ---- internal ----

    def _update_stats(
        self,
        adapter_name: str,
        success: bool,
        latency: float = 0.0,
        error: str | None = None,
        skipped: bool = False,
    ) -> None:
        stats = self.stats.setdefault(adapter_name, HistoricalAdapterStats())
        if success:
            stats.success_count += 1
            total = stats.success_count
            stats.avg_latency_ms = round(
                (stats.avg_latency_ms * (total - 1) + latency) / total, 2
            )
            stats.last_success_at = datetime.now(timezone.utc).isoformat()
            stats.last_error = None
        elif skipped:
            stats.skip_count += 1
        else:
            stats.failure_count += 1
            stats.last_error = error
