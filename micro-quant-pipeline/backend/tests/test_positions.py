from datetime import date, datetime, timedelta, timezone

from app.services import database, positions


def make_conn():
    conn = database.connect(":memory:")
    database.init_db(conn)
    return conn


def test_empty_positions_block_c_class_sell():
    conn = make_conn()
    allowed, reason = positions.can_sell_c_class(conn, "008282", date.today(), False, False)
    assert not allowed
    assert "No local position" in reason


def test_c_class_lot_bought_three_days_ago_blocks_sell():
    conn = make_conn()
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=3), "test")
    allowed, reason = positions.can_sell_c_class(conn, "008282", date.today(), False, False)
    assert not allowed
    assert "blocked" in reason or "拦截" in reason


def test_c_class_young_lot_allows_sell_with_extreme_stop_loss():
    conn = make_conn()
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=3), "test")
    allowed, reason = positions.can_sell_c_class(conn, "008282", date.today(), True, False)
    assert allowed
    assert "extreme_stop_loss" in reason


def test_c_class_young_lot_allows_sell_with_crash_override():
    conn = make_conn()
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=3), "test")
    allowed, reason = positions.can_sell_c_class(conn, "008282", date.today(), False, True)
    assert allowed
    assert "crash_override" in reason


def test_c_class_eight_day_lot_allows_sell():
    conn = make_conn()
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=8), "test")
    allowed, reason = positions.can_sell_c_class(conn, "008282", date.today(), False, False)
    assert allowed
    assert "available shares" in reason


def test_fifo_uses_oldest_buy_date():
    conn = make_conn()
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=8), "old")
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=3), "new")
    lots = positions.fifo_lots(conn, "008282")
    assert lots[0]["buy_date"] < lots[1]["buy_date"]
    assert positions.min_holding_days(conn, "008282", date.today()) == 8


def test_fifo_clearance_only_closes_lots_held_at_least_seven_days():
    conn = make_conn()
    now = datetime.now(timezone.utc)
    lot1 = positions.insert_lot(conn, "008282", 10, 1.0, now - timedelta(days=10))
    lot2 = positions.insert_lot(conn, "008282", 20, 1.0, now - timedelta(days=8))
    lot3 = positions.insert_lot(conn, "008282", 30, 1.0, now - timedelta(days=3))

    evaluation = positions.evaluate_fifo_sell(conn, "008282", 60, now)
    assert evaluation["available_shares"] == 30
    assert evaluation["executable_shares"] == 30
    assert evaluation["blocked_shares"] == 30
    assert evaluation["reason"] == "因 7 天锁定规则，卖出指令被部分截断"

    updates = positions.execute_fifo_sell(conn, "008282", evaluation["executable_shares"], now)
    assert [update["lot_id"] for update in updates] == [lot1, lot2]

    lots = {lot["id"]: lot for lot in conn.execute("SELECT * FROM lots ORDER BY id").fetchall()}
    assert lots[lot1]["status"] == "CLOSED"
    assert lots[lot2]["status"] == "CLOSED"
    assert lots[lot3]["status"] == "OPEN"
    assert lots[lot3]["shares"] == 30


def test_append_and_read_recent_execution_logs():
    conn = make_conn()
    log_id = positions.append_paper_execution_log(
        conn,
        run_id="run-1",
        timestamp=datetime.now(timezone.utc),
        asset_code="008282",
        router_branch="deep",
        raw_signal={"action": "Sell", "shares": 60},
        guard_result={"reason": "因 7 天锁定规则，卖出指令被部分截断"},
        final_action="Sell",
    )
    logs = positions.recent_execution_logs(conn)
    assert logs[0]["id"] == log_id
    assert logs[0]["guard_result"]["reason"] == "因 7 天锁定规则，卖出指令被部分截断"
