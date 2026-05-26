from __future__ import annotations

import pytest

from app.config import load_config
from app.services import cloud_llm, ollama


@pytest.mark.anyio
async def test_generate_with_ollama_delegates_to_cloud_llm(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    seen = {}

    async def fake_generate_with_cloud_llm(config, prompt, *, allow_web_search_tools=True):
        seen["model"] = config.llm.model
        seen["prompt"] = prompt
        seen["allow_web_search_tools"] = allow_web_search_tools
        return "delegated"

    monkeypatch.setattr(cloud_llm, "generate_with_cloud_llm", fake_generate_with_cloud_llm)

    result = await ollama.generate_with_ollama(config, "prompt")

    assert result == "delegated"
    assert seen == {
        "model": "mimo-v2.5-pro",
        "prompt": "prompt",
        "allow_web_search_tools": True,
    }


@pytest.mark.anyio
async def test_test_ollama_connection_delegates_to_cloud_llm(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    seen = {}

    async def fake_test_cloud_llm_connection(config):
        seen["model"] = config.llm.model

    monkeypatch.setattr(cloud_llm, "test_cloud_llm_connection", fake_test_cloud_llm_connection)

    await ollama.test_ollama_connection(config)

    assert seen == {"model": "mimo-v2.5-pro"}


def test_parse_json_object_still_uses_cloud_parser():
    assert ollama.parse_json_object("```json\n{\"ok\": true}\n```") == {"ok": True}
