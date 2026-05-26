import sqlite3
from pathlib import Path
from typing import Iterable


LOTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS lots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_code TEXT NOT NULL,
  buy_date TEXT NOT NULL,
  shares REAL NOT NULL,
  cost_price REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')) DEFAULT 'OPEN'
);
"""

PAPER_EXECUTION_LOGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_execution_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  asset_code TEXT NOT NULL,
  router_branch TEXT,
  raw_signal TEXT NOT NULL,
  guard_result TEXT NOT NULL,
  final_action TEXT NOT NULL
);
"""

APP_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

STOCK_QUOTES_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_quotes_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    current_price REAL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    prev_close REAL,
    volume REAL,
    amount REAL,
    change_pct REAL,
    sector_name TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(stock_code)
);
"""

SECTOR_QUOTES_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sector_quotes_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_code TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    sector_type TEXT NOT NULL CHECK (sector_type IN ('industry', 'concept')),
    change_pct REAL,
    turnover_rate REAL,
    leading_stock TEXT,
    rise_count INTEGER,
    fall_count INTEGER,
    fetched_at TEXT NOT NULL,
    UNIQUE(sector_code, sector_type)
);
"""

FUND_NAV_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fund_nav_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    fund_name TEXT,
    nav REAL,
    acc_nav REAL,
    nav_date TEXT,
    daily_return REAL,
    fetched_at TEXT NOT NULL,
    UNIQUE(fund_code)
);
"""

ANALYSIS_LOGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_type TEXT NOT NULL CHECK (analysis_type IN ('stock_sector', 'fund_sector')),
    target_code TEXT NOT NULL,
    target_name TEXT,
    llm_prompt TEXT,
    llm_raw_output TEXT,
    parsed_result TEXT,
    created_at TEXT NOT NULL
);
"""

USER_WATCHLIST_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL CHECK (item_type IN ('stock', 'fund')),
    code TEXT NOT NULL,
    name TEXT,
    added_at TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    purchase_amount REAL,
    purchase_nav REAL,
    purchase_date TEXT,
    shares REAL,
    UNIQUE(item_type, code)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _migrate_watchlist_purchase_fields(conn: sqlite3.Connection) -> None:
    """Add purchase info columns to user_watchlist if they don't exist."""
    if not _table_exists(conn, "user_watchlist"):
        return
    columns = _table_columns(conn, "user_watchlist")
    migrations = [
        ("purchase_amount", "REAL"),
        ("purchase_nav", "REAL"),
        ("purchase_date", "TEXT"),
        ("shares", "REAL"),
    ]
    for col_name, col_type in migrations:
        if col_name not in columns:
            conn.execute(f"ALTER TABLE user_watchlist ADD COLUMN {col_name} {col_type}")


