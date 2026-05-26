from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class AppConfig(BaseModel):
    name: str = "micro-quant-pipeline"
    mode: Literal["paper"]
    database_path: str = "data/finance_agent.sqlite"
    paper_log_path: str = "data/paper_executions.jsonl"


class MarketConfig(BaseModel):
    vix_symbol: str = "^VIX"
    allow_mock_vix: bool = True
    mock_vix_value: float = 18.5


class LLMConfig(BaseModel):
    base_url: str = Field(default="https://open.bigmodel.cn", min_length=1, max_length=500)
    generate_path: str = Field(default="/api/paas/v4", min_length=1, max_length=255)
    model: str = Field(default="glm-4-flash", min_length=1, max_length=200)
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    api_key: str | None = Field(default=None, repr=False)

    @field_validator("base_url", "generate_path", "model", mode="before")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("LLM settings fields must be strings")
        stripped = value.strip()
        if not stripped:
            raise ValueError("LLM settings fields must not be blank")
        return stripped

    @field_validator("api_key", mode="before")
    @classmethod
    def strip_optional_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("api_key must be a string")
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_generate_path(self) -> "LLMConfig":
        if not self.generate_path.startswith("/"):
            raise ValueError("ollama.generate_path must start with '/'")
        return self


OllamaConfig = LLMConfig


class WebhookConfig(BaseModel):
    enabled: bool = False
    type: str | None = None
    url: str | None = None
    timeout_seconds: int = 3


class AssetConfig(BaseModel):
    name: str
    category: str
    fund_class: str = "A"


class ConfidenceThresholds(BaseModel):
    default: float = 0.65
    broad_index: float = 0.60
    high_volatility: float = 0.70


class AkShareConfig(BaseModel):
    enabled: bool = True
    stock_cache_ttl_seconds: int = 60
    sector_cache_ttl_seconds: int = 60
    fund_cache_ttl_seconds: int = 300
    request_timeout_seconds: int = 15


class ProxyConfig(BaseModel):
    http: str = ""
    https: str = ""


class FallbackConfig(BaseModel):
    max_retries: int = 1
    timeout_seconds: int = 10


class DataSourceConfig(BaseModel):
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)
    akshare: AkShareConfig = Field(default_factory=AkShareConfig)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: AppConfig
    market: MarketConfig = Field(default_factory=MarketConfig)
    ollama: LLMConfig = Field(default_factory=LLMConfig)
    confidence_thresholds: ConfidenceThresholds = Field(default_factory=ConfidenceThresholds)
    assets: dict[str, AssetConfig] = Field(default_factory=dict)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    data_sources: DataSourceConfig = Field(default_factory=DataSourceConfig)

    @property
    def llm(self) -> LLMConfig:
        return self.ollama

    @model_validator(mode="after")
    def reject_non_paper_mode(self) -> "Config":
        if self.app.mode != "paper":
            raise ValueError("Phase 1 only supports paper mode")
        return self


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_absolute() and not config_path.exists():
        candidate = DEFAULT_CONFIG_PATH.parent / config_path
        if candidate.exists():
            config_path = candidate
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    config = Config.model_validate(raw)
    base_dir = config_path.parent
    if not Path(config.app.database_path).is_absolute():
        config.app.database_path = str(base_dir / config.app.database_path)
    if not Path(config.app.paper_log_path).is_absolute():
        config.app.paper_log_path = str(base_dir / config.app.paper_log_path)
    return config


def threshold_for_asset(config: Config, asset_code: str) -> float:
    asset = config.assets.get(asset_code)
    if asset is None:
        return config.confidence_thresholds.default
    if asset.category == "broad_index":
        return config.confidence_thresholds.broad_index
    if asset.category == "high_volatility":
        return config.confidence_thresholds.high_volatility
    return config.confidence_thresholds.default
