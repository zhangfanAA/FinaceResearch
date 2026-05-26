"""Position operations service for MySQL-backed watchlist items.

Provides add_operation (buy/sell/add/reduce), get_operations history,
and get_summary for portfolio-level aggregation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.services.mysql_database import get_connection
from app.config import MySQLConfig

logger = logging.getLogger(__name__)


def sync_watchlist_item_to_mysql(
    mysql_cfg: MySQLConfig,
    item_type: str,
    code: str,
    name: str | None = None,
    purchase_amount: float | None = None,
    purchase_nav: float | None = None,
    purchase_date: str | None = None,
    shares: float | None = None,
    added_at: str | None = None,
    sort_order: int = 0,
) -> int:
    """Sync a watchlist item to MySQL, inserting or updating as needed.

    Returns the MySQL watchlist item id.
    """
    with get_connection(
        host=mysql_cfg.host,
        port=mysql_cfg.port,
        user=mysql_cfg.user,
        password=mysql_cfg.password,
        database=mysql_cfg.database,
        pool_size=mysql_cfg.pool_size,
    ) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM user_watchlist WHERE item_type = %s AND code = %s",
            (item_type, code),
        )
        existing = cursor.fetchone()

        if existing:
            # Update existing
            cursor.execute(
                """
                UPDATE user_watchlist
                SET name = COALESCE(%s, name),
                    purchase_amount = COALESCE(%s, purchase_amount),
                    purchase_nav = COALESCE(%s, purchase_nav),
                    purchase_date = COALESCE(%s, purchase_date),
                    shares = COALESCE(%s, shares),
                    sort_order = %s
                WHERE id = %s
                """,
                (
                    name,
                    _decimal_or_none(purchase_amount),
                    _decimal_or_none(purchase_nav),
                    purchase_date,
                    _decimal_or_none(shares),
                    sort_order,
                    existing["id"],
                ),
            )
            item_id = existing["id"]
        else:
            # Insert new
            cursor.execute(
                """
                INSERT INTO user_watchlist
                    (item_type, code, name, added_at, sort_order,
                     purchase_amount, purchase_nav, purchase_date, shares)
                VALUES (%s, %s, %s, COALESCE(%s, NOW()), %s, %s, %s, %s, %s)
                """,
                (
                    item_type,
                    code,
                    name,
                    added_at,
                    sort_order,
                    _decimal_or_none(purchase_amount),
                    _decimal_or_none(purchase_nav),
                    purchase_date,
                    _decimal_or_none(shares),
                ),
            )
            item_id = cursor.lastrowid

        cursor.close()
        return item_id


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _row_to_dict(cursor: Any) -> dict[str, Any]:
    """Convert a mysql.connector cursor row to a dict using column names."""
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, cursor.fetchone()))


def _rows_to_list(cursor: Any) -> list[dict[str, Any]]:
    """Convert all rows from a mysql.connector cursor to list of dicts."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _serialize_value(value: Any) -> Any:
    """Convert MySQL-specific types to JSON-serializable Python types."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize all values in a row dict."""
    return {k: _serialize_value(v) for k, v in row.items()}


