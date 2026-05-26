from datetime import date, datetime, timedelta, timezone

from app.config import load_config
from app.graph import build_graph
from app.models import MarketSnapshot
from app import nodes
from app.services import database, positions


def invoke_with_mock_vix(tmp_path, monkeypatch, vix):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")

    def fake_snapshot(_config):
        if vix == "unavailable":
            return MarketSnapshot(as_of="2026-05-06T00:00:00Z", vix=None, source="unavailable")
        return MarketSnapshot(as_of="2026-05-06T00:00:00Z", vix=vix, source="mock")

    monkeypatch.setattr(nodes.market_data, "get_market_snapshot", fake_snapshot)

    def fake_reason(state, _config):
        next_state = dict(state)
        next_state["hermes_raw_json"] = {
            "target_asset": next_state["asset_code"],
            "sentiment_score": 0.0,
            "confidence": 1.0,
            "reasoning": "route test",
        }
        return next_state

    monkeypatch.setattr(nodes, "reason_with_hermes", fake_reason)
    app = build_graph(config)
    return app.invoke({"run_id": "test-run", "asset_code": "000510"})


def test_mock_vix_routes_deep(tmp_path, monkeypatch):
    state = invoke_with_mock_vix(tmp_path, monkeypatch, 18.5)
    assert state["run_id"] == "test-run"
    assert state["router_branch"] == "deep"
    assert state["status"] == "completed"


def test_mock_vix_routes_emergency(tmp_path, monkeypatch):
    state = invoke_with_mock_vix(tmp_path, monkeypatch, 40)
    assert state["router_branch"] == "emergency"
    assert state["parsed_signal"]["action"] == "Hold"


def test_unavailable_vix_routes_sleep(tmp_path, monkeypatch):
    state = invoke_with_mock_vix(tmp_path, monkeypatch, "unavailable")
    assert state["router_branch"] == "sleep"
    assert state["status"] == "slept"


def test_low_confidence_signal_becomes_hold(tmp_path, monkeypatch):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")

    monkeypatch.setattr(
        nodes.market_data,
        "get_market_snapshot",
        lambda _config: MarketSnapshot(as_of="2026-05-06T00:00:00Z", vix=18.5, source="mock"),
    )

    def low_confidence(state, _config):
        next_state = dict(state)
        next_state["hermes_raw_json"] = {
            "target_asset": "008282",
            "sentiment_score": 0.45,
            "confidence": 0.69,
            "reasoning": "below high volatility threshold",
        }
        return next_state

    monkeypatch.setattr(nodes, "reason_with_hermes", low_confidence)
    app = build_graph(config)
    state = app.invoke({"run_id": "run-low-confidence", "asset_code": "008282"})
    assert state["parsed_signal"]["action"] == "Hold"
    assert "below threshold" in state["parsed_signal"]["reason"]


def test_invalid_hermes_json_retries_then_fallback_hold(tmp_path, monkeypatch):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")

    monkeypatch.setattr(
        nodes.market_data,
        "get_market_snapshot",
        lambda _config: MarketSnapshot(as_of="2026-05-06T00:00:00Z", vix=18.5, source="mock"),
    )

    def invalid_json(state, _config):
        next_state = dict(state)
        next_state["hermes_raw_json"] = "not json"
        return next_state

    monkeypatch.setattr(nodes, "reason_with_hermes", invalid_json)
    app = build_graph(config)
    state = app.invoke({"run_id": "run-invalid", "asset_code": "000510"})
    assert state["retry_count"] == 2
    assert state["parsed_signal"]["action"] == "Hold"
    assert "Invalid Hermes JSON" in state["parsed_signal"]["reason"]


def test_hermes_sentiment_schema_maps_to_internal_signal(tmp_path, monkeypatch):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")

    monkeypatch.setattr(
        nodes.market_data,
        "get_market_snapshot",
        lambda _config: MarketSnapshot(as_of="2026-05-06T00:00:00Z", vix=18.5, source="mock"),
    )

    def hermes_schema(state, _config):
        next_state = dict(state)
        next_state["hermes_raw_json"] = {
            "target_asset": "000510",
            "sentiment_score": 0.45,
            "confidence": 0.88,
            "reasoning": "positive market context",
        }
        return next_state

    monkeypatch.setattr(nodes, "reason_with_hermes", hermes_schema)
    app = build_graph(config)
    state = app.invoke({"run_id": "run-hermes-schema", "asset_code": "000510"})

    assert state["parsed_signal"]["asset_code"] == "000510"
    assert state["parsed_signal"]["action"] == "Buy"
    assert state["parsed_signal"]["confidence"] == 0.88
    assert state["parsed_signal"]["reason"] == "positive market context"


