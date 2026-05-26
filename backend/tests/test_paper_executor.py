from pathlib import Path

import requests

from app.config import load_config
from app.models import GuardResult, ParsedSignal
from app.services.paper_executor import execute_paper


def test_execute_paper_writes_jsonl(tmp_path: Path):
    config = load_config("config.yaml")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")
    signal = ParsedSignal(asset_code="000510", action="Hold", confidence=0.8, reason="test")
    guard = GuardResult(allowed=True, final_action="Hold", reason="hold")

    execution = execute_paper(config, signal, guard, run_id="run-1", router_branch="deep")

    log_path = Path(config.app.paper_log_path)
    assert log_path.exists()
    assert execution.paper_only is True
    assert execution.run_id == "run-1"
    assert "Hold" in log_path.read_text(encoding="utf-8")


def test_hold_writes_log_entry(tmp_path: Path):
    config = load_config("config.yaml")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")
    signal = ParsedSignal(asset_code="000510", action="Hold", confidence=0.8, reason="test")
    guard = GuardResult(allowed=True, final_action="Hold", reason="hold")

    execute_paper(config, signal, guard, run_id="run-1", router_branch="deep")

    assert len(Path(config.app.paper_log_path).read_text(encoding="utf-8").splitlines()) == 1


def test_webhook_exception_is_suppressed(tmp_path: Path, monkeypatch):
    config = load_config("config.yaml")
    config.app.paper_log_path = str(tmp_path / "paper.jsonl")
    config.webhook.enabled = True
    config.webhook.url = "http://example.invalid/webhook"

    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("boom")

    monkeypatch.setattr(requests, "post", raise_timeout)
    signal = ParsedSignal(asset_code="000510", action="Hold", confidence=0.8, reason="test")
    guard = GuardResult(allowed=True, final_action="Hold", reason="hold")

    execution = execute_paper(config, signal, guard, run_id="run-1", router_branch="deep")

    assert execution.paper_only is True