def add_operation(
    mysql_cfg: MySQLConfig,
    watchlist_id: int,
    operation_type: str,
    operation_amount: float | None = None,
    operation_shares: float | None = None,
    operation_nav: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Execute a position operation (buy/sell/add/reduce) on a watchlist item.

    Validates the watchlist item exists and operation_type is valid.
    Updates the watchlist item's shares/NAV based on operation type.
    Records the operation in position_operations.

    Args:
        mysql_cfg: MySQL connection config.
        watchlist_id: ID of the watchlist item.
        operation_type: One of 'buy', 'sell', 'add', 'reduce'.
        operation_amount: Total transaction amount in CNY.
        operation_shares: Number of shares for this operation.
        operation_nav: NAV at time of operation.
        note: Optional note.

    Returns:
        Dict of the created operation record.

    Raises:
        ValueError: If watchlist_id not found or operation_type invalid.
        RuntimeError: If database operation fails.
    """
    valid_types = ("buy", "sell", "add", "reduce")
    if operation_type not in valid_types:
        raise ValueError(f"operation_type must be one of {valid_types}, got '{operation_type}'")

    with get_connection(
        host=mysql_cfg.host,
        port=mysql_cfg.port,
        user=mysql_cfg.user,
        password=mysql_cfg.password,
        database=mysql_cfg.database,
        pool_size=mysql_cfg.pool_size,
    ) as conn:
        cursor = conn.cursor(dictionary=True)

        # Verify watchlist item exists
        cursor.execute(
            "SELECT id, item_type, code, name, shares, purchase_nav, purchase_amount "
            "FROM user_watchlist WHERE id = %s",
            (watchlist_id,),
        )
        watchlist_item = cursor.fetchone()
        if watchlist_item is None:
            cursor.close()
            raise ValueError(f"Watchlist item with id={watchlist_id} not found")

        now = datetime.now()

        # Insert operation record
        cursor.execute(
            """
            INSERT INTO position_operations
                (watchlist_id, operation_type, operation_amount, operation_shares,
                 operation_nav, operation_date, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                watchlist_id,
                operation_type,
                _decimal_or_none(operation_amount),
                _decimal_or_none(operation_shares),
                _decimal_or_none(operation_nav),
                now,
                note,
            ),
        )
        operation_id = cursor.lastrowid

        # Update watchlist item based on operation type
        current_shares = float(watchlist_item["shares"] or 0)
        current_nav = float(watchlist_item["purchase_nav"] or 0)
        current_amount = float(watchlist_item["purchase_amount"] or 0)

        op_shares = operation_shares or 0
        op_nav = operation_nav or 0
        op_amount = operation_amount or 0

        new_shares = current_shares
        new_nav = current_nav
        new_amount = current_amount

        if operation_type in ("buy", "add"):
            # Add shares
            new_shares = current_shares + op_shares
            if op_nav > 0:
                # Weighted average NAV
                if new_shares > 0:
                    new_nav = (current_nav * current_shares + op_nav * op_shares) / new_shares
                else:
                    new_nav = op_nav
            new_amount = current_amount + op_amount
        elif operation_type in ("sell", "reduce"):
            # Remove shares
            new_shares = max(current_shares - op_shares, 0)
            new_amount = max(current_amount - op_amount, 0)
            # NAV stays the same (cost basis doesn't change on sell)

        # Calculate total P&L if we have current NAV info
        total_pnl = None
        total_pnl_pct = None
        if new_nav > 0 and op_nav > 0:
            total_pnl_pct = round((op_nav - new_nav) / new_nav * 100, 4)
            if new_shares > 0:
                total_pnl = round((op_nav - new_nav) * new_shares, 2)

        cursor.execute(
            """
            UPDATE user_watchlist
            SET shares = %s, purchase_nav = %s, purchase_amount = %s,
                current_nav = %s, current_nav_date = %s,
                total_pnl = %s, total_pnl_pct = %s
            WHERE id = %s
            """,
            (
                _decimal_or_none(new_shares),
                _decimal_or_none(new_nav),
                _decimal_or_none(new_amount),
                _decimal_or_none(op_nav) if op_nav > 0 else None,
                now.date() if op_nav > 0 else None,
                _decimal_or_none(total_pnl),
                _decimal_or_none(total_pnl_pct),
                watchlist_id,
            ),
        )

        # Fetch the created operation
        cursor.execute(
            "SELECT * FROM position_operations WHERE id = %s",
            (operation_id,),
        )
        result = cursor.fetchone()
        cursor.close()

        return _serialize_row(result)


