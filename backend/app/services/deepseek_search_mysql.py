"""MySQL persistence layer for DeepSeek web search results.

Provides per-data-type tables with a sliding window (100 records per query_key)
to store DeepSeek search responses.  This allows the system to serve recent
search results as fallback when the DeepSeek API is temporarily unavailable.

Tables are created at startup via ``init_deepseek_tables()`` (called from
``mysql_database.init_tables``).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.services.mysql_database import get_connection

logger = logging.getLogger(__name__)

# Sliding window size: keep only the most recent N records per query_key.
WINDOW_SIZE = 100


def init_deepseek_tables(
    *,
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "",
    database: str = "Finnacequant",
    pool_size: int = 5,
) -> None:
    """Create all DeepSeek search cache tables if they do not exist.

    Safe to call multiple times (idempotent).
    """
    from app.services.mysql_database import _DEEPSEEK_SECTOR_HISTORY_DDL
    from app.services.mysql_database import _DEEPSEEK_INDEX_HISTORY_DDL
    from app.services.mysql_database import _DEEPSEEK_FUND_NAV_HISTORY_DDL
    from app.services.mysql_database import _DEEPSEEK_SECTOR_REALTIME_DDL
    from app.services.mysql_database import _DEEPSEEK_STOCK_REALTIME_DDL
    from app.services.mysql_database import _DEEPSEEK_MARKET_OVERVIEW_DDL

    ddls = [
        _DEEPSEEK_SECTOR_HISTORY_DDL,
        _DEEPSEEK_INDEX_HISTORY_DDL,
        _DEEPSEEK_FUND_NAV_HISTORY_DDL,
        _DEEPSEEK_SECTOR_REALTIME_DDL,
        _DEEPSEEK_STOCK_REALTIME_DDL,
        _DEEPSEEK_MARKET_OVERVIEW_DDL,
    ]
    with get_connection(
        host=host, port=port, user=user, password=password,
        database=database, pool_size=pool_size,
    ) as conn:
        cursor = conn.cursor()
        for ddl in ddls:
            cursor.execute(ddl)
        cursor.close()
    logger.info("DeepSeek search MySQL tables initialized")


def store(
    table: str,
    query_key: str,
    data: Any,
    *,
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "",
    database: str = "Finnacequant",
    pool_size: int = 5,
) -> None:
    """Insert a DeepSeek search result and enforce sliding window per query_key.

    Args:
        table: Target table name (e.g. ``deepseek_sector_history``).
        query_key: Unique key for this query (e.g. ``sector:白酒:industry:60``).
        data: JSON-serializable data to store.
    """
    with get_connection(
        host=host, port=port, user=user, password=password,
        database=database, pool_size=pool_size,
    ) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO {table} (query_key, data, fetched_at) VALUES (%s, %s, %s)",
            (query_key, json.dumps(data, ensure_ascii=False), time.time()),
        )
        # Sliding window: delete old rows beyond WINDOW_SIZE per query_key.
        # Uses a subquery workaround because MySQL cannot modify a table
        # that is referenced in a subquery of the same statement.
        cursor.execute(
            f"DELETE FROM {table} WHERE query_key = %s AND id NOT IN ("
            f"  SELECT id FROM ("
            f"    SELECT id FROM {table} WHERE query_key = %s ORDER BY fetched_at DESC LIMIT %s"
            f"  ) AS tmp"
            f")",
            (query_key, query_key, WINDOW_SIZE),
        )
        cursor.close()


def retrieve(
    table: str,
    query_key: str,
    *,
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "",
    database: str = "Finnacequant",
    pool_size: int = 5,
) -> dict[str, Any] | None:
    """Retrieve the most recent DeepSeek search result for a query_key.

    Returns:
        Dict with ``data`` (parsed JSON) and ``fetched_at`` (Unix timestamp),
        or ``None`` if no record exists.
    """
    with get_connection(
        host=host, port=port, user=user, password=password,
        database=database, pool_size=pool_size,
    ) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            f"SELECT data, fetched_at FROM {table} WHERE query_key = %s "
            "ORDER BY fetched_at DESC LIMIT 1",
            (query_key,),
        )
        row = cursor.fetchone()
        cursor.close()

    if row:
        return {"data": json.loads(row["data"]), "fetched_at": row["fetched_at"]}
    return None
