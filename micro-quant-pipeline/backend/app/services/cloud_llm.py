from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import Config, LLMConfig
from app.services.llm_settings import get_effective_llm_config

logger = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 0.0
DEFAULT_TEST_PROMPT = "Return a minimal JSON object."
WEB_SEARCH_TOOL = {"type": "web_search", "web_search": {"enable": True}}
TOOL_ERROR_MARKERS = (
    "tool",
    "tools",
    "web_search",
    "unsupported",
    "unknown parameter",
    "extra_forbidden",
)


class CloudLLMError(RuntimeError):
    pass


class CloudLLMToolCompatibilityError(CloudLLMError):
    pass


class CloudLLMInvalidJSONError(CloudLLMError):
    pass


class CloudLLMNoAPIKeyError(CloudLLMError):
    """Raised when no API key is configured for the LLM."""
    pass


def _build_base_url(llm_config: LLMConfig) -> str:
    base_url = llm_config.base_url.rstrip("/")
    generate_path = llm_config.generate_path.strip()
    if not generate_path:
        return base_url
    return f"{base_url}{generate_path}"


def _build_client(llm_config: LLMConfig) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=llm_config.api_key or "sk-placeholder",
        base_url=_build_base_url(llm_config),
        timeout=llm_config.timeout_seconds,
    )


def _extract_text(response: Any) -> str:
    # Try Chat Completions format first (choices[0].message.content)
    choices = getattr(response, "choices", None)
    if choices and len(choices) > 0:
        message = getattr(choices[0], "message", None)
        if message:
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()

    # Try Responses API format (output_text)
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = getattr(response, "output", None)
    if isinstance(output, list):
        collected: list[str] = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) in {"output_text", "text"}:
                    text = getattr(content, "text", None)
                    if isinstance(text, str) and text.strip():
                        collected.append(text.strip())
        if collected:
            return "\n".join(collected)

    raise CloudLLMError("Cloud LLM response did not contain non-empty response text")


def strip_markdown_code_fences(raw_text: str) -> str:
    stripped = raw_text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines:
        return stripped
    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = strip_markdown_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("Hermes output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Hermes output JSON is not an object")
    return parsed


def _is_tool_compatibility_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in TOOL_ERROR_MARKERS)


async def _chat_completions_create(
    llm_config: LLMConfig,
    prompt: str,
    *,
    allow_web_search_tools: bool,
) -> str:
    """Use Chat Completions API (compatible with MIMO and most OpenAI-compatible APIs)."""
    if not llm_config.api_key:
        raise CloudLLMNoAPIKeyError(
            "LLM API key not configured. Please set it via the Settings page or config.yaml."
        )

    client = _build_client(llm_config)
    messages = [{"role": "user", "content": prompt}]
    request_kwargs: dict[str, Any] = {
        "model": llm_config.model,
        "messages": messages,
        "temperature": DEFAULT_TEMPERATURE,
    }

    try:
        response = await client.chat.completions.create(**request_kwargs)
    except CloudLLMNoAPIKeyError:
        raise
    except Exception as exc:
        if isinstance(exc, httpx.HTTPError):
            raise CloudLLMError(f"Cloud LLM request failed: {exc}") from exc
        raise CloudLLMError(f"Cloud LLM request failed: {exc}") from exc
    finally:
        await client.close()

    return _extract_text(response)


async def _responses_create(
    llm_config: LLMConfig,
    prompt: str,
    *,
    allow_web_search_tools: bool,
) -> str:
    """Use Responses API (OpenAI native). Falls back to Chat Completions on failure."""
    if not llm_config.api_key:
        raise CloudLLMNoAPIKeyError(
            "LLM API key not configured. Please set it via the Settings page or config.yaml."
        )

    client = _build_client(llm_config)
    request_kwargs: dict[str, Any] = {
        "model": llm_config.model,
        "input": prompt,
        "temperature": DEFAULT_TEMPERATURE,
    }
    if allow_web_search_tools:
        request_kwargs["tools"] = [WEB_SEARCH_TOOL]

    try:
        response = await client.responses.create(**request_kwargs)
    except CloudLLMNoAPIKeyError:
        raise
    except Exception as exc:
        if allow_web_search_tools and _is_tool_compatibility_error(exc):
            raise CloudLLMToolCompatibilityError(str(exc)) from exc
        if isinstance(exc, httpx.HTTPError):
            raise CloudLLMError(f"Cloud LLM request failed: {exc}") from exc
        raise CloudLLMError(f"Cloud LLM request failed: {exc}") from exc
    finally:
        await client.close()

    return _extract_text(response)


async def generate_with_cloud_llm(
    config: Config,
    prompt: str,
    *,
    allow_web_search_tools: bool = True,
) -> str:
    """Generate text using the configured LLM.

    Strategy:
    1. Try Chat Completions API (works with MIMO and most providers)
    2. If that fails with tool compatibility error, try without tools
    3. If that also fails, try Responses API as last resort
    """
    llm_config = get_effective_llm_config(config)

    # Primary: Chat Completions API (most compatible)
    try:
        return await _chat_completions_create(
            llm_config,
            prompt,
            allow_web_search_tools=allow_web_search_tools,
        )
    except CloudLLMNoAPIKeyError:
        raise
    except CloudLLMToolCompatibilityError:
        # Retry without tools
        try:
            return await _chat_completions_create(
                llm_config,
                prompt,
                allow_web_search_tools=False,
            )
        except CloudLLMNoAPIKeyError:
            raise
        except Exception:
            pass  # Fall through to Responses API
    except Exception as exc:
        logger.debug("Chat Completions API failed: %s, trying Responses API", exc)

    # Fallback: Responses API
    try:
        return await _responses_create(
            llm_config,
            prompt,
            allow_web_search_tools=allow_web_search_tools,
        )
    except CloudLLMToolCompatibilityError:
        return await _responses_create(
            llm_config,
            prompt,
            allow_web_search_tools=False,
        )


async def test_cloud_llm_connection(config: Config) -> None:
    llm_config = get_effective_llm_config(config)
    try:
        await _chat_completions_create(
            llm_config,
            DEFAULT_TEST_PROMPT,
            allow_web_search_tools=False,
        )
    except CloudLLMNoAPIKeyError:
        raise
    except Exception as exc:
        raise CloudLLMError(f"Cloud LLM connectivity test failed: {exc}") from exc
