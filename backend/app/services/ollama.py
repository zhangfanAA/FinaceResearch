from __future__ import annotations

from app.services import cloud_llm

OllamaGenerateError = cloud_llm.CloudLLMError
parse_json_object = cloud_llm.parse_json_object


def generate_with_ollama(*args, **kwargs):
    return cloud_llm.generate_with_cloud_llm(*args, **kwargs)


def test_ollama_connection(*args, **kwargs):
    return cloud_llm.test_cloud_llm_connection(*args, **kwargs)
