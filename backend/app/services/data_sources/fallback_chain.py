"""FallbackChain -- executes adapters in priority order, returning the first success.

Tracks per-adapter success/failure statistics for the ``/api/system/data-source-status``
endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.services.data_sources.base import AdapterStats, DataSourceAdapter, DataSourceResult

logger = logging.getLogger(__name__)


class FallbackChain:
    """Try each adapter in priority order; return the first successful result.

    If every adapter fails, returns a ``DataSourceResult`` with ``data=None``
    and an error summary so the caller always receives a well-formed envelope.
    """

    def __init__(self, adapters: list[DataSourceAdapter]) -> None:
        self.adapters = sorted(adapters, key=lambda a: a.priority)
        self.stats: dict[str, AdapterStats] = {}
        for adapter in self.adapters:
            self.stats.setdefault(adapter.name, AdapterStats())

    def execute(self, method: str, *args: object, **kwargs: object) -> DataSourceResult:
        """Execute *method* on each adapter until one succeeds.

        Each adapter is retried up to ``max_retries`` times on transient
        failures before moving to the next adapter in the chain.

        Args:
            method: One of ``"fetch_stock_realtime"``, ``"fetch_sector_list"``,
                    ``"fetch_fund_nav"``.
            *args, **kwargs: Forwarded to the adapter method.

        Returns:
            The first ``DataSourceResult`` with ``error is None`` and
            ``data is not None``.  If all fail, returns an error envelope.
        """
        max_retries = 2  # Per-adapter retry count (in addition to initial call)
        errors: list[str] = []
        for adapter in self.adapters:
            fn = getattr(adapter, method, None)
            if fn is None:
                continue
            last_error = None
            for attempt in range(1 + max_retries):
                try:
                    result = fn(*args, **kwargs)
                    has_data = result.data is not None and (
                        not isinstance(result.data, (list, dict)) or len(result.data) > 0
                    )
                    if result.error is None and has_data:
                        self._update_stats(adapter.name, success=True, latency=result.latency_ms)
                        return result
                    # Adapter returned error envelope or empty data
                    last_error = result.error
                    if attempt < max_retries:
                        logger.info(
                            "Adapter %s returned error on attempt %d/%d for %s, retrying: %s",
                            adapter.name, attempt + 1, 1 + max_retries, method, result.error,
                        )
                except Exception as exc:
                    last_error = str(exc)
                    logger.warning(
                        "Adapter %s raised on attempt %d/%d for %s: %s",
                        adapter.name, attempt + 1, 1 + max_retries, method, exc,
                    )
            # All retries for this adapter exhausted
            self._update_stats(adapter.name, success=False, error=last_error)
            errors.append(f"[{adapter.name}] {last_error}")

        # All adapters failed -- return error envelope (no mock fallback)
        error_summary = "; ".join(errors) if errors else "All adapters failed"
        logger.error("FallbackChain exhausted for %s: %s", method, error_summary)
        return DataSourceResult(
            data=None,
            source="none",
            is_mock=False,
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