def get_operations(
    mysql_cfg: MySQLConfig,
    watchlist_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query operation history for a watchlist item.

    Args:
        mysql_cfg: MySQL connection config.
        watchlist_id: ID of the watchlist item.
        limit: Max records to return.
        offset: Pagination offset.

    Returns:
        List of operation records as dicts.
    """
    with get_connection(
        host=mysql_cfg.host,
        port=mysql_cfg.port,
        user=mysql_cfg.user,
        password=mysql_cfg.password,
        database=mysql_cfg.database,
        pool_size=mysql_cfg.pool_size,
    ) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, watchlist_id, operation_type,
                   operation_amount, operation_shares, operation_nav,
                   operation_date, note, created_at
            FROM position_operations
            WHERE watchlist_id = %s
            ORDER BY operation_date DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (watchlist_id, limit, offset),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [_serialize_row(row) for row in rows]


def get_summary(
    mysql_cfg: MySQLConfig,
) -> dict[str, Any]:
    """Get portfolio-level position summary.

    Returns aggregated data across all watchlist items:
    - total_items: count of watchlist items
    - total_purchase_amount: sum of all purchase amounts
    - total_shares: sum of all shares
    - total_pnl: sum of all total_pnl
    - total_current_value: sum of current_nav * shares
    - items: list of watchlist items with their latest operation

    Returns:
        Summary dict.
    """
    with get_connection(
        host=mysql_cfg.host,
        port=mysql_cfg.port,
        user=mysql_cfg.user,
        password=mysql_cfg.password,
        database=mysql_cfg.database,
        pool_size=mysql_cfg.pool_size,
    ) as conn:
        cursor = conn.cursor(dictionary=True)

        # Get all watchlist items
        cursor.execute(
            """
            SELECT id, item_type, code, name, added_at, sort_order,
                   purchase_amount, purchase_nav, purchase_date, shares,
                   current_nav, current_nav_date, daily_return,
                   total_pnl, total_pnl_pct, updated_at
            FROM user_watchlist
            ORDER BY sort_order, id
            """
        )
        items = cursor.fetchall()

        # Get operation counts per watchlist item
        cursor.execute(
            """
            SELECT watchlist_id, COUNT(*) as op_count
            FROM position_operations
            GROUP BY watchlist_id
            """
        )
        op_counts = {row["watchlist_id"]: row["op_count"] for row in cursor.fetchall()}

        # Get latest operation per watchlist item
        cursor.execute(
            """
            SELECT po.watchlist_id, po.operation_type, po.operation_nav,
                   po.operation_date
            FROM position_operations po
            INNER JOIN (
                SELECT watchlist_id, MAX(id) as max_id
                FROM position_operations
                GROUP BY watchlist_id
            ) latest ON po.id = latest.max_id
            """
        )
        latest_ops = {row["watchlist_id"]: row for row in cursor.fetchall()}
        cursor.close()

        # Aggregate
        total_purchase_amount = 0.0
        total_shares = 0.0
        total_pnl = 0.0
        total_current_value = 0.0

        enriched_items = []
        for item in items:
            row = _serialize_row(item)
            purchase_amount = float(row.get("purchase_amount") or 0)
            shares = float(row.get("shares") or 0)
            pnl = float(row.get("total_pnl") or 0)
            current_nav = float(row.get("current_nav") or 0)

            total_purchase_amount += purchase_amount
            total_shares += shares
            total_pnl += pnl
            if current_nav > 0 and shares > 0:
                total_current_value += current_nav * shares

            item_id = row["id"]
            row["operation_count"] = op_counts.get(item_id, 0)
            latest = latest_ops.get(item_id)
            if latest:
                row["latest_operation"] = _serialize_row(latest)
            else:
                row["latest_operation"] = None
            enriched_items.append(row)

        total_pnl_pct = 0.0
        if total_purchase_amount > 0:
            total_pnl_pct = round(total_pnl / total_purchase_amount * 100, 4)

        return {
            "total_items": len(items),
            "total_purchase_amount": round(total_purchase_amount, 2),
            "total_shares": round(total_shares, 4),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": total_pnl_pct,
            "total_current_value": round(total_current_value, 2),
            "items": enriched_items,
        }
