from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.config import Config, LLMConfig, OllamaConfig
from app.services import database

LLM_BASE_URL_KEY = "llm.base_url"
LLM_GENERATE_PATH_KEY = "llm.generate_path"
LLM_MODEL_KEY = "llm.model"
LLM_TIMEOUT_SECONDS_KEY = "llm.timeout_seconds"
LLM_API_KEY = "llm.api_key"

_runtime_api_keys: dict[str, str] = {}
_runtime_api_keys_lock = Lock()


@dataclass(slots=True)
class LLMSettingsUpdate:
    base_url: str | None = None
    generate_path: str | None = None
    model: str | None = None
    timeout_seconds: float | None = None
    api_key: str | None = None
    api_key_was_provided: bool = False
    persist_api_key: bool = False


def _runtime_key(config: Config) -> str:
    return str(Path(config.app.database_path).resolve())


def _persisted_settings(config: Config) -> dict[str, str]:
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        return database.get_app_settings(
            conn,
            [
                LLM_BASE_URL_KEY,
                LLM_GENERATE_PATH_KEY,
                LLM_MODEL_KEY,
                LLM_TIMEOUT_SECONDS_KEY,
                LLM_API_KEY,
            ],
        )
    finally:
        conn.close()


def get_effective_llm_config(config: Config) -> LLMConfig:
    persisted = _persisted_settings(config)
    runtime_key = _runtime_key(config)

    data = config.llm.model_dump()
    if LLM_BASE_URL_KEY in persisted:
        data["base_url"] = persisted[LLM_BASE_URL_KEY]
    if LLM_GENERATE_PATH_KEY in persisted:
        data["generate_path"] = persisted[LLM_GENERATE_PATH_KEY]
    if LLM_MODEL_KEY in persisted:
        data["model"] = persisted[LLM_MODEL_KEY]
    if LLM_TIMEOUT_SECONDS_KEY in persisted:
        data["timeout_seconds"] = float(persisted[LLM_TIMEOUT_SECONDS_KEY])

    with _runtime_api_keys_lock:
        runtime_api_key = _runtime_api_keys.get(runtime_key)
    if runtime_api_key is not None:
        data["api_key"] = runtime_api_key
    elif LLM_API_KEY in persisted:
        data["api_key"] = persisted[LLM_API_KEY]

    return LLMConfig.model_validate(data)


def get_effective_ollama_config(config: Config) -> OllamaConfig:
    return OllamaConfig.model_validate(get_effective_llm_config(config).model_dump())


def get_llm_settings_view(config: Config) -> dict[str, str | float | bool]:
    effective = get_effective_llm_config(config)
    return {
        "base_url": effective.base_url,
        "generate_path": effective.generate_path,
        "model": effective.model,
        "timeout_seconds": effective.timeout_seconds,
        "has_api_key": effective.api_key is not None,
    }


def update_llm_settings(config: Config, update: LLMSettingsUpdate) -> dict[str, str | float | bool]:
    current = get_effective_llm_config(config)
    merged = current.model_copy(
        update={
            key: value
            for key, value in {
                "base_url": update.base_url,
                "generate_path": update.generate_path,
                "model": update.model,
                "timeout_seconds": update.timeout_seconds,
            }.items()
            if value is not None
        }
    )

    timestamp = current_timestamp()
    conn = database.connect(config.app.database_path)
    runtime_key = _runtime_key(config)
    try:
        database.init_db(conn)
        conn.execute("BEGIN")
        database.set_app_setting(conn, LLM_BASE_URL_KEY, merged.base_url, updated_at=timestamp, commit=False)
        database.set_app_setting(conn, LLM_GENERATE_PATH_KEY, merged.generate_path, updated_at=timestamp, commit=False)
        database.set_app_setting(conn, LLM_MODEL_KEY, merged.model, updated_at=timestamp, commit=False)
        database.set_app_setting(
            conn,
            LLM_TIMEOUT_SECONDS_KEY,
            str(merged.timeout_seconds),
            updated_at=timestamp,
            commit=False,
        )

        if update.api_key_was_provided:
            if update.api_key:
                if update.persist_api_key:
                    database.set_app_setting(conn, LLM_API_KEY, update.api_key, updated_at=timestamp, commit=False)
                    with _runtime_api_keys_lock:
                        _runtime_api_keys.pop(runtime_key, None)
                else:
                    database.delete_app_setting(conn, LLM_API_KEY, commit=False)
                    with _runtime_api_keys_lock:
                        _runtime_api_keys[runtime_key] = update.api_key
            else:
                database.delete_app_setting(conn, LLM_API_KEY, commit=False)
                with _runtime_api_keys_lock:
                    _runtime_api_keys.pop(runtime_key, None)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_llm_settings_view(config)


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
