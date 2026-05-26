from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.config import load_config
from app.services import cloud_llm
from app.services.llm_settings import LLMSettingsUpdate, update_llm_settings


class FakeClient:
    def __init__(self, create_fn):
        self.responses = SimpleNamespace(create=create_fn)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create_fn))
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_parse_json_object_returns_dict():
    assert cloud_llm.parse_json_object('{"confidence": 0.8}') == {"confidence": 0.8}


def test_parse_json_object_strips_markdown_fences():
    assert cloud_llm.parse_json_object("```json\n{\"confidence\": 0.8}\n```") == {"confidence": 0.8}


def test_parse_json_object_rejects_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        cloud_llm.parse_json_object("not json")


def test_parse_json_object_rejects_non_object_json():
    with pytest.raises(ValueError, match="not an object"):
        cloud_llm.parse_json_object("[]")


def test_generate_with_cloud_llm_uses_dynamic_settings_and_tools(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    update_llm_settings(
        config,
        LLMSettingsUpdate(
            base_url="https://api.example.com",
            generate_path="/v1",
            model="runtime-model",
            timeout_seconds=12.5,
            api_key="secret-token",
            api_key_was_provided=True,
            persist_api_key=False,
        ),
    )
    seen = {}

    def fake_build_client(llm_config):
        seen["base_url"] = llm_config.base_url
        seen["generate_path"] = llm_config.generate_path
        seen["model"] = llm_config.model
        seen["timeout_seconds"] = llm_config.timeout_seconds
        seen["api_key"] = llm_config.api_key

        async def create(**kwargs):
            seen["request_kwargs"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

        return FakeClient(create)

    monkeypatch.setattr(cloud_llm, "_build_client", fake_build_client)

    result = asyncio.run(cloud_llm.generate_with_cloud_llm(config, "prompt"))

    assert result == '{"ok": true}'
    assert seen["base_url"] == "https://api.example.com"
    assert seen["generate_path"] == "/v1"
    assert seen["model"] == "runtime-model"
    assert seen["timeout_seconds"] == 12.5
    assert seen["api_key"] == "secret-token"
    assert seen["request_kwargs"] == {
        "model": "runtime-model",
        "messages": [{"role": "user", "content": "prompt"}],
        "temperature": 0.0,
    }


def test_generate_with_cloud_llm_retries_without_tools_on_compatibility_error(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    update_llm_settings(
        config,
        LLMSettingsUpdate(
            api_key="test-key",
            api_key_was_provided=True,
            persist_api_key=False,
        ),
    )
    calls = []

    def fake_build_client(_llm_config):
        async def create(**kwargs):
            calls.append(kwargs)
            if "tools" in kwargs:
                raise httpx.HTTPStatusError(
                    "Unsupported tools parameter",
                    request=httpx.Request("POST", "https://api.example.com/v1/responses"),
                    response=httpx.Response(400),
                )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

        return FakeClient(create)

    monkeypatch.setattr(cloud_llm, "_build_client", fake_build_client)

    result = asyncio.run(cloud_llm.generate_with_cloud_llm(config, "prompt"))

    assert result == '{"ok": true}'


def test_generate_with_cloud_llm_raises_cleanly_on_http_error(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    update_llm_settings(
        config,
        LLMSettingsUpdate(
            api_key="test-key",
            api_key_was_provided=True,
            persist_api_key=False,
        ),
    )

    def fake_build_client(_llm_config):
        async def create(**kwargs):
            raise httpx.HTTPStatusError(
                "Bad gateway",
                request=httpx.Request("POST", "https://api.example.com/v1/responses"),
                response=httpx.Response(502),
            )

        return FakeClient(create)

    monkeypatch.setattr(cloud_llm, "_build_client", fake_build_client)

    with pytest.raises(cloud_llm.CloudLLMError, match="request failed"):
        asyncio.run(cloud_llm.generate_with_cloud_llm(config, "prompt", allow_web_search_tools=False))


def test_generate_with_cloud_llm_rejects_empty_response(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    update_llm_settings(
        config,
        LLMSettingsUpdate(
            api_key="test-key",
            api_key_was_provided=True,
            persist_api_key=False,
        ),
    )

    def fake_build_client(_llm_config):
        async def create(**kwargs):
            return SimpleNamespace(output_text="   ", output=[], choices=[])

        return FakeClient(create)

    monkeypatch.setattr(cloud_llm, "_build_client", fake_build_client)

    with pytest.raises(cloud_llm.CloudLLMError, match="non-empty response text"):
        asyncio.run(cloud_llm.generate_with_cloud_llm(config, "prompt", allow_web_search_tools=False))


def test_test_cloud_llm_connection_only_checks_connectivity(monkeypatch, tmp_path):
    config = load_config("config.yaml")
    config.app.database_path = str(tmp_path / "test.sqlite")
    update_llm_settings(
        config,
        LLMSettingsUpdate(
            api_key="test-key",
            api_key_was_provided=True,
            persist_api_key=False,
        ),
    )
    seen = {}

    def fake_build_client(_llm_config):
        async def create(**kwargs):
            seen["kwargs"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

        return FakeClient(create)

    monkeypatch.setattr(cloud_llm, "_build_client", fake_build_client)

    asyncio.run(cloud_llm.test_cloud_llm_connection(config))

    assert seen["kwargs"] == {
        "model": config.llm.model,
        "messages": [{"role": "user", "content": "Return a minimal JSON object."}],
        "temperature": 0.0,
    }
