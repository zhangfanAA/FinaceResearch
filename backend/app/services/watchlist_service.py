"""Watchlist management service for user stock/fund tracking.

Provides CRUD operations on the user_watchlist table with auto-name
resolution from AkShare when a name is not supplied by the caller.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from app.services import database

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_stock_name(code: str) -> str | None:
    """Try to fetch a stock name from AkShare spot data. Returns None on failure."""
    try:
        import akshare as ak  # noqa: F811

        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            row = df[df["代码"] == code.strip()]
            if not row.empty:
                name = row.iloc[0].get("名称")
                if name and str(name).strip():
                    return str(name).strip()
    except Exception as exc:
        logger.debug("AkShare stock name lookup failed for %s: %s", code, exc)
    return None


def _resolve_fund_name(code: str) -> str | None:
    """Try to fetch a fund name from AkShare fund info. Returns None on failure."""
    try:
        import akshare as ak  # noqa: F811

        df = ak.fund_open_fund_info_em(symbol=code.strip(), indicator="基金概况")
        if df is not None and not df.empty:
            name = df.iloc[0].get("基金简称")
            if name and str(name).strip():
                return str(name).strip()
    except Exception as exc:
        logger.debug("AkShare fund name lookup failed for %s: %s", code, exc)
    return None


def _auto_resolve_name(item_type: str, code: str) -> str | None:
    """Dispatch name resolution to the correct AkShare helper."""
    if item_type == "stock":
        return _resolve_stock_name(code)
    if item_type == "fund":
        return _resolve_fund_name(code)
    return None


def get_watchlist(
    conn: sqlite3.Connection,
    item_type: str | None = None,
) -> list[dict]:
    """Return watchlist items, optionally filtered by type.

    Args:
        conn: SQLite connection (must have called init_db).
        item_type: ``'stock'``, ``'fund'``, or ``None`` for all.
    Returns:
        List of dicts with keys: id, item_type, code, name, added_at, sort_order,
        purchase_amount, purchase_nav, purchase_date, shares.
    """
    return database.get_watchlist(conn, item_type=item_type)


def add_to_watchlist(
    conn: sqlite3.Connection,
    item_type: str,
    code: str,
    name: str | None = None,
    *,
    purchase_amount: float | None = None,
    purchase_nav: float | None = None,
    purchase_date: str | None = None,
    shares: float | None = None,
) -> dict:
    """Add an item to the watchlist with de-duplication.

    If the (item_type, code) pair already exists the existing row is returned.
    If *name* is ``None`` the service attempts AkShare lookup (best-effort).

    Args:
        conn: SQLite connection.
        item_type: ``'stock'`` or ``'fund'``.
        code: Asset code.
        name: Optional display name.
        purchase_amount: Total purchase amount in CNY.
        purchase_nav: NAV at time of purchase.
        purchase_date: Date of purchase (ISO format).
        shares: Number of shares held.

    Returns:
        Dict of the watchlist row (newly inserted or existing).

    Raises:
        ValueError: if item_type is invalid or code is blank.
    """
    if item_type not in ("stock", "fund"):
        raise ValueError(f"item_type must be 'stock' or 'fund', got '{item_type}'")
    code = code.strip()
    if not code:
        raise ValueError("code must not be empty")

    # Dedup check
    existing = database.get_watchlist_item_by_code(conn, item_type, code)
    if existing is not None:
        return existing

    # Auto-resolve name if not provided
    resolved_name = name
    if resolved_name is None:
        resolved_name = _auto_resolve_name(item_type, code)

    added_at = _now_iso()
    # Compute next sort_order = max + 1
    all_items = database.get_watchlist(conn, item_type=item_type)
    max_order = max((item["sort_order"] for item in all_items), default=-1)
    next_order = max_order + 1

    item_id = database.insert_watchlist_item(
        conn,
        item_type=item_type,
        code=code,
        name=resolved_name,
        added_at=added_at,
        sort_order=next_order,
        purchase_amount=purchase_amount,
        purchase_nav=purchase_nav,
        purchase_date=purchase_date,
        shares=shares,
    )
    return {
        "id": item_id,
        "item_type": item_type,
        "code": code,
        "name": resolved_name,
        "added_at": added_at,
        "sort_order": next_order,
        "purchase_amount": purchase_amount,
        "purchase_nav": purchase_nav,
        "purchase_date": purchase_date,
        "shares": shares,
    }


def update_watchlist_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    name: str | None = None,
    purchase_amount: float | None = None,
    purchase_nav: float | None = None,
    purchase_date: str | None = None,
    shares: float | None = None,
) -> bool:
    """Update a watchlist item's purchase info."""
    return database.update_watchlist_item(
        conn,
        item_id,
        name=name,
        purchase_amount=purchase_amount,
        purchase_nav=purchase_nav,
        purchase_date=purchase_date,
        shares=shares,
    )


def remove_from_watchlist(conn: sqlite3.Connection, item_id: int) -> bool:
    """Remove a watchlist item by id.

    Returns True if a row was deleted, False if the id was not found.
    """
    return database.delete_watchlist_item(conn, item_id)


def reorder_watchlist(conn: sqlite3.Connection, item_ids: list[int]) -> None:
    """Bulk-update sort_order for the given item ids.

    The order of *item_ids* determines the new sort_order values (0-based).
    """
    database.update_watchlist_sort_order(conn, item_ids)
