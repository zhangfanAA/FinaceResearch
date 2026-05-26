"""MySQL database connection pool and schema initialization.

Provides a thread-safe connection pool using mysql.connector,
a context-managed get_connection helper, and init_tables for
creating all required MySQL tables.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection Pool
# ---------------------------------------------------------------------------

_pool: pooling.MySQLConnectionPool | None = None


def _get_pool(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    pool_size: int = 5,
) -> pooling.MySQLConnectionPool:
    """Return the global connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="finance_quant_pool",
            pool_size=pool_size,
            pool_reset_session=True,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            collation="utf8mb4_general_ci",
            autocommit=False,
        )
        logger.info("MySQL connection pool created (pool_size=%d, db=%s)", pool_size, database)
    return _pool


def init_pool(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    pool_size: int = 5,
) -> None:
    """Explicitly initialize (or re-initialize) the global pool."""
    global _pool
    _pool = None
    _get_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        pool_size=pool_size,
    )


@contextmanager
def get_connection(
    *,
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "",
    database: str = "Finnacequant",
    pool_size: int = 5,
) -> Generator[Any, None, None]:
    """Context manager that yields a pooled MySQL connection.

    Commits on success, rolls back on exception, and always returns
    the connection to the pool.
    """
    pool = _get_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        pool_size=pool_size,
    )
    conn = pool.get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_USER_WATCHLIST_DDL = """
CREATE TABLE IF NOT EXISTS user_watchlist (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_type ENUM('stock', 'fund') NOT NULL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    added_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sort_order INT DEFAULT 0,
    purchase_amount DECIMAL(15,2),
    purchase_nav DECIMAL(10,4),
    purchase_date DATE,
    shares DECIMAL(15,4),
    current_nav DECIMAL(10,4),
    current_nav_date DATE,
    daily_return DECIMAL(8,4),
    total_pnl DECIMAL(15,2),
    total_pnl_pct DECIMAL(8,4),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_item_type_code (item_type, code),
    INDEX idx_item_type (item_type),
    INDEX idx_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_POSITION_OPERATIONS_DDL = """
