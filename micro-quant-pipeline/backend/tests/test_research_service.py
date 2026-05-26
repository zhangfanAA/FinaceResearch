from __future__ import annotations

import pytest

from app.config import load_config
from app.services import research_service


@pytest.mark.anyio
async def test_analyze_fund_research_enables_web_search(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    seen = {}

    async def fake_generate_with_cloud_llm(config, prompt, *, allow_web_search_tools):
        seen["model"] = config.llm.model
        seen["prompt"] = prompt
        seen["allow_web_search_tools"] = allow_web_search_tools
        return "ok"

    monkeypatch.setattr(research_service, "generate_with_cloud_llm", fake_generate_with_cloud_llm)

    result = await research_service.analyze_fund_research(config, "research prompt")

    assert result == "ok"
    assert seen == {
        "model": "mimo-v2.5-pro",
        "prompt": "research prompt",
        "allow_web_search_tools": True,
    }
