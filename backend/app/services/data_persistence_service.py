"""Data persistence service for API response caching with stale fallback.

Stores successful API responses to MySQL so that when all live data sources
fail, the system can return the most recent stored record with a ``stale``
flag and the original fetch timestamp.

This prevents "fake refreshes" -- the frontend can distinguish between fresh
live data and cached stale data.

Usage::

    from app.services.data_persistence_service import DataPersistenceService
    from app.config import load_config

    config = load_config()
    svc = DataPersistenceService(config.mysql)

    # Store a successful response
    svc.store("sector-history", "akshare", "白酒|industry|60", data)

    # Retrieve fallback when all sources fail
    result = svc.retrieve("sector-history", "白酒|industry|60")
    if result:
        data, source, fetched_at, is_stale = result
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import MySQLConfig
from app.services.mysql_database import get_connection

logger = logging.getLogger(__name__)


def _make_query_key(*parts: Any) -> str:
    """Generate a deterministic query key from variable parts."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class DataPersistenceService:
    """Store and retrieve API responses from MySQL for stale-data fallback.

    Each stored record is keyed by (endpoint, source, query_key).
    When retrieval is requested, the service returns the most recent record
    regardless of source, unless a specific source is requested.
    """

    def __init__(self, mysql_cfg: MySQLConfig) -> None:
        self._cfg = mysql_cfg

    def _conn(self):
        """Return a context-managed MySQL connection."""
        return get_connection(
            host=self._cfg.host,
            port=self._cfg.port,
            user=self._cfg.user,
            password=self._cfg.password,
            database=self._cfg.database,
            pool_size=self._cfg.pool_size,
        )

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store(
        self,
        endpoint: str,
        source: str,
        query_key: str,
        data: list[dict[str, Any]] | dict[str, Any],
    ) -> None:
        """Store a successful API response.

        Uses INSERT ... ON DUPLICATE KEY UPDATE so repeated calls with the
        same (endpoint, source, query_key) overwrite the previous record.

        Args:
            endpoint: Endpoint identifier, e.g. "sector-history".
            source: Data source name, e.g. "akshare", "tushare".
            query_key: Pre-computed query key string.
            data: The response payload (will be JSON-serialized).
        """
        data_json = json.dumps(data, ensure_ascii=False, default=str)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO data_source_cache
                        (endpoint, source, query_key, data, fetched_at, stale)
                    VALUES (%s, %s, %s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE
                        data = VALUES(data),
                        fetched_at = VALUES(fetched_at),
                        stale = 0
                    """,
                    (endpoint, source, query_key, data_json, now),
                )
                cursor.close()
                logger.debug(
                    "Stored data for endpoint=%s source=%s key=%s",
                    endpoint, source, query_key[:12],
                )
        except Exception as exc:
            logger.warning(
                "Failed to store data for endpoint=%s source=%s: %s",
                endpoint, source, exc,
            )

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def retrieve(
        self,
        endpoint: str,
        query_key: str,
        preferred_source: str | None = None,
    ) -> tuple[list[dict[str, Any]] | dict[str, Any], str, str, bool] | None:
        """Retrieve the most recent stored record for an endpoint.

        Args:
            endpoint: Endpoint identifier.
            query_key: Pre-computed query key string.
            preferred_source: If set, prefer this source; otherwise use
                the most recent record across all sources.

        Returns:
            Tuple of (data, source, fetched_at_iso, is_stale) or None if
            no record exists.

            ``is_stale`` is always True for retrieved fallback data (the
            caller should set it to False only for fresh live data).
        """
        try:
            with self._conn() as conn:
                cursor = conn.cursor(dictionary=True)

                if preferred_source:
                    cursor.execute(
                        """
                        SELECT data, source, fetched_at
                        FROM data_source_cache
                        WHERE endpoint = %s AND query_key = %s AND source = %s
                        ORDER BY fetched_at DESC
                        LIMIT 1
                        """,
                        (endpoint, query_key, preferred_source),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT data, source, fetched_at
                        FROM data_source_cache
                        WHERE endpoint = %s AND query_key = %s
                        ORDER BY fetched_at DESC
                        LIMIT 1
                        """,
                        (endpoint, query_key),
                    )

                row = cursor.fetchone()
                cursor.close()

                if row is None:
                    return None

                data = json.loads(row["data"])
                source = row["source"]
                fetched_at = row["fetched_at"]

                # Normalize fetched_at to ISO string
                if isinstance(fetched_at, datetime):
                    fetched_at_iso = fetched_at.isoformat()
                else:
                    fetched_at_iso = str(fetched_at)

                logger.info(
                    "Retrieved stale fallback for endpoint=%s source=%s fetched_at=%s",
                    endpoint, source, fetched_at_iso,
                )

                return (data, source, fetched_at_iso, True)

        except Exception as exc:
            logger.warning(
                "Failed to retrieve fallback for endpoint=%s: %s",
                endpoint, exc,
            )
            return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_old_records(self, days: int = 30) -> int:
        """Delete records older than *days* days.

        Returns:
            Number of deleted records.
        """
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM data_source_cache
                    WHERE fetched_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                    """,
                    (days,),
                )
                deleted = cursor.rowcount
                cursor.close()
                if deleted > 0:
                    logger.info("Cleaned up %d old data_source_cache records", deleted)
                return deleted
        except Exception as exc:
            logger.warning("Failed to cleanup old records: %s", exc)
            return 0


# ---------------------------------------------------------------------------
# Module-level helper: build query keys for known endpoints
# ---------------------------------------------------------------------------


def sector_history_key(sector_name: str, sector_type: str, days: int) -> str:
    """Build query key for sector-history endpoint."""
    return _make_query_key(sector_name, sector_type, days)


def index_history_key(code: str, days: int) -> str:
    """Build query key for index-history endpoint."""
    return _make_query_key(code, days)


def fund_nav_history_key(code: str, days: int) -> str:
    """Build query key for fund-nav-history endpoint."""
    return _make_query_key(code, days)


def stock_realtime_key(codes: list[str]) -> str:
    """Build query key for stock-realtime endpoint."""
    return _make_query_key(*sorted(codes))


def fund_nav_key(codes: list[str]) -> str:
    """Build query key for fund-nav endpoint."""
    return _make_query_key(*sorted(codes))


def sector_list_key(sector_type: str, limit: int) -> str:
    """Build query key for sectors endpoint."""
    return _make_query_key(sector_type, limit)


def market_overview_key() -> str:
    """Build query key for market-overview endpoint (no params)."""
    return _make_query_key("market_overview")