def test_hermes_rejects_executable_fields_and_never_uses_llm_override(tmp_path, monkeypatch):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")
    conn = database.connect(config.app.database_path)
    database.init_db(conn)
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=3), "test")
    conn.close()

    monkeypatch.setattr(
        nodes.market_data,
        "get_market_snapshot",
        lambda _config: MarketSnapshot(as_of="2026-05-06T00:00:00Z", vix=18.5, source="mock"),
    )

    def unsafe_hermes(state, _config):
        next_state = dict(state)
        next_state["hermes_raw_json"] = {
            "target_asset": "008282",
            "sentiment_score": -0.45,
            "confidence": 0.95,
            "reasoning": "unsafe executable field attempt",
            "crash_override": True,
        }
        return next_state

    monkeypatch.setattr(nodes, "reason_with_hermes", unsafe_hermes)
    app = build_graph(config)
    state = app.invoke({"run_id": "run-unsafe-hermes", "asset_code": "008282"})

    assert state["retry_count"] == 2
    assert state["parsed_signal"] == {
        "asset_code": "008282",
        "action": "Hold",
        "confidence": 0.0,
        "reason": "Invalid Hermes JSON after retries; fallback Hold.",
        "shares": 1.0,
        "cost_price": 1.0,
        "extreme_stop_loss": False,
        "crash_override": False,
    }
    assert state["guard_result"]["final_action"] == "Hold"


def test_validate_llm_json_clears_stale_parsed_signal(tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    state = {
        "run_id": "run-stale-signal",
        "asset_code": "008282",
        "retry_count": 0,
        "hermes_raw_json": "not json",
        "parsed_signal": {
            "asset_code": "008282",
            "action": "Sell",
            "confidence": 1.0,
            "reason": "stale signal must be cleared",
            "shares": 1.0,
            "cost_price": 1.0,
            "extreme_stop_loss": False,
            "crash_override": True,
        },
    }

    next_state = nodes.validate_llm_json(state, config)

    assert "parsed_signal" not in next_state
    assert nodes.route_after_validation(next_state) == "retry"


    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    conn = database.connect(config.app.database_path)
    database.init_db(conn)
    positions.insert_position(conn, "008282", "C", 1.0, date.today() - timedelta(days=3), "test")
    conn.close()

    state = {
        "run_id": "run-guard",
        "asset_code": "008282",
        "parsed_signal": {
            "asset_code": "008282",
            "action": "Sell",
            "confidence": 0.9,
            "reason": "test sell",
            "shares": 1.0,
            "extreme_stop_loss": False,
            "crash_override": False,
        },
    }
    guarded = nodes.position_policy_guard(state, config)
    assert guarded["guard_result"]["final_action"] == "Hold"

    state["parsed_signal"]["crash_override"] = True
    guarded = nodes.position_policy_guard(state, config)
    assert guarded["guard_result"]["final_action"] == "Sell"


def test_graph_blocks_locked_c_class_lot_and_logs(tmp_path, monkeypatch):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")
    now = datetime.now(timezone.utc)
    conn = database.connect(config.app.database_path)
    database.init_db(conn)
    positions.insert_lot(conn, "008282", 10, 1.0, now - timedelta(days=10))
    positions.insert_lot(conn, "008282", 20, 1.0, now - timedelta(days=8))
    young_lot = positions.insert_lot(conn, "008282", 30, 1.0, now - timedelta(days=3))
    conn.close()

    monkeypatch.setattr(
        nodes.market_data,
        "get_market_snapshot",
        lambda _config: MarketSnapshot(as_of="2026-05-06T00:00:00Z", vix=18.5, source="mock"),
    )

    def sell_all(state, _config):
        next_state = dict(state)
        next_state["hermes_raw_json"] = {
            "target_asset": "008282",
            "sentiment_score": -0.45,
            "confidence": 0.95,
            "reasoning": "clear position",
        }
        return next_state

    monkeypatch.setattr(nodes, "reason_with_hermes", sell_all)
    app = build_graph(config)
    state = app.invoke({"run_id": "run-partial", "asset_code": "008282"})

    assert state["guard_result"]["partial"] is False
    assert state["guard_result"]["executable_shares"] == 1
    assert state["guard_result"]["blocked_shares"] == 0
    assert state["guard_result"]["reason"] == "FIFO sell allowed"

    conn = database.connect(config.app.database_path)
    database.init_db(conn)
    lots = {lot["id"]: lot for lot in conn.execute("SELECT * FROM lots ORDER BY id").fetchall()}
    logs = positions.recent_execution_logs(conn)
    conn.close()

    oldest_lot = min(lots.values(), key=lambda lot: lot["id"])
    closed_lots = [lot for lot in lots.values() if lot["status"] == "CLOSED"]
    assert oldest_lot["shares"] == 9
    assert len(closed_lots) == 0
    assert lots[young_lot]["status"] == "OPEN"
    assert lots[young_lot]["shares"] == 30
    assert logs[0]["run_id"] == "run-partial"
    assert logs[0]["guard_result"]["reason"] == "FIFO sell allowed"
    assert logs[0]["final_action"] == "Sell"