CREATE TABLE IF NOT EXISTS position_operations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    watchlist_id INT NOT NULL,
    operation_type ENUM('buy', 'sell', 'add', 'reduce') NOT NULL,
    operation_amount DECIMAL(15,2),
    operation_shares DECIMAL(15,4),
    operation_nav DECIMAL(10,4),
    operation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (watchlist_id) REFERENCES user_watchlist(id) ON DELETE CASCADE,
    INDEX idx_watchlist_id (watchlist_id),
    INDEX idx_operation_date (operation_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_ANALYSIS_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS analysis_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    analysis_type ENUM('stock_sector', 'fund_sector', 'watchlist', 'ai_wind') NOT NULL,
    target_code VARCHAR(20) NOT NULL,
    target_name VARCHAR(100),
    llm_prompt TEXT,
    llm_raw_output LONGTEXT,
    parsed_result JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_analysis_type (analysis_type),
    INDEX idx_target_code (target_code),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# ---------------------------------------------------------------------------
# Data Source Cache / Persistence Table
# ---------------------------------------------------------------------------
# Stores API responses from each data source so that when all live sources
# fail, the system can fall back to the most recent stored record.
# Composite unique key: (endpoint, source, query_key) prevents duplicates.
# fetched_at timestamp prevents "fake refreshes" (showing stale as fresh).

_DATA_SOURCE_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS data_source_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    endpoint VARCHAR(100) NOT NULL COMMENT 'API endpoint identifier, e.g. sector-history',
    source VARCHAR(50) NOT NULL COMMENT 'Data source name: tushare/baostock/efinance/akshare/eastmoney',
    query_key VARCHAR(255) NOT NULL COMMENT 'Hash or composite of query params',
    data JSON NOT NULL COMMENT 'Cached API response payload',
    fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When data was originally fetched',
    stale TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 if this record was served as stale fallback',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_endpoint_source_query (endpoint, source, query_key),
    INDEX idx_endpoint (endpoint),
    INDEX idx_source (source),
    INDEX idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


# ---------------------------------------------------------------------------
# DeepSeek Search Cache Tables
# ---------------------------------------------------------------------------
# Per-data-type tables storing DeepSeek web search results with a sliding
# window (100 records per query_key).  Used as last-resort fallback when
# all traditional data sources and the live DeepSeek API are unavailable.

_DEEPSEEK_SECTOR_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS deepseek_sector_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    query_key VARCHAR(255) NOT NULL,
    data JSON NOT NULL,
    source VARCHAR(50) DEFAULT 'deepseek',
    fetched_at DOUBLE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_query_key (query_key),
    INDEX idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DEEPSEEK_INDEX_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS deepseek_index_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    query_key VARCHAR(255) NOT NULL,
    data JSON NOT NULL,
    source VARCHAR(50) DEFAULT 'deepseek',
    fetched_at DOUBLE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_query_key (query_key),
    INDEX idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DEEPSEEK_FUND_NAV_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS deepseek_fund_nav_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    query_key VARCHAR(255) NOT NULL,
    data JSON NOT NULL,
    source VARCHAR(50) DEFAULT 'deepseek',
    fetched_at DOUBLE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_query_key (query_key),
    INDEX idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DEEPSEEK_SECTOR_REALTIME_DDL = """
CREATE TABLE IF NOT EXISTS deepseek_sector_realtime (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    query_key VARCHAR(255) NOT NULL,
    data JSON NOT NULL,
    source VARCHAR(50) DEFAULT 'deepseek',
    fetched_at DOUBLE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_query_key (query_key),
    INDEX idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DEEPSEEK_STOCK_REALTIME_DDL = """
CREATE TABLE IF NOT EXISTS deepseek_stock_realtime (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    query_key VARCHAR(255) NOT NULL,
    data JSON NOT NULL,
    source VARCHAR(50) DEFAULT 'deepseek',
    fetched_at DOUBLE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_query_key (query_key),
    INDEX idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DEEPSEEK_MARKET_OVERVIEW_DDL = """
CREATE TABLE IF NOT EXISTS deepseek_market_overview (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    query_key VARCHAR(255) NOT NULL,
    data JSON NOT NULL,
    source VARCHAR(50) DEFAULT 'deepseek',
    fetched_at DOUBLE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_query_key (query_key),
    INDEX idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def init_tables(
    *,
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "",
    database: str = "Finnacequant",
    pool_size: int = 5,
) -> None:
    """Create all MySQL tables if they do not exist.

    Safe to call multiple times (idempotent).
    """
    with get_connection(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        pool_size=pool_size,
    ) as conn:
        cursor = conn.cursor()
        cursor.execute(_USER_WATCHLIST_DDL)
        cursor.execute(_POSITION_OPERATIONS_DDL)
        cursor.execute(_ANALYSIS_LOGS_DDL)
        cursor.execute(_DATA_SOURCE_CACHE_DDL)
        # DeepSeek search cache tables
        cursor.execute(_DEEPSEEK_SECTOR_HISTORY_DDL)
        cursor.execute(_DEEPSEEK_INDEX_HISTORY_DDL)
        cursor.execute(_DEEPSEEK_FUND_NAV_HISTORY_DDL)
        cursor.execute(_DEEPSEEK_SECTOR_REALTIME_DDL)
        cursor.execute(_DEEPSEEK_STOCK_REALTIME_DDL)
        cursor.execute(_DEEPSEEK_MARKET_OVERVIEW_DDL)
        # Migrate analysis_logs ENUM to include 'ai_wind' for existing databases
        try:
            cursor.execute(
                "ALTER TABLE analysis_logs MODIFY COLUMN analysis_type "
                "ENUM('stock_sector', 'fund_sector', 'watchlist', 'ai_wind') NOT NULL"
            )
        except Exception as exc:
            logger.debug("ALTER TABLE analysis_logs skipped (may already be up to date): %s", exc)
        cursor.close()
        logger.info("MySQL tables initialized successfully")
