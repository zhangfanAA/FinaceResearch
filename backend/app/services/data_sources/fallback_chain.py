"""FallbackChain -- executes adapters in priority order, returning the first success.

Tracks per-adapter success/failure statistics for the ``/api/system/data-source-status``
endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.services.data_sources.base import AdapterStats, DataSourceAdapter, DataSourceResult
from app.services.data_sources.mock_adapter import MockAdapter

logger = logging.getLogger(__name__)


class FallbackChain:
    """Try each adapter in priority order; return the first successful result.

    If every adapter fails, returns a mock ``DataSourceResult`` with an error
    summary so the caller always receives a well-formed envelope.
    """

    def __init__(self, adapters: list[DataSourceAdapter]) -> None:
        self.adapters = sorted(adapters, key=lambda a: a.priority)
        self.stats: dict[str, AdapterStats] = {}
        for adapter in self.adapters:
            self.stats.setdefault(adapter.name, AdapterStats())

    def execute(self, method: str, *args: object, **kwargs: object) -> DataSourceResult:
        """Execute *method* on each adapter until one succeeds.

        Args:
            method: One of ``"fetch_stock_realtime"``, ``"fetch_sector_list"``,
                    ``"fetch_fund_nav"``.
            *args, **kwargs: Forwarded to the adapter method.

        Returns:
            The first ``DataSourceResult`` with ``error is None`` and
            ``data is not None``.  If all fail, returns a mock result.
        """
        errors: list[str] = []
        for adapter in self.adapters:
            fn = getattr(adapter, method, None)
            if fn is None:
                continue
            try:
                result = fn(*args, **kwargs)
                has_data = result.data is not None and (
                    not isinstance(result.data, (list, dict)) or len(result.data) > 0
                )
                if result.error is None and has_data:
                    self._update_stats(adapter.name, success=True, latency=result.latency_ms)
                    return result
                # Adapter returned an error envelope or empty data -- record and try next
                self._update_stats(adapter.name, success=False, error=result.error)
                errors.append(f"[{adapter.name}] {result.error}")
            except Exception as exc:
                self._update_stats(adapter.name, success=False, error=str(exc))
                errors.append(f"[{adapter.name}] {exc}")
                logger.warning("Adapter %s raised for %s: %s", adapter.name, method, exc)

        # All adapters failed -- return mock as absolute last resort
        error_summary = "; ".join(errors) if errors else "All adapters failed"
        logger.error("FallbackChain exhausted for %s: %s", method, error_summary)
        return DataSourceResult(
            data=None,
            source="none",
            is_mock=True,
            error=error_summary,
        )

    def get_status(self) -> dict[str, dict]:
        """Return serialised stats for every registered adapter."""
        return {name: asdict(stats) for name, stats in self.stats.items()}

    # ---- internal ----

    def _update_stats(
        self,
        adapter_name: str,
        success: bool,
        latency: float = 0.0,
        error: str | None = None,
    ) -> None:
        stats = self.stats.setdefault(adapter_name, AdapterStats())
        if success:
            stats.success_count += 1
            # Running average
            total = stats.success_count
            stats.avg_latency_ms = round(
                (stats.avg_latency_ms * (total - 1) + latency) / total, 2
            )
            stats.last_success_at = datetime.now(timezone.utc).isoformat()
            stats.last_error = None
        else:
            stats.failure_count += 1
            stats.last_error = error
