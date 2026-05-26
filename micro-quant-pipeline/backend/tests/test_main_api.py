from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import load_config
from app.main import app, get_config
from app.services import database, positions


@pytest.fixture
def temp_config(tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "api.sqlite")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")
    return config


@pytest.fixture
def client(temp_config) -> Iterator[TestClient]:
    app.dependency_overrides[get_config] = lambda: temp_config
    main.LAST_STATE = None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    main.LAST_STATE = None


def test_health_remains_available(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "paper"}


def test_dashboard_route_is_not_served(client):
    response = client.get("/dashboard")

    assert response.status_code == 404


def test_cors_allows_only_frontend_origins(client):
    allowed = client.options(
        "/api/status",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked = client.options(
        "/api/status",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert blocked.status_code == 400


def test_api_lots_returns_open_lots_with_holding_days(client, temp_config):
    now = datetime.now(timezone.utc)
    conn = database.connect(temp_config.app.database_path)
    try:
        database.init_db(conn)
        open_lot_id = positions.insert_lot(conn, "008282", 12.5, 1.23, now - timedelta(days=8))
        closed_lot_id = positions.insert_lot(conn, "008282", 3.0, 1.11, now - timedelta(days=10))
        conn.execute("UPDATE lots SET status = 'CLOSED' WHERE id = ?", (closed_lot_id,))
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/lots")

    assert response.status_code == 200
    lots = response.json()
    assert len(lots) == 1
    assert lots[0]["id"] == open_lot_id
    assert lots[0]["asset_code"] == "008282"
    assert lots[0]["status"] == "OPEN"
    assert lots[0]["holding_days"] >= 8
    assert lots[0]["pnl_ratio"] == -0.1057


def test_api_logs_returns_recent_logs_in_reverse_chronological_order(client, temp_config):
    conn = database.connect(temp_config.app.database_path)
    try:
        database.init_db(conn)
        positions.append_paper_execution_log(
            conn,
            run_id="older-run",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
            asset_code="000510",
            router_branch="sleep",
            raw_signal={"action": "Hold"},
            guard_result={"final_action": "Hold"},
            final_action="Hold",
        )
        positions.append_paper_execution_log(
            conn,
            run_id="newer-run",
            timestamp=datetime.now(timezone.utc),
            asset_code="008282",
            router_branch="deep",
            raw_signal={"action": "Sell", "shares": 1},
            guard_result={"final_action": "Hold"},
            final_action="Hold",
        )
    finally:
        conn.close()

    response = client.get("/api/logs?limit=1")

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["run_id"] == "newer-run"
    assert logs[0]["raw_signal"]["action"] == "Sell"


def test_api_status_reports_components_without_external_service_dependencies(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["backend"]["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["langgraph"]["status"] == "configured"
    assert body["chromadb"]["status"] in {"unknown", "configured", "degraded"}
    assert body["ollama"]["status"] in {"unknown", "configured", "degraded"}


def test_api_llm_settings_get_and_put_stay_frontend_compatible(client):
    get_response = client.get("/api/settings/llm")

    assert get_response.status_code == 200
    assert get_response.json()["model"] == "mimo-v2.5-pro"
    assert get_response.json()["has_api_key"] is False

    put_response = client.put(
        "/api/settings/llm",
        json={
            "base_url": "https://api.example.com",
            "generate_path": "/v1",
            "model": "custom-model",
            "timeout_seconds": 12.5,
            "api_key": "secret-token",
            "persist_api_key": False,
        },
    )

    assert put_response.status_code == 200
    assert put_response.json() == {
        "base_url": "https://api.example.com",
        "generate_path": "/v1",
        "model": "custom-model",
        "timeout_seconds": 12.5,
        "has_api_key": True,
    }


def test_api_llm_connectivity_test_uses_cloud_client(client, monkeypatch):
    seen = {}

    async def fake_test_cloud_llm_connection(config):
        seen["model"] = config.llm.model

    monkeypatch.setattr(main, "test_cloud_llm_connection", fake_test_cloud_llm_connection)

    response = client.post("/api/settings/llm/test")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "detail": "LLM connectivity test succeeded",
    }
    assert seen["model"] == "mimo-v2.5-pro"


def test_api_research_analyze_uses_web_search_and_stays_read_only(client, temp_config, monkeypatch):
    conn = database.connect(temp_config.app.database_path)
    try:
        database.init_db(conn)
        initial_logs = len(positions.recent_execution_logs(conn, limit=100))
        initial_lots = len(positions.list_open_lots(conn))
    finally:
        conn.close()

    seen = {}

    async def fake_analyze_fund_research(config, prompt):
        seen["model"] = config.llm.model
        seen["prompt"] = prompt
        return "research result"

    monkeypatch.setattr(main, "analyze_fund_research", fake_analyze_fund_research)

    response = client.post(
        "/api/research/analyze",
        json={"prompt": "Analyze semiconductor C-class funds with web search."},
    )

    assert response.status_code == 200
    assert response.json() == {"output": "research result"}
    assert seen == {
        "model": "mimo-v2.5-pro",
        "prompt": "Analyze semiconductor C-class funds with web search.",
    }

    conn = database.connect(temp_config.app.database_path)
    try:
        database.init_db(conn)
        final_logs = len(positions.recent_execution_logs(conn, limit=100))
        final_lots = len(positions.list_open_lots(conn))
    finally:
        conn.close()

    assert final_logs == initial_logs
    assert final_lots == initial_lots


def test_api_research_analyze_rejects_empty_prompt(client):
    response = client.post("/api/research/analyze", json={"prompt": ""})

    assert response.status_code == 422


def test_api_research_analyze_surfaces_cloud_errors(client, monkeypatch):
    async def fake_analyze_fund_research(config, prompt):
        raise main.CloudLLMError("upstream failed")

    monkeypatch.setattr(main, "analyze_fund_research", fake_analyze_fund_research)

    response = client.post("/api/research/analyze", json={"prompt": "test prompt"})

    assert response.status_code == 502
    assert response.json()["detail"] == "upstream failed"


def test_api_trigger_generates_run_id_and_returns_final_state(client, monkeypatch):
    captured = {}

    def fake_run_once(asset_code=None, config_path="config.yaml", run_id=None):
        captured["asset_code"] = asset_code
        captured["config_path"] = config_path
        captured["run_id"] = run_id
        return {
            "run_id": run_id,
            "asset_code": asset_code,
            "status": "completed",
            "router_branch": "deep",
            "guard_result": {"final_action": "Hold"},
        }

    monkeypatch.setattr(main, "run_once", fake_run_once)

    response = client.post("/api/trigger", json={"asset_code": "008282"})

    assert response.status_code == 202
    body = response.json()
    assert body["run_id"] == captured["run_id"]
    assert captured["asset_code"] == "008282"
    assert body["state"]["status"] == "completed"
    assert body["state"]["guard_result"]["final_action"] == "Hold"


def test_api_analysis_history_returns_logs(client, temp_config):
    conn = database.connect(temp_config.app.database_path)
    try:
        database.init_db(conn)
        conn.execute(
            """
            INSERT INTO analysis_logs (analysis_type, target_code, target_name, llm_prompt, llm_raw_output, parsed_result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("stock_sector", "半导体", "半导体", "prompt text", '{"trend":"bullish"}', '{"trend":"bullish"}', "2026-05-25T10:00:00"),
        )
        conn.execute(
            """
            INSERT INTO analysis_logs (analysis_type, target_code, target_name, llm_prompt, llm_raw_output, parsed_result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("fund_sector", "000510", "某基金", "prompt text", '{"judgment":"positive"}', '{"judgment":"positive"}', "2026-05-25T11:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/analysis/history")

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 2
    assert logs[0]["analysis_type"] == "fund_sector"
    assert logs[0]["target_code"] == "000510"
    assert logs[1]["analysis_type"] == "stock_sector"


def test_api_analysis_history_filters_by_type(client, temp_config):
    conn = database.connect(temp_config.app.database_path)
    try:
        database.init_db(conn)
        conn.execute(
            """
            INSERT INTO analysis_logs (analysis_type, target_code, target_name, llm_prompt, llm_raw_output, parsed_result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("stock_sector", "半导体", "半导体", "p", "raw", "parsed", "2026-05-25T10:00:00"),
        )
        conn.execute(
            """
            INSERT INTO analysis_logs (analysis_type, target_code, target_name, llm_prompt, llm_raw_output, parsed_result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("fund_sector", "000510", "某基金", "p", "raw", "parsed", "2026-05-25T11:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/analysis/history?type=stock_sector")

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["analysis_type"] == "stock_sector"


def test_api_analysis_history_respects_limit(client, temp_config):
    conn = database.connect(temp_config.app.database_path)
    try:
        database.init_db(conn)
        for i in range(5):
            conn.execute(
                """
                INSERT INTO analysis_logs (analysis_type, target_code, target_name, llm_prompt, llm_raw_output, parsed_result, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("stock_sector", f"CODE{i}", f"Name{i}", "p", "raw", "parsed", f"2026-05-25T1{i}:00:00"),
            )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/analysis/history?limit=2")

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 2


def test_api_analysis_history_empty_when_no_logs(client):
    response = client.get("/api/analysis/history")

    assert response.status_code == 200
    assert response.json() == []
