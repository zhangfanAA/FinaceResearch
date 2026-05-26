"""SQLite-backed cache for historical financial data.

Stores cached API responses keyed by an MD5 hash of (adapter_name + method + params).
Default TTL is 4 hours. Supports get, set, and expired-entry cleanup.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TTL_HOURS = 4.0
_DEFAULT_DB_PATH = "data/historical_cache.db"


def _make_key(adapter_name: str, method: str, **params: Any) -> str:
    """Generate a deterministic cache key from adapter name, method, and params."""
    raw = f"{adapter_name}:{method}:{json.dumps(params, sort_keys=True, default=str)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class HistoricalCache:
    """SQLite cache for historical data fetch results.

    Table schema:
        cache_entries(
            key TEXT PRIMARY KEY,
            data TEXT,          -- JSON-serialized result
            cached_at REAL,     -- time.time() at insertion
            ttl_hours REAL      -- TTL in hours
        )
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._db_path = str(db_path)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection with row_factory."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_table(self) -> None:
        """Create the cache_entries table if it does not exist."""
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    cached_at REAL NOT NULL,
                    ttl_hours REAL NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get(
        self,
        adapter_name: str,
        method: str,
        **params: Any,
    ) -> list[dict[str, Any]] | None:
        """Retrieve cached data if it exists and has not expired.

        Args:
            adapter_name: Name of the adapter that produced the data.
            method: The fetch method name.
            **params: The parameters that were passed to the fetch method.

        Returns:
            The cached data as a list of dicts, or None if cache miss / expired.
        """
        key = _make_key(adapter_name, method, **params)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data, cached_at, ttl_hours FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None

            cached_at = float(row["cached_at"])
            ttl_hours = float(row["ttl_hours"])
            age_hours = (time.time() - cached_at) / 3600.0

            if age_hours > ttl_hours:
                # Expired -- delete and return miss
                conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                conn.commit()
                logger.debug("Cache expired for key=%s (age=%.2fh, ttl=%.2fh)", key, age_hours, ttl_hours)
                return None

            data = json.loads(row["data"])
            logger.debug("Cache hit for key=%s (age=%.2fh)", key, age_hours)
            return data
        finally:
            conn.close()

    def set(
        self,
        adapter_name: str,
        method: str,
        data: list[dict[str, Any]],
        ttl_hours: float = _DEFAULT_TTL_HOURS,
        **params: Any,
    ) -> None:
        """Store data in the cache.

        Args:
            adapter_name: Name of the adapter that produced the data.
            method: The fetch method name.
            data: The data to cache (will be JSON-serialized).
            ttl_hours: Time-to-live in hours.
            **params: The parameters that were passed to the fetch method.
        """
        key = _make_key(adapter_name, method, **params)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_entries (key, data, cached_at, ttl_hours)
                VALUES (?, ?, ?, ?)
                """,
                (key, json.dumps(data, ensure_ascii=False, default=str), time.time(), ttl_hours),
            )
            conn.commit()
            logger.debug("Cached data for key=%s (ttl=%.2fh)", key, ttl_hours)
        finally:
            conn.close()

    def clear_expired(self) -> int:
        """Remove all expired cache entries.

        Returns:
            Number of entries removed.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                DELETE FROM cache_entries
                WHERE (cached_at + ttl_hours * 3600.0) < ?
                """,
                (time.time(),),
            )
            conn.commit()
            removed = cursor.rowcount
            if removed > 0:
                logger.info("Cleared %d expired cache entries", removed)
            return removed
        finally:
            conn.close()

    def clear_all(self) -> int:
        """Remove all cache entries.

        Returns:
            Number of entries removed.
        """
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM cache_entries")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
