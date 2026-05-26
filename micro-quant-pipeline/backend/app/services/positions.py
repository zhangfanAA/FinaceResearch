import json
import sqlite3
from datetime import date, datetime, time, timezone
from typing import Any


C_CLASS_MIN_HOLDING_DAYS = 7


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _as_datetime(value: datetime | date) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _holding_days(buy_date: str, as_of: datetime) -> int:
    bought_at = datetime.fromisoformat(buy_date)
    if bought_at.tzinfo is not None and as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    if bought_at.tzinfo is None and as_of.tzinfo is not None:
        bought_at = bought_at.replace(tzinfo=timezone.utc)
    return (as_of - bought_at).days


def insert_lot(
    conn: sqlite3.Connection,
    asset_code: str,
    shares: float,
    cost_price: float,
    buy_date: datetime | date,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO lots (asset_code, buy_date, shares, cost_price, status)
        VALUES (?, ?, ?, ?, 'OPEN')
        """,
        (asset_code, _as_datetime(buy_date).isoformat(), shares, cost_price),
    )
    if commit:
        conn.commit()
    return int(cursor.lastrowid)


def insert_position(
    conn: sqlite3.Connection,
    asset_code: str,
    fund_class: str,
    quantity: float,
    buy_date: date,
    source: str,
) -> int:
    return insert_lot(conn, asset_code, quantity, 1.0, buy_date)


def list_open_lots(conn: sqlite3.Connection, asset_code: str | None = None) -> list[dict]:
    if asset_code is None:
        rows = conn.execute(
            "SELECT * FROM lots WHERE status = 'OPEN' ORDER BY buy_date, id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM lots WHERE asset_code = ? AND status = 'OPEN' ORDER BY buy_date, id",
            (asset_code,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_positions(conn: sqlite3.Connection, asset_code: str | None = None) -> list[dict]:
    return list_open_lots(conn, asset_code)


def fifo_lots(conn: sqlite3.Connection, asset_code: str) -> list[dict]:
    return list_open_lots(conn, asset_code)


def min_holding_days(conn: sqlite3.Connection, asset_code: str, as_of: date) -> int | None:
    lots = fifo_lots(conn, asset_code)
    if not lots:
        return None
    return _holding_days(lots[0]["buy_date"], _as_datetime(as_of))


def available_lots_for_sell(
    conn: sqlite3.Connection,
    asset_code: str,
    as_of: datetime | date,
    min_holding_days_required: int = C_CLASS_MIN_HOLDING_DAYS,
) -> list[dict]:
    checked_at = _as_datetime(as_of)
    return [
        lot
        for lot in fifo_lots(conn, asset_code)
        if _holding_days(lot["buy_date"], checked_at) >= min_holding_days_required
    ]


def available_shares_for_sell(
    conn: sqlite3.Connection,
    asset_code: str,
    as_of: datetime | date,
) -> float:
    return sum(float(lot["shares"]) for lot in available_lots_for_sell(conn, asset_code, as_of))


def can_sell_c_class(
    conn: sqlite3.Connection,
    asset_code: str,
    as_of: date,
    extreme_stop_loss: bool,
    crash_override: bool,
) -> tuple[bool, str]:
    lots = fifo_lots(conn, asset_code)
    if not lots:
        return False, f"No local position found for {asset_code}"
    if extreme_stop_loss:
        return True, "C-class sell allowed by extreme_stop_loss override"
    if crash_override:
        return True, "C-class sell allowed by crash_override"
    available = available_shares_for_sell(conn, asset_code, as_of)
    if available <= 0:
        youngest_blocked_days = max(_holding_days(lot["buy_date"], _as_datetime(as_of)) for lot in lots)
        return False, f"C-class holding period blocked: newest available age {youngest_blocked_days} < 7 days"
    return True, f"C-class available shares after 7-day filter: {available:g}"


def evaluate_fifo_sell(
    conn: sqlite3.Connection,
    asset_code: str,
    requested_shares: float,
    as_of: datetime | date,
    min_holding_days_required: int = C_CLASS_MIN_HOLDING_DAYS,
    allow_locked: bool = False,
) -> dict[str, Any]:
    lots = fifo_lots(conn, asset_code)
    if not lots:
        return {
            "requested_shares": requested_shares,
            "available_shares": 0.0,
            "executable_shares": 0.0,
            "blocked_shares": requested_shares,
            "partial": False,
            "reason": f"No local position found for {asset_code}",
        }

    eligible_lots = lots if allow_locked else available_lots_for_sell(
        conn, asset_code, as_of, min_holding_days_required
    )
    available = sum(float(lot["shares"]) for lot in eligible_lots)
    executable = min(requested_shares, available)
    blocked = max(requested_shares - executable, 0.0)
    partial = 0 < executable < requested_shares

    if executable <= 0:
        reason = "因 7 天锁定期，卖出指令被完全拦截"
    elif partial:
        reason = "因 7 天锁定规则，卖出指令被部分截断"
    else:
        reason = "FIFO sell allowed"

    return {
        "requested_shares": requested_shares,
        "available_shares": available,
        "executable_shares": executable,
        "blocked_shares": blocked,
        "partial": partial,
        "reason": reason,
    }


def execute_fifo_sell(
    conn: sqlite3.Connection,
    asset_code: str,
    shares_to_sell: float,
    as_of: datetime | date,
    min_holding_days_required: int = C_CLASS_MIN_HOLDING_DAYS,
    allow_locked: bool = False,
    commit: bool = True,
) -> list[dict]:
    remaining = shares_to_sell
    updated: list[dict] = []
    eligible_lots = fifo_lots(conn, asset_code) if allow_locked else available_lots_for_sell(
        conn, asset_code, as_of, min_holding_days_required
    )

    for lot in eligible_lots:
        if remaining <= 0:
            break
        lot_shares = float(lot["shares"])
        deducted = min(lot_shares, remaining)
        new_shares = lot_shares - deducted
        status = "CLOSED" if new_shares <= 0 else "OPEN"
        conn.execute(
            "UPDATE lots SET shares = ?, status = ? WHERE id = ?",
            (max(new_shares, 0.0), status, lot["id"]),
        )
        updated.append({"lot_id": lot["id"], "deducted_shares": deducted, "status": status})
        remaining -= deducted

    if commit:
        conn.commit()
    return updated


def append_paper_execution_log(
    conn: sqlite3.Connection,
    run_id: str,
    timestamp: datetime,
    asset_code: str,
    router_branch: str | None,
    raw_signal: dict,
    guard_result: dict,
    final_action: str,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO paper_execution_logs
          (run_id, timestamp, asset_code, router_branch, raw_signal, guard_result, final_action)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            timestamp.isoformat(),
            asset_code,
            router_branch,
            json.dumps(raw_signal, ensure_ascii=False),
            json.dumps(guard_result, ensure_ascii=False),
            final_action,
        ),
    )
    if commit:
        conn.commit()
    return int(cursor.lastrowid)


def recent_execution_logs(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM paper_execution_logs ORDER BY timestamp DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    logs = []
    for row in rows:
        item = _row_to_dict(row)
        item["raw_signal"] = json.loads(item["raw_signal"])
        item["guard_result"] = json.loads(item["guard_result"])
        logs.append(item)
    return logs
