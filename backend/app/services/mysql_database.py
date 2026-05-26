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