def _migrate_positions_to_lots(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "positions"):
        return
    columns = _table_columns(conn, "positions")
    required = {"asset_code", "quantity", "buy_date"}
    if not required.issubset(columns):
        return

    rows = conn.execute("SELECT * FROM positions ORDER BY buy_date, id").fetchall()
    for row in rows:
        exists = conn.execute(
            """
            SELECT id FROM lots
            WHERE asset_code = ? AND buy_date = ? AND shares = ? AND status = 'OPEN'
            LIMIT 1
            """,
            (row["asset_code"], row["buy_date"], row["quantity"]),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO lots (asset_code, buy_date, shares, cost_price, status)
            VALUES (?, ?, ?, ?, 'OPEN')
            """,
            (row["asset_code"], row["buy_date"], row["quantity"], 1.0),
        )


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(LOTS_SCHEMA)
    conn.execute(PAPER_EXECUTION_LOGS_SCHEMA)
    conn.execute(APP_SETTINGS_SCHEMA)
    conn.execute(STOCK_QUOTES_CACHE_SCHEMA)
    conn.execute(SECTOR_QUOTES_CACHE_SCHEMA)
    conn.execute(FUND_NAV_CACHE_SCHEMA)
    conn.execute(ANALYSIS_LOGS_SCHEMA)
    conn.execute(USER_WATCHLIST_SCHEMA)
    _migrate_watchlist_purchase_fields(conn)
    _migrate_positions_to_lots(conn)
    conn.commit()


def get_app_settings(conn: sqlite3.Connection, keys: Iterable[str] | None = None) -> dict[str, str]:
    if keys is None:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    else:
        keys = list(keys)
        if not keys:
            return {}
        placeholders = ", ".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
            tuple(keys),
        ).fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def set_app_setting(
    conn: sqlite3.Connection,
    key: str,
    value: str,
    *,
    updated_at: str,
    commit: bool = True,
) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, updated_at),
    )
    if commit:
        conn.commit()


def delete_app_setting(conn: sqlite3.Connection, key: str, commit: bool = True) -> None:
    conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    if commit:
        conn.commit()


# ---- Watchlist CRUD helpers ----


def get_watchlist(
    conn: sqlite3.Connection,
    item_type: str | None = None,
) -> list[dict]:
    """Return watchlist rows, optionally filtered by item_type ('stock' or 'fund')."""
    if item_type is not None:
        rows = conn.execute(
            "SELECT id, item_type, code, name, added_at, sort_order, "
            "purchase_amount, purchase_nav, purchase_date, shares "
            "FROM user_watchlist WHERE item_type = ? ORDER BY sort_order, id",
            (item_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, item_type, code, name, added_at, sort_order, "
            "purchase_amount, purchase_nav, purchase_date, shares "
            "FROM user_watchlist ORDER BY sort_order, id",
        ).fetchall()
    return [dict(row) for row in rows]


def insert_watchlist_item(
    conn: sqlite3.Connection,
    item_type: str,
    code: str,
    name: str | None,
    added_at: str,
    sort_order: int = 0,
    *,
    purchase_amount: float | None = None,
    purchase_nav: float | None = None,
    purchase_date: str | None = None,
    shares: float | None = None,
    commit: bool = True,
) -> int:
    """Insert a watchlist row. Returns the new row id.

    Raises sqlite3.IntegrityError if (item_type, code) already exists.
    """
    cursor = conn.execute(
        "INSERT INTO user_watchlist (item_type, code, name, added_at, sort_order, "
        "purchase_amount, purchase_nav, purchase_date, shares) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_type, code, name, added_at, sort_order,
         purchase_amount, purchase_nav, purchase_date, shares),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def delete_watchlist_item(conn: sqlite3.Connection, item_id: int, *, commit: bool = True) -> bool:
    """Delete a watchlist row by id. Returns True if a row was deleted."""
    cursor = conn.execute("DELETE FROM user_watchlist WHERE id = ?", (item_id,))
    if commit:
        conn.commit()
    return cursor.rowcount > 0


def update_watchlist_sort_order(
    conn: sqlite3.Connection,
    item_ids: list[int],
    *,
    commit: bool = True,
) -> None:
    """Bulk-update sort_order for a list of item ids (order = list index)."""
    for idx, item_id in enumerate(item_ids):
        conn.execute(
            "UPDATE user_watchlist SET sort_order = ? WHERE id = ?",
            (idx, item_id),
        )
    if commit:
        conn.commit()


def update_watchlist_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    name: str | None = None,
    purchase_amount: float | None = None,
    purchase_nav: float | None = None,
    purchase_date: str | None = None,
    shares: float | None = None,
    commit: bool = True,
) -> bool:
    """Update a watchlist item's purchase info. Returns True if a row was updated."""
    updates = []
    params: list = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if purchase_amount is not None:
        updates.append("purchase_amount = ?")
        params.append(purchase_amount)
    if purchase_nav is not None:
        updates.append("purchase_nav = ?")
        params.append(purchase_nav)
    if purchase_date is not None:
        updates.append("purchase_date = ?")
        params.append(purchase_date)
    if shares is not None:
        updates.append("shares = ?")
        params.append(shares)
    if not updates:
        return False
    params.append(item_id)
    cursor = conn.execute(
        f"UPDATE user_watchlist SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    if commit:
        conn.commit()
    return cursor.rowcount > 0


def get_watchlist_item_by_code(
    conn: sqlite3.Connection,
    item_type: str,
    code: str,
) -> dict | None:
    """Look up a single watchlist entry by (item_type, code)."""
    row = conn.execute(
        "SELECT id, item_type, code, name, added_at, sort_order, "
        "purchase_amount, purchase_nav, purchase_date, shares "
        "FROM user_watchlist WHERE item_type = ? AND code = ?",
        (item_type, code),
    ).fetchone()
    return dict(row) if row else None
