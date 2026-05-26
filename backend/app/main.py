from __future__ import annotations

# ---------------------------------------------------------------------------
# [HOTFIX] Force-clear ALL proxy environment variables at process startup.
#
# On Windows, stale system/user proxy env vars (HTTP_PROXY, HTTPS_PROXY,
# ALL_PROXY, etc.) cause the `requests` library to route through a dead proxy,
# resulting in:
#   - ProxyError / RemoteDisconnected  (AkShare layer)
#   - 502 Bad Gateway                 (East Money push2 endpoint)
#
# This block MUST execute BEFORE any module that imports `requests` or
# `akshare`, because `stock_service` and `fund_service` instantiate
# AkShareAdapter / EastMoneyAdapter at module-level (which reads env vars).
# ---------------------------------------------------------------------------
import os as _os
import logging as _logging

_PROXY_KEYS = (
    "http_proxy", "HTTP_PROXY",
    "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY",
    "no_proxy", "NO_PROXY",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)

_proxy_logger = _logging.getLogger("proxy_cleanup")
_cleared = []
for _key in _PROXY_KEYS:
    if _key in _os.environ:
        _cleared.append(f"{_key}={_os.environ.pop(_key)!r}")
if _cleared:
    _proxy_logger.info(
        "Proxy env vars cleared at startup (%d vars): %s",
        len(_cleared),
        ", ".join(_cleared),
    )
else:
    _proxy_logger.debug("No proxy env vars found -- proceeding with direct connection.")

# Belt-and-suspenders: also patch requests default Session to never read
# system proxy environment variables.  This protects against lazy imports or
# third-party code that creates sessions after our initial cleanup.
try:
    import requests as _requests

    _original_merge_environment_settings = _requests.Session.merge_environment_settings

    def _no_proxy_merge_environment_settings(self, url, proxies, stream, verify, cert):
        """Override: always force proxies to empty dict (direct connection)."""
        proxies = {} if proxies is None else proxies
        return _original_merge_environment_settings(self, url, proxies, stream, verify, cert)

    _requests.Session.merge_environment_settings = _no_proxy_merge_environment_settings  # type: ignore[assignment]
    _proxy_logger.info("Patched requests.Session to ignore system proxy environment variables.")
except ImportError:
    _proxy_logger.debug("requests not yet importable -- skipping session patch (will retry on import).")

# Critical on Windows: `requests` uses urllib.request.getproxies() internally,
# which reads the Windows registry (HKCU\...\Internet Settings\ProxyEnable).
# If the system has a proxy configured (e.g. 127.0.0.1:7890 from Clash/V2Ray),
# requests will STILL try to use it even after clearing env vars.
# We must override getproxies() to return an empty dict.
import urllib.request as _urllib_request

_original_getproxies = _urllib_request.getproxies

def _no_registry_proxies() -> dict[str, str]:
    """Override: return empty proxy dict -- ignore Windows registry proxy."""
    return {}

_urllib_request.getproxies = _no_registry_proxies
_proxy_logger.info("Patched urllib.request.getproxies to ignore Windows registry proxy settings.")
# ---------------------------------------------------------------------------

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import DEFAULT_CONFIG_PATH, Config, LLMConfig, load_config
from app.graph import run_once
from app.models import (
    AIWindRequest,
    AIWindResponse,
    AnalysisHistoryResponse,
    FundAnalysisRequest,
    FundAnalysisResponse,
    FundHoldingItem,
    FundNavHistoryPoint,
    FundNavHistoryResponse,
    FundNavResponse,
    GraphState,
    HistoryPoint,
    ImageParseRequest,
    ImageParseResponse,
    IndexHistoryResponse,
    MarketOverviewResponse,
    ParsedItem,
    PositionOperationRequest,
    PositionOperationResponse,
    PositionSummaryResponse,
    SectorHistoryResponse,
    SectorQuoteResponse,
    StockAnalysisRequest,
    StockAnalysisResponse,
    StockQuoteResponse,
    WatchlistItem,
    WatchlistReorderRequest,
    WatchlistRequest,
)
from app.services import database, fund_service, positions, stock_service
from app.services.mysql_database import get_connection
from app.services.position_service import (
    add_operation,
    get_operations,
    get_summary,
    sync_watchlist_item_to_mysql,
)
from app.services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
    remove_from_watchlist,
    reorder_watchlist,
    update_watchlist_item,
)
from app.services.cloud_llm import CloudLLMError, CloudLLMNoAPIKeyError, test_cloud_llm_connection
from app.services.deepseek_search_service import DeepSeekSearchService
from app.services.deepseek_date_guard import date_guard
from app.services.llm_settings import (
    LLMSettingsUpdate,
    get_effective_llm_config,
    get_llm_settings_view,
    update_llm_settings,
)
from app.services.research_service import analyze_fund_research

import logging
logger = logging.getLogger(__name__)

CONFIG_PATH = DEFAULT_CONFIG_PATH
LAST_STATE: dict[str, Any] | None = None

# DeepSeek search service singleton (initialized at startup)
_deepseek_search_service: DeepSeekSearchService | None = None


def get_deepseek_search_service() -> DeepSeekSearchService | None:
    """Return the global DeepSeekSearchService singleton, or None if not initialized."""
    return _deepseek_search_service


# ---------------------------------------------------------------------------
# Data Persistence Service (lazy singleton for MySQL stale-data fallback)
# ---------------------------------------------------------------------------

_persistence_service = None


def _get_persistence():
    """Lazy-initialize the DataPersistenceService singleton."""
    global _persistence_service
    if _persistence_service is None:
        try:
            from app.services.data_persistence_service import DataPersistenceService
            config = load_config(CONFIG_PATH)
            _persistence_service = DataPersistenceService(config.mysql)
        except Exception as exc:
            logger.warning("Failed to initialize DataPersistenceService: %s", exc)
    return _persistence_service

ALLOWED_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]


class TriggerRequest(BaseModel):
    asset_code: str | None = Field(default=None, min_length=1, max_length=64)


class TriggerResponse(BaseModel):
    run_id: str
    state: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    mode: str


class LotResponse(BaseModel):
    id: int
    asset_code: str
    buy_date: str
    shares: float
    cost_price: float
    status: str
    holding_days: int = Field(ge=0)
    pnl_ratio: float


class ExecutionLogResponse(BaseModel):
    id: int
    run_id: str
    timestamp: str
    asset_code: str
    router_branch: str | None
    raw_signal: dict[str, Any]
    guard_result: dict[str, Any]
    final_action: str


class ComponentStatus(BaseModel):
    status: str
    detail: str | None = None


class StatusResponse(BaseModel):
    backend: ComponentStatus
    database: ComponentStatus
    langgraph: ComponentStatus
    chromadb: ComponentStatus
    ollama: ComponentStatus
    last_run: dict[str, Any] | None = None


class LLMSettingsResponse(BaseModel):
    base_url: str
    generate_path: str
    model: str
    timeout_seconds: float = Field(gt=0, le=600)
    has_api_key: bool


class LLMSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    generate_path: str | None = Field(default=None, min_length=1, max_length=255)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    api_key: str | None = Field(default=None, max_length=1000)
    persist_api_key: bool = False


class LLMSettingsTestResponse(BaseModel):
    status: str
    detail: str


class ResearchAnalyzeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)


class ResearchAnalyzeResponse(BaseModel):
    output: str


app = FastAPI(title="micro-quant-pipeline", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_init_mysql_tables():
    """Initialize MySQL tables (including data_source_cache and DeepSeek tables) at app startup."""
    global _deepseek_search_service

    try:
        from app.services.mysql_database import init_tables
        config = load_config(CONFIG_PATH)
        init_tables(
            host=config.mysql.host,
            port=config.mysql.port,
            user=config.mysql.user,
            password=config.mysql.password,
            database=config.mysql.database,
            pool_size=config.mysql.pool_size,
        )
        logger.info("MySQL tables initialized at startup")
    except Exception as exc:
        logger.warning("Failed to initialize MySQL tables at startup: %s", exc)

    # Initialize DeepSeek search service singleton
    try:
        config = load_config(CONFIG_PATH)
        ds_config = config.deepseek_search
        if ds_config.enabled:
            # Resolve API key: use deepseek_search.api_key, fall back to
            # deepseek.api_key, then main LLM key, then DEEPSEEK_API_KEY env var
            api_key = ds_config.api_key
            if not api_key:
                api_key = config.deepseek.api_key
            if not api_key:
                try:
                    main_llm = get_effective_llm_config(config)
                    api_key = main_llm.api_key or ""
                except Exception:
                    pass
            if not api_key:
                api_key = _os.environ.get("DEEPSEEK_API_KEY", "")
            if api_key:
                _deepseek_search_service = DeepSeekSearchService(
                    base_url=ds_config.base_url,
                    api_key=api_key,
                    model=ds_config.model,
                    timeout=ds_config.timeout_seconds,
                    requests_per_minute=ds_config.requests_per_minute,
                    daily_limit=ds_config.daily_limit,
                )
                logger.info("DeepSeek search service initialized (model=%s)", ds_config.model)
            else:
                logger.warning("DeepSeek search service skipped: no API key configured")
        else:
            logger.info("DeepSeek search service disabled in config")
    except Exception as exc:
        logger.warning("Failed to initialize DeepSeek search service: %s", exc)


def get_config() -> Config:
    return load_config(CONFIG_PATH)


def _validated_llm_update(request: LLMSettingsUpdateRequest, config: Config) -> LLMSettingsUpdate:
    effective_config = get_effective_llm_config(config)
    candidate_payload = effective_config.model_dump()
    for field_name in ("base_url", "generate_path", "model", "timeout_seconds"):
        value = getattr(request, field_name)
        if value is not None:
            candidate_payload[field_name] = value
    if "api_key" in request.model_fields_set:
        candidate_payload["api_key"] = request.api_key
    try:
        validated = LLMConfig.model_validate(candidate_payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return LLMSettingsUpdate(
        base_url=validated.base_url if request.base_url is not None else None,
        generate_path=validated.generate_path if request.generate_path is not None else None,
        model=validated.model if request.model is not None else None,
        timeout_seconds=validated.timeout_seconds if request.timeout_seconds is not None else None,
        api_key=validated.api_key if "api_key" in request.model_fields_set else None,
        api_key_was_provided="api_key" in request.model_fields_set,
        persist_api_key=request.persist_api_key,
    )


def _holding_days(buy_date: str, as_of: datetime | None = None) -> int:
    bought_at = datetime.fromisoformat(buy_date)
    checked_at = as_of or datetime.now(timezone.utc)
    if bought_at.tzinfo is None and checked_at.tzinfo is not None:
        bought_at = bought_at.replace(tzinfo=timezone.utc)
    if bought_at.tzinfo is not None and checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return max((checked_at - bought_at).days, 0)



def _pnl_ratio(cost_price: float, current_price: float | None) -> float:
    if current_price is None or cost_price <= 0:
        return 0.0
    return round((current_price - cost_price) / cost_price, 4)


def _state_summary(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "asset_code": state.get("asset_code"),
        "router_branch": state.get("router_branch"),
        "final_action": (state.get("guard_result") or {}).get("final_action")
        if isinstance(state.get("guard_result"), dict)
        else None,
    }


@app.get("/health", response_model=HealthResponse, summary="Backend liveness check")
async def health(config: Config = Depends(get_config)) -> HealthResponse:
    """Return a lightweight backend health response without triggering graph execution."""
    return HealthResponse(status="ok", mode=config.app.mode)


@app.get(
    "/api/lots",
    response_model=list[LotResponse],
    summary="List open position lots",
)
async def list_lots(config: Config = Depends(get_config)) -> list[LotResponse]:
    """Return OPEN SQLite lots with server-side holding-day calculations and mock pnl ratios."""
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        open_lots = positions.list_open_lots(conn)
    finally:
        conn.close()
    return [
        LotResponse(
            id=int(lot["id"]),
            asset_code=str(lot["asset_code"]),
            buy_date=str(lot["buy_date"]),
            shares=float(lot["shares"]),
            cost_price=float(lot["cost_price"]),
            status=str(lot["status"]),
            holding_days=_holding_days(str(lot["buy_date"])),
            pnl_ratio=_pnl_ratio(
                cost_price=float(lot["cost_price"]),
                current_price=None,  # No mock data -- real price requires live market feed
            ),
        )
        for lot in open_lots
    ]


@app.get(
    "/api/logs",
    response_model=list[ExecutionLogResponse],
    summary="List recent paper execution logs",
)
async def list_logs(
    limit: int = Query(default=10, ge=1, le=100),
    config: Config = Depends(get_config),
) -> list[ExecutionLogResponse]:
    """Return recent paper execution logs in reverse chronological order."""
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        recent_logs = positions.recent_execution_logs(conn, limit=limit)
    finally:
        conn.close()
    return [ExecutionLogResponse(**log) for log in recent_logs]


@app.get("/api/status", response_model=StatusResponse, summary="Component health summary")
async def api_status(config: Config = Depends(get_config)) -> StatusResponse:
    """Return backend dependency health without hard-requiring deferred services."""
    database_status = ComponentStatus(status="ok", detail=config.app.database_path)
    try:
        conn = database.connect(config.app.database_path)
        try:
            database.init_db(conn)
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception as exc:
        database_status = ComponentStatus(status="degraded", detail=str(exc))

    return StatusResponse(
        backend=ComponentStatus(status="ok", detail=f"mode={config.app.mode}"),
        database=database_status,
        langgraph=ComponentStatus(status="configured", detail="app.graph.run_once"),
        chromadb=ComponentStatus(status="unknown", detail="not wired in this iteration"),
        ollama=ComponentStatus(status="configured", detail="app.services.cloud_llm"),
        last_run=_state_summary(LAST_STATE),
    )


@app.get(
    "/api/settings/llm",
    response_model=LLMSettingsResponse,
    summary="Get effective LLM runtime settings",
)
async def get_llm_settings(config: Config = Depends(get_config)) -> LLMSettingsResponse:
    """Return effective editable LLM settings without exposing any secret api_key value."""
    return LLMSettingsResponse(**get_llm_settings_view(config))


@app.put(
    "/api/settings/llm",
    response_model=LLMSettingsResponse,
    summary="Update editable LLM runtime settings",
)
async def put_llm_settings(
    request: LLMSettingsUpdateRequest,
    config: Config = Depends(get_config),
) -> LLMSettingsResponse:
    """Persist non-secret LLM settings and optionally store api_key in memory or SQLite."""
    try:
        validated_update = _validated_llm_update(request, config)
        updated = await run_in_threadpool(update_llm_settings, config, validated_update)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return LLMSettingsResponse(**updated)


@app.post(
    "/api/settings/llm/test",
    response_model=LLMSettingsTestResponse,
    summary="Test LLM connectivity with current effective settings",
)
async def post_llm_settings_test(config: Config = Depends(get_config)) -> LLMSettingsTestResponse:
    """Only test direct LLM connectivity; do not invoke LangGraph or any trading execution path."""
    try:
        await test_cloud_llm_connection(config)
    except CloudLLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return LLMSettingsTestResponse(status="ok", detail="LLM connectivity test succeeded")


@app.post(
    "/api/research/analyze",
    response_model=ResearchAnalyzeResponse,
    summary="Run read-only fund research analysis",
)


# ---------------------------------------------------------------------------
# Mock Toggle API
# ---------------------------------------------------------------------------


class MockSettingsResponse(BaseModel):
    enable_mock: bool


class MockSettingsUpdate(BaseModel):
    enable_mock: bool


@app.get(
    "/api/settings/mock",
    response_model=MockSettingsResponse,
    summary="Get mock data toggle state",
)
async def get_mock_settings(config: Config = Depends(get_config)) -> MockSettingsResponse:
    """Return whether mock data fallback is enabled."""
    return MockSettingsResponse(enable_mock=config.market.enable_mock)


@app.put(
    "/api/settings/mock",
    response_model=MockSettingsResponse,
    summary="Update mock data toggle",
)
async def put_mock_settings(
    update: MockSettingsUpdate,
) -> MockSettingsResponse:
    """Toggle mock data on/off by updating config.yaml."""
    import yaml

    config_path = Path(CONFIG_PATH)
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    market = raw.setdefault("market", {})
    market["enable_mock"] = update.enable_mock
    market["allow_mock_vix"] = update.enable_mock

    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return MockSettingsResponse(enable_mock=update.enable_mock)
async def post_research_analyze(
    request: ResearchAnalyzeRequest,
    config: Config = Depends(get_config),
) -> ResearchAnalyzeResponse:
    """Run cloud-backed read-only research without touching execution, lots, or logs."""
    try:
        output = await analyze_fund_research(config, request.prompt)
    except CloudLLMNoAPIKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM API key not configured. Please set it in Settings page. Error: {exc}",
        ) from exc
    except CloudLLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ResearchAnalyzeResponse(output=output)


@app.post(
    "/api/trigger",
    response_model=TriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger one paper-only graph run",
)
async def trigger_graph(request: TriggerRequest) -> TriggerResponse:
    """Run the LangGraph pipeline once and return the generated run id plus final state."""
    global LAST_STATE
    run_id = uuid4().hex
    try:
        state: GraphState = await run_in_threadpool(
            run_once,
            asset_code=request.asset_code,
            config_path=CONFIG_PATH,
            run_id=run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Graph run failed",
        ) from exc
    LAST_STATE = dict(state)
    return TriggerResponse(run_id=run_id, state=LAST_STATE)


# ---- Stock Sector Endpoints ----


@app.get(
    "/api/stocks/realtime",
    response_model=list[StockQuoteResponse],
    summary="Fetch real-time A-share stock quotes",
)
async def get_stock_realtime(
    codes: str = Query(..., min_length=1, description="Comma-separated stock codes, e.g. 600519,000001"),
    config: Config = Depends(get_config),
) -> list[StockQuoteResponse]:
    """Fetch real-time quotes for specified A-share stocks via AkShare.

    On success, stores the result in MySQL for stale-data fallback.
    When all sources fail, returns the most recent cached record with stale=True.
    """
    from app.services.data_persistence_service import stock_realtime_key

    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No valid stock codes provided")

    ps = _get_persistence()
    qk = stock_realtime_key(code_list)

    try:
        quotes = await run_in_threadpool(stock_service.fetch_stock_realtime_batch, code_list)
        result = [StockQuoteResponse(**dataclasses.asdict(q)) for q in quotes]

        if ps and result:
            try:
                ps.store("stock-realtime", "live", qk, [dataclasses.asdict(q) for q in quotes])
            except Exception as store_exc:
                logger.debug("Failed to persist stock-realtime: %s", store_exc)

        return result
    except Exception as exc:
        logger.warning("Live stock-realtime failed: %s", exc)

        if ps:
            fallback = ps.retrieve("stock-realtime", qk)
            if fallback:
                cached_data, cached_source, cached_at, _ = fallback
                logger.info("Returning stale stock-realtime from %s", cached_source)
                return [StockQuoteResponse(**{**d, "stale": True}) for d in cached_data]

        raise HTTPException(status_code=502, detail=f"Stock data fetch failed: {exc}") from exc


@app.get(
    "/api/stocks/sectors",
    response_model=list[SectorQuoteResponse],
    summary="Fetch A-share sector board rankings",
)
async def get_stock_sectors(
    type: str = Query(default="industry", pattern="^(industry|concept)$"),
    limit: int = Query(default=20, ge=1, le=100),
    config: Config = Depends(get_config),
) -> list[SectorQuoteResponse]:
    """Fetch sector board rankings sorted by change_pct descending.

    On success, stores the result in MySQL for stale-data fallback.
    When all sources fail, returns the most recent cached record with stale=True.
    """
    from app.services.data_persistence_service import sector_list_key

    ps = _get_persistence()
    qk = sector_list_key(type, limit)

    try:
        sectors = await run_in_threadpool(stock_service.fetch_sector_list, type)
        result = [SectorQuoteResponse(**dataclasses.asdict(s)) for s in sectors[:limit]]

        if ps and result:
            try:
                ps.store("sectors", "live", qk, [dataclasses.asdict(s) for s in sectors[:limit]])
            except Exception as store_exc:
                logger.debug("Failed to persist sectors: %s", store_exc)

        return result
    except Exception as exc:
        logger.warning("Live sectors fetch failed: %s", exc)

        if ps:
            fallback = ps.retrieve("sectors", qk)
            if fallback:
                cached_data, cached_source, cached_at, _ = fallback
                logger.info("Returning stale sectors from %s", cached_source)
                return [SectorQuoteResponse(**{**d, "stale": True}) for d in cached_data]

        raise HTTPException(status_code=502, detail=f"Sector data fetch failed: {exc}") from exc


@app.post(
    "/api/stocks/analyze",
    response_model=StockAnalysisResponse,
    summary="AI stock sector analysis",
)
async def post_stock_analyze(
    request: StockAnalysisRequest,
    config: Config = Depends(get_config),
) -> StockAnalysisResponse:
    """Run AI-powered stock sector analysis. Provide either sector_name or stock_code."""
    from app.services.stock_analysis_service import analyze_single_stock, analyze_stock_sector

    try:
        if request.sector_name:
            result = await analyze_stock_sector(config, request.sector_name, request.sector_type)
        elif request.stock_code:
            result = await analyze_single_stock(config, request.stock_code)
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide either sector_name or stock_code",
            )
    except CloudLLMNoAPIKeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LLM API key not configured. Please set it in Settings page. Error: {exc}",
        ) from exc
    except CloudLLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StockAnalysisResponse(**dataclasses.asdict(result))


# ---- Fund Sector Endpoints ----


@app.get(
    "/api/funds/nav",
    response_model=list[FundNavResponse],
    summary="Fetch real-time fund NAV",
)
async def get_fund_nav(
    codes: str = Query(..., min_length=1, description="Comma-separated fund codes, e.g. 000510,008282"),
    config: Config = Depends(get_config),
) -> list[FundNavResponse]:
    """Fetch real-time NAV for specified funds via AkShare.

    On success, stores the result in MySQL for stale-data fallback.
    When all sources fail, returns the most recent cached record with stale=True.
    """
    from app.services.data_persistence_service import fund_nav_key

    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No valid fund codes provided")

    ps = _get_persistence()
    qk = fund_nav_key(code_list)

    try:
        navs = await run_in_threadpool(fund_service.fetch_fund_nav_batch, code_list)
        result = [FundNavResponse(**dataclasses.asdict(n)) for n in navs]

        if ps and result:
            try:
                ps.store("fund-nav", "live", qk, [dataclasses.asdict(n) for n in navs])
            except Exception as store_exc:
                logger.debug("Failed to persist fund-nav: %s", store_exc)

        return result
    except Exception as exc:
        logger.warning("Live fund-nav failed: %s", exc)

        if ps:
            fallback = ps.retrieve("fund-nav", qk)
            if fallback:
                cached_data, cached_source, cached_at, _ = fallback
                logger.info("Returning stale fund-nav from %s", cached_source)
                return [FundNavResponse(**{**d, "stale": True}) for d in cached_data]

        raise HTTPException(status_code=502, detail=f"Fund NAV fetch failed: {exc}") from exc


@app.post(
    "/api/funds/analyze",
    response_model=FundAnalysisResponse,
    summary="AI fund comprehensive judgment",
)
async def post_fund_analyze(
    request: FundAnalysisRequest,
    config: Config = Depends(get_config),
) -> FundAnalysisResponse:
    """Run AI-powered fund analysis combining NAV data, news, and sentiment."""
    from app.services.fund_analysis_service import analyze_fund_sector

    try:
        result = await analyze_fund_sector(config, request.fund_code, request.custom_prompt)
    except CloudLLMNoAPIKeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LLM API key not configured. Please set it in Settings page. Error: {exc}",
        ) from exc
    except CloudLLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FundAnalysisResponse(**dataclasses.asdict(result))


@app.get(
    "/api/funds/nav-realtime",
    response_model=list[FundNavResponse],
    summary="Fetch real-time fund NAV (intraday refresh)",
)
async def get_fund_nav_realtime(
    codes: str = Query(..., min_length=1, description="Comma-separated fund codes, e.g. 000510,008282"),
    config: Config = Depends(get_config),
) -> list[FundNavResponse]:
    """Fetch minute-level real-time NAV for specified funds via AkShare."""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No valid fund codes provided")
    try:
        navs = await run_in_threadpool(fund_service.fetch_fund_nav_batch, code_list)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fund NAV fetch failed: {exc}") from exc
    return [FundNavResponse(**dataclasses.asdict(n)) for n in navs]


@app.post(
    "/api/funds/ai-wind",
    response_model=AIWindResponse,
    summary="AI wind vane: market sentiment and fund recommendations",
)
async def post_ai_wind(
    request: AIWindRequest,
    config: Config = Depends(get_config),
) -> AIWindResponse:
    """Run DeepSeek-powered AI wind vane analysis combining sector data and user holdings.

    Returns hot sectors, fund operation recommendations, market sentiment score, and summary.
    Results are cached for 300 seconds unless force_refresh is set.
    """
    from app.services.deepseek_wind_service import analyze_ai_wind

    try:
        result = await analyze_ai_wind(config, force_refresh=request.force_refresh)
    except CloudLLMNoAPIKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DeepSeek API key not configured. Error: {exc}",
        ) from exc
    except CloudLLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return AIWindResponse(
        hot_sectors=result.hot_sectors,
        fund_recommendations=result.fund_recommendations,
        market_sentiment=result.market_sentiment,
        sentiment_score=result.sentiment_score,
        summary=result.summary,
        generated_at=result.generated_at,
        cached=result.cached,
    )


# ---- Market Overview Endpoint ----


@app.get(
    "/api/market/overview",
    response_model=MarketOverviewResponse,
    summary="Market overview dashboard data",
)
async def get_market_overview(
    config: Config = Depends(get_config),
) -> MarketOverviewResponse:
    """Aggregate market overview: VIX + major A-share indices + top/bottom sectors.

    On success, stores the result in MySQL for stale-data fallback.
    When all sources fail, returns the most recent cached record with stale=True.
    """
    from app.services.data_persistence_service import market_overview_key
    from app.services.market_data import get_market_snapshot

    ps = _get_persistence()
    qk = market_overview_key()

    try:
        snapshot = get_market_snapshot(config)

        major: list[StockQuoteResponse] = []
        sectors: list[SectorQuoteResponse] = []

        try:
            major_quotes = await run_in_threadpool(
                stock_service.fetch_stock_realtime_batch,
                ["000001", "399001", "000300", "000905"],
            )
            major = [StockQuoteResponse(**dataclasses.asdict(m)) for m in major_quotes]
        except Exception:
            major = []

        try:
            sector_quotes = await run_in_threadpool(stock_service.fetch_sector_list, "industry")
            sector_resp = [SectorQuoteResponse(**dataclasses.asdict(s)) for s in sector_quotes]
            top = sorted(sector_resp, key=lambda s: s.change_pct, reverse=True)[:5]
            bottom = sorted(sector_resp, key=lambda s: s.change_pct)[:5]
        except Exception:
            top, bottom = [], []

        result = MarketOverviewResponse(
            vix=snapshot.vix,
            major_indices=major,
            top_sectors=top,
            bottom_sectors=bottom,
            fetched_at=snapshot.as_of.isoformat(),
            stale=False,
        )

        # Store for fallback (only if we got some data)
        if ps and (major or top or bottom):
            try:
                store_data = {
                    "vix": snapshot.vix,
                    "major_indices": [dataclasses.asdict(m) for m in major],
                    "top_sectors": [dataclasses.asdict(s) for s in top],
                    "bottom_sectors": [dataclasses.asdict(s) for s in bottom],
                }
                ps.store("market-overview", "live", qk, store_data)
            except Exception as store_exc:
                logger.debug("Failed to persist market-overview: %s", store_exc)

        return result

    except Exception as exc:
        logger.warning("Live market-overview failed: %s", exc)

        if ps:
            fallback = ps.retrieve("market-overview", qk)
            if fallback:
                cached_data, cached_source, cached_at, _ = fallback
                logger.info("Returning stale market-overview from %s", cached_source)
                return MarketOverviewResponse(
                    vix=cached_data.get("vix"),
                    major_indices=[StockQuoteResponse(**{**d, "stale": True}) for d in cached_data.get("major_indices", [])],
                    top_sectors=[SectorQuoteResponse(**{**d, "stale": True}) for d in cached_data.get("top_sectors", [])],
                    bottom_sectors=[SectorQuoteResponse(**{**d, "stale": True}) for d in cached_data.get("bottom_sectors", [])],
                    fetched_at=cached_at,
                    stale=True,
                    cached_at=cached_at,
                )

        raise HTTPException(
            status_code=500,
            detail=f"Market overview fetch failed: {exc}",
        ) from exc


# ---- Data Source Status Endpoint (cached) ----

import time as _time

_ds_status_cache: dict[str, Any] = {}
_ds_status_ts: float = 0.0
_DS_STATUS_TTL: float = 300.0  # 5 minutes


@app.get(
    "/api/system/data-source-status",
    summary="Data source adapter health and stats",
)
async def get_data_source_status() -> dict:
    """Return per-adapter success/failure statistics from all data source fallback chains.

    Results are cached for 5 minutes to avoid expensive health-check calls
    on every request.  Includes real-time data adapters (stock, fund) and
    historical data adapters (tushare, baostock, efinance, akshare, deepseek).
    """
    global _ds_status_cache, _ds_status_ts
    now = _time.time()

    # Return cached result if still fresh
    if _ds_status_cache and (now - _ds_status_ts) < _DS_STATUS_TTL:
        return _ds_status_cache

    stock_status = stock_service.fallback_chain.get_status()
    fund_status = fund_service.fallback_chain.get_status()

    # Merge: fund stats only add adapters not already in stock stats
    merged = {**stock_status}
    for name, stats in fund_status.items():
        if name not in merged:
            merged[name] = stats

    # Add historical data adapter status (expensive -- only on cache miss)
    try:
        from app.services.historical_data_service import create_historical_data_service
        config = load_config()
        ds_service = get_deepseek_search_service()
        hist_service = create_historical_data_service(config, deepseek_search_service=ds_service)
        historical_status = hist_service.get_data_source_status()
        merged["historical_adapters"] = historical_status
    except Exception as exc:
        logger.warning("Failed to get historical data source status: %s", exc)
        merged["historical_adapters"] = {"error": str(exc)}

    _ds_status_cache = merged
    _ds_status_ts = now
    return merged


# ---- DeepSeek Search Status Endpoint ----


@app.get(
    "/api/system/deepseek-status",
    summary="DeepSeek web search service status",
)
async def get_deepseek_status() -> dict:
    """Return DeepSeek web search service health, rate limiter, and circuit breaker status."""
    ds_service = get_deepseek_search_service()
    if ds_service is None:
        return {
            "enabled": False,
            "initialized": False,
            "error": "DeepSeek search service not initialized (check API key config)",
        }

    status = ds_service.get_status()
    return {
        "enabled": True,
        "initialized": True,
        "rate_limiter": status["rate_limiter"],
        "circuit_breaker": status["circuit_breaker"],
    }


# ---- DeepSeek Q&A Endpoint ----


class DeepSeekAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)


class DeepSeekAskResponse(BaseModel):
    answer: str
    model: str
    sources: list[str] = []


@app.post(
    "/api/deepseek/ask",
    response_model=DeepSeekAskResponse,
    summary="Ask DeepSeek a financial question",
)
async def post_deepseek_ask(request: DeepSeekAskRequest) -> DeepSeekAskResponse:
    """Send a financial question to DeepSeek and return the answer.

    Uses the same DeepSeek API configuration as the search service.
    Falls back to the main LLM if DeepSeek is not configured.

    The date guard middleware ensures that:
    - The system prompt includes the real CST date.
    - Vague date words in the user message are replaced with absolute dates.
    - The response is validated for stale dates (retries once if stale).
    """
    import httpx as _httpx

    ds_service = get_deepseek_search_service()

    # Build the prompt with a financial-analysis system instruction
    system_msg = (
        "你是一个专业的金融分析师助手，具备联网搜索能力。"
        "请务必使用联网搜索功能获取最新的市场数据和金融信息来回答用户问题。"
        "当用户询问市场行情、股票走势、基金表现等实时信息时，必须先搜索最新数据再回答。"
        "回答要专业、准确、有条理，并注明数据来源和时间。"
    )

    # --- Date guard: inject real date + clean user message ---
    system_msg, user_msg = date_guard.process_request(system_msg, request.question)

    if ds_service is not None:
        # Use the DeepSeek search service's API configuration
        base_url = ds_service.base_url
        api_key = ds_service.api_key
        model = ds_service.model
        timeout = ds_service.timeout
    else:
        # Fall back to main LLM config
        config = load_config(CONFIG_PATH)
        try:
            main_llm = get_effective_llm_config(config)
            base_url = main_llm.base_url.rstrip("/")
            api_key = main_llm.api_key or ""
            model = main_llm.model
            timeout = int(main_llm.timeout_seconds)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"No LLM configured. Please set an API key in Settings. Error: {exc}",
            ) from exc

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No API key configured. Please set an API key in Settings.",
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Helper: build the request body for a given system/user message pair
    def _build_body(sys_content: str, usr_content: str) -> dict:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": usr_content},
            ],
            "tools": [
                {
                    "type": "web_search",
                    "web_search": {"enable": True},
                }
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

    # Helper: extract text content from API response data
    def _extract_content(data: dict) -> str:
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls")
        if tool_calls and not content:
            parts = []
            for tc in tool_calls:
                func = tc.get("function", {})
                if func.get("arguments"):
                    parts.append(func["arguments"])
            if parts:
                content = "\n".join(parts)
        return content or "未能获取到有效回答，请重试。"

    # Helper: send a single request, handling the tools-parameter 400 fallback
    async def _send_request(
        client: _httpx.AsyncClient, body: dict
    ) -> dict:
        resp = await client.post(
            f"{base_url}/chat/completions", json=body, headers=headers
        )
        if resp.status_code == 400:
            logger.warning(
                "DeepSeek API rejected tools parameter, retrying without web search"
            )
            body.pop("tools", None)
            resp = await client.post(
                f"{base_url}/chat/completions", json=body, headers=headers
            )
        resp.raise_for_status()
        return resp.json()

    today_cn, today_iso, _ = date_guard.get_real_date()

    try:
        async with _httpx.AsyncClient(timeout=timeout) as client:
            # --- First attempt ---
            body = _build_body(system_msg, user_msg)
            data = await _send_request(client, body)
            content = _extract_content(data)

            # --- Validate response dates ---
            is_valid, reason = date_guard.process_response(content)
            if not is_valid:
                logger.warning(
                    "DeepSeek response has stale dates (%s), retrying with stronger date prompt",
                    reason,
                )
                # --- Retry with explicit date emphasis ---
                retry_system = (
                    system_msg
                    + f"\n\n【紧急提醒】你的上一次回答包含错误日期（{reason}）。"
                    f"当前真实日期是{today_cn}（{today_iso}）。"
                    f"请务必使用此日期重新搜索并回答，绝对不能使用其他日期。"
                )
                retry_body = _build_body(retry_system, user_msg)
                data = await _send_request(client, retry_body)
                content = _extract_content(data)

                # Final validation
                is_valid, reason = date_guard.process_response(content)
                if not is_valid:
                    logger.error(
                        "DeepSeek response still has stale dates after retry: %s", reason
                    )
                    return DeepSeekAskResponse(
                        answer=f"无法获取{today_cn}的最新数据，DeepSeek返回了过期日期（{reason}）。请稍后重试。",
                        model=model,
                        sources=[],
                    )

        return DeepSeekAskResponse(
            answer=content,
            model=model,
            sources=[],
        )
    except _httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="DeepSeek API request timed out. Please try again.",
        )
    except _httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"DeepSeek API error: {exc.response.text}",
        )
    except Exception as exc:
        logger.error("DeepSeek ask failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek API call failed: {exc}",
        ) from exc


# ---- Data Source Selection API ----


class DataSourcePreferenceResponse(BaseModel):
    active_source: str
    available_sources: list[str]


class DataSourcePreferenceUpdate(BaseModel):
    active_source: str = Field(min_length=1, max_length=50)


@app.get(
    "/api/settings/data-source",
    response_model=DataSourcePreferenceResponse,
    summary="Get active historical data source preference",
)
async def get_data_source_preference(
    config: Config = Depends(get_config),
) -> DataSourcePreferenceResponse:
    """Return the currently active historical data source and available sources."""
    try:
        from app.services.historical_data_service import create_historical_data_service
        service = create_historical_data_service(config)
        return DataSourcePreferenceResponse(
            active_source=service.get_active_source(),
            available_sources=service.get_available_sources(),
        )
    except Exception as exc:
        logger.error("Failed to get data source preference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data source preference: {exc}",
        ) from exc


@app.put(
    "/api/settings/data-source",
    response_model=DataSourcePreferenceResponse,
    summary="Set active historical data source preference",
)
async def put_data_source_preference(
    update: DataSourcePreferenceUpdate,
    config: Config = Depends(get_config),
) -> DataSourcePreferenceResponse:
    """Set the active historical data source. Persists to config.yaml.

    Use "auto" for the full fallback chain, or a specific adapter name
    (e.g. "baostock", "tushare", "efinance", "akshare").
    """
    try:
        from app.services.historical_data_service import create_historical_data_service
        service = create_historical_data_service(config)
        service.set_active_source(update.active_source)
        return DataSourcePreferenceResponse(
            active_source=service.get_active_source(),
            available_sources=service.get_available_sources(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to set data source preference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set data source preference: {exc}",
        ) from exc


# ---- Analysis History Endpoint ----


@app.get(
    "/api/analysis/history",
    response_model=list[AnalysisHistoryResponse],
    summary="AI analysis history logs",
)
async def get_analysis_history(
    type: str = Query(default="all", pattern="^(all|stock_sector|fund_sector)$"),
    limit: int = Query(default=20, ge=1, le=100),
    config: Config = Depends(get_config),
) -> list[AnalysisHistoryResponse]:
    """Return recent AI analysis logs, optionally filtered by type."""
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        logs = stock_service.get_analysis_logs(conn, analysis_type=type, limit=limit)
    finally:
        conn.close()
    return [AnalysisHistoryResponse(**log) for log in logs]


# ---- Watchlist Endpoints ----


@app.get(
    "/api/watchlist",
    response_model=list[WatchlistItem],
    summary="Get user watchlist",
)
async def get_watchlist_endpoint(
    type: str = Query(default="all", pattern="^(all|stock|fund)$"),
    config: Config = Depends(get_config),
) -> list[WatchlistItem]:
    """Return user watchlist items, optionally filtered by stock or fund."""
    item_type: str | None = None if type == "all" else type
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        items = get_watchlist(conn, item_type=item_type)
    finally:
        conn.close()
    return [WatchlistItem(**item) for item in items]


@app.post(
    "/api/watchlist",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add item to watchlist",
)
async def post_watchlist(
    request: WatchlistRequest,
    config: Config = Depends(get_config),
) -> WatchlistItem:
    """Add a stock or fund to the user watchlist. Auto-deduplicates by (item_type, code).

    If *name* is omitted the service attempts an AkShare lookup (best-effort).
    """
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        try:
            item = add_to_watchlist(
                conn,
                item_type=request.item_type,
                code=request.code,
                name=request.name,
                purchase_amount=request.purchase_amount,
                purchase_nav=request.purchase_nav,
                purchase_date=request.purchase_date,
                shares=request.shares,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        conn.close()
    # Sync to MySQL for position operations
    try:
        sync_watchlist_item_to_mysql(
            mysql_cfg=config.mysql,
            item_type=item["item_type"],
            code=item["code"],
            name=item.get("name"),
            purchase_amount=item.get("purchase_amount"),
            purchase_nav=item.get("purchase_nav"),
            purchase_date=item.get("purchase_date"),
            shares=item.get("shares"),
            added_at=item.get("added_at"),
            sort_order=item.get("sort_order", 0),
        )
    except Exception as exc:
        logger.warning("Failed to sync watchlist item to MySQL: %s", exc)
    return WatchlistItem(**item)


@app.delete(
    "/api/watchlist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove item from watchlist",
)
async def delete_watchlist(
    item_id: int,
    config: Config = Depends(get_config),
):
    """Remove a watchlist entry by its id."""
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        deleted = remove_from_watchlist(conn, item_id)
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")


@app.put(
    "/api/watchlist/reorder",
    response_model=list[WatchlistItem],
    summary="Reorder watchlist items",
)
async def put_watchlist_reorder(
    request: WatchlistReorderRequest,
    config: Config = Depends(get_config),
) -> list[WatchlistItem]:
    """Reorder watchlist items. The *item_ids* list defines the new sort order (index 0 = first)."""
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        reorder_watchlist(conn, request.item_ids)
        items = get_watchlist(conn)
    finally:
        conn.close()
    return [WatchlistItem(**item) for item in items]


@app.post(
    "/api/watchlist/parse-image",
    response_model=ImageParseResponse,
    summary="Parse image for stock/fund codes",
)
async def post_watchlist_parse_image(
    request: ImageParseRequest,
    config: Config = Depends(get_config),
) -> ImageParseResponse:
    """Extract stock and fund codes from a base64-encoded screenshot using OCR / regex."""
    from app.services.ocr_service import parse_image_base64

    try:
        parsed = await run_in_threadpool(parse_image_base64, request.image_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image parsing failed: {exc}",
        ) from exc
    items = [ParsedItem(**p) for p in parsed]
    return ImageParseResponse(items=items)


class WatchlistUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    purchase_amount: float | None = Field(default=None, gt=0)
    purchase_nav: float | None = Field(default=None, gt=0)
    purchase_date: str | None = Field(default=None, max_length=20)
    shares: float | None = Field(default=None, gt=0)


@app.put(
    "/api/watchlist/{item_id}",
    response_model=WatchlistItem,
    summary="Update watchlist item purchase info",
)
async def put_watchlist_item(
    item_id: int,
    request: WatchlistUpdateRequest,
    config: Config = Depends(get_config),
) -> WatchlistItem:
    """Update a watchlist item's name or purchase info."""
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        updated = update_watchlist_item(
            conn,
            item_id,
            name=request.name,
            purchase_amount=request.purchase_amount,
            purchase_nav=request.purchase_nav,
            purchase_date=request.purchase_date,
            shares=request.shares,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")
        item = database.get_watchlist_item_by_code(conn, "fund", "") or {}
        # Re-fetch by getting all and filtering
        all_items = get_watchlist(conn)
        found = next((i for i in all_items if i["id"] == item_id), None)
        if found is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")
    finally:
        conn.close()
    # Sync to MySQL for position operations
    try:
        sync_watchlist_item_to_mysql(
            mysql_cfg=config.mysql,
            item_type=found["item_type"],
            code=found["code"],
            name=found.get("name"),
            purchase_amount=found.get("purchase_amount"),
            purchase_nav=found.get("purchase_nav"),
            purchase_date=found.get("purchase_date"),
            shares=found.get("shares"),
            added_at=found.get("added_at"),
            sort_order=found.get("sort_order", 0),
        )
    except Exception as exc:
        logger.warning("Failed to sync watchlist update to MySQL: %s", exc)
    return WatchlistItem(**found)


@app.get(
    "/api/fund-holdings",
    response_model=list[FundHoldingItem],
    summary="Get fund holdings with current NAV and P&L",
)
async def get_fund_holdings(config: Config = Depends(get_config)) -> list[FundHoldingItem]:
    """Return fund watchlist items enriched with current NAV and P&L.

    For each fund in user_watchlist (MySQL):
    1. Fetch current NAV from fund_service
    2. Calculate daily return, total P&L, and P&L percentage
    3. Return enriched FundHoldingItem list
    """
    try:
        with get_connection(
            host=config.mysql.host,
            port=config.mysql.port,
            user=config.mysql.user,
            password=config.mysql.password,
            database=config.mysql.database,
            pool_size=config.mysql.pool_size,
        ) as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, code, name, purchase_amount, purchase_nav, "
                "purchase_date, shares, current_nav, current_nav_date, "
                "daily_return, total_pnl, total_pnl_pct "
                "FROM user_watchlist WHERE item_type = 'fund' ORDER BY sort_order, added_at"
            )
            rows = cursor.fetchall()
            cursor.close()
    except Exception as exc:
        logger.warning("Failed to read fund holdings from MySQL: %s", exc)
        rows = []

    results: list[FundHoldingItem] = []
    for row in rows:
        code = row.get("code", "")
        current_nav = row.get("current_nav")
        daily_return = row.get("daily_return")
        total_pnl = row.get("total_pnl")
        total_pnl_pct = row.get("total_pnl_pct")
        data_source = "mysql"

        # Try to fetch live NAV if we have a fund code
        if code:
            try:
                nav_data = fund_service.fetch_fund_nav(code)
                if nav_data and nav_data.nav is not None:
                    current_nav = nav_data.nav
                    daily_return = nav_data.daily_return
                    data_source = nav_data.data_source or "akshare"

                    # Calculate P&L if we have purchase info
                    purchase_nav = row.get("purchase_nav")
                    shares = row.get("shares")
                    purchase_amount = row.get("purchase_amount")

                    if purchase_nav and shares and current_nav:
                        total_pnl = round((current_nav - purchase_nav) * shares, 2)
                        if purchase_nav > 0:
                            total_pnl_pct = round(((current_nav - purchase_nav) / purchase_nav) * 100, 4)
                    elif purchase_amount and purchase_nav and current_nav and purchase_nav > 0:
                        estimated_shares = purchase_amount / purchase_nav
                        total_pnl = round((current_nav - purchase_nav) * estimated_shares, 2)
                        total_pnl_pct = round(((current_nav - purchase_nav) / purchase_nav) * 100, 4)
            except Exception as exc:
                logger.debug("Failed to fetch live NAV for %s: %s", code, exc)

        results.append(FundHoldingItem(
            id=row.get("id", 0),
            code=code,
            name=row.get("name"),
            purchase_amount=row.get("purchase_amount"),
            purchase_nav=row.get("purchase_nav"),
            purchase_date=str(row.get("purchase_date")) if row.get("purchase_date") else None,
            shares=row.get("shares"),
            current_nav=current_nav,
            current_nav_date=str(row.get("current_nav_date")) if row.get("current_nav_date") else None,
            daily_return=daily_return,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            data_source=data_source,
        ))

    return results


@app.post(
    "/api/watchlist/{item_id}/operations",
    response_model=PositionOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute position operation (buy/sell/add/reduce)",
)
async def post_position_operation(
    item_id: int,
    request: PositionOperationRequest,
    config: Config = Depends(get_config),
) -> PositionOperationResponse:
    """Execute a position operation on a watchlist item.

    Supports buy, sell, add, reduce operations.
    Automatically updates the watchlist item's shares and NAV.
    """
    try:
        result = add_operation(
            mysql_cfg=config.mysql,
            watchlist_id=item_id,
            operation_type=request.operation_type,
            operation_amount=request.operation_amount,
            operation_shares=request.operation_shares,
            operation_nav=request.operation_nav,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Position operation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Position operation failed: {exc}",
        ) from exc
    return PositionOperationResponse(**result)


@app.get(
    "/api/watchlist/{item_id}/operations",
    response_model=list[PositionOperationResponse],
    summary="Get position operation history",
)
async def get_position_operations(
    item_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    config: Config = Depends(get_config),
) -> list[PositionOperationResponse]:
    """Return operation history for a specific watchlist item."""
    try:
        rows = get_operations(
            mysql_cfg=config.mysql,
            watchlist_id=item_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error("Failed to fetch operations: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch operations: {exc}",
        ) from exc
    return [PositionOperationResponse(**row) for row in rows]


@app.get(
    "/api/watchlist/summary",
    response_model=PositionSummaryResponse,
    summary="Get portfolio position summary",
)
async def get_position_summary(
    config: Config = Depends(get_config),
) -> PositionSummaryResponse:
    """Return aggregated portfolio summary with per-item operation metadata."""
    try:
        result = get_summary(mysql_cfg=config.mysql)
    except Exception as exc:
        logger.error("Failed to fetch position summary: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch position summary: {exc}",
        ) from exc
    return PositionSummaryResponse(**result)


# ---------------------------------------------------------------------------
# Historical Data Endpoints
# ---------------------------------------------------------------------------


@app.get(
    "/api/stocks/sector-history",
    response_model=SectorHistoryResponse,
    summary="Get sector historical kline data",
)
async def get_sector_history(
    sector_name: str = Query(..., min_length=1, description="板块名称，如 '白酒'"),
    sector_type: str = Query("industry", description="板块类型: industry 或 concept"),
    days: int = Query(60, ge=1, le=365, description="历史天数"),
) -> SectorHistoryResponse:
    """Return historical daily kline data for a sector.

    On success, stores the result in MySQL for stale-data fallback.
    When all sources fail, returns the most recent cached record with stale=True.
    """
    from app.services.data_persistence_service import sector_history_key

    ps = _get_persistence()
    qk = sector_history_key(sector_name, sector_type, days)

    try:
        data = await run_in_threadpool(
            stock_service.fetch_sector_history, sector_name, sector_type, days
        )
        # Store successful result for future fallback
        if ps and data:
            try:
                ps.store("sector-history", "live", qk, data)
            except Exception as store_exc:
                logger.debug("Failed to persist sector-history: %s", store_exc)

        return SectorHistoryResponse(
            sector_name=sector_name,
            sector_type=sector_type,
            data=[HistoryPoint(**d) for d in data],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            stale=False,
        )
    except (ValueError, Exception) as exc:
        logger.warning("Live sector-history failed for %s: %s", sector_name, exc)

        # Try MySQL fallback
        if ps:
            fallback = ps.retrieve("sector-history", qk)
            if fallback:
                cached_data, cached_source, cached_at, _ = fallback
                logger.info("Returning stale sector-history for %s from %s", sector_name, cached_source)
                return SectorHistoryResponse(
                    sector_name=sector_name,
                    sector_type=sector_type,
                    data=[HistoryPoint(**d) for d in cached_data],
                    fetched_at=cached_at,
                    stale=True,
                    cached_at=cached_at,
                )

        # No fallback available
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sector history: {exc}",
        ) from exc


@app.get(
    "/api/stocks/index-history",
    response_model=IndexHistoryResponse,
    summary="Get stock index historical kline data",
)
async def get_index_history(
    code: str = Query(..., min_length=1, description="指数代码，如 '000001'"),
    days: int = Query(60, ge=1, le=365, description="历史天数"),
) -> IndexHistoryResponse:
    """Return historical daily kline data for a stock index.

    On success, stores the result in MySQL for stale-data fallback.
    When all sources fail, returns the most recent cached record with stale=True.
    """
    from app.services.data_persistence_service import index_history_key

    ps = _get_persistence()
    qk = index_history_key(code, days)

    try:
        data = await run_in_threadpool(
            stock_service.fetch_index_history, code, days
        )
        if ps and data:
            try:
                ps.store("index-history", "live", qk, data)
            except Exception as store_exc:
                logger.debug("Failed to persist index-history: %s", store_exc)

        return IndexHistoryResponse(
            index_code=code,
            data=[HistoryPoint(**d) for d in data],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            stale=False,
        )
    except (ValueError, Exception) as exc:
        logger.warning("Live index-history failed for %s: %s", code, exc)

        if ps:
            fallback = ps.retrieve("index-history", qk)
            if fallback:
                cached_data, cached_source, cached_at, _ = fallback
                logger.info("Returning stale index-history for %s from %s", code, cached_source)
                return IndexHistoryResponse(
                    index_code=code,
                    data=[HistoryPoint(**d) for d in cached_data],
                    fetched_at=cached_at,
                    stale=True,
                    cached_at=cached_at,
                )

        if isinstance(exc, ValueError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch index history: {exc}",
        ) from exc


@app.get(
    "/api/funds/nav-history",
    response_model=FundNavHistoryResponse,
    summary="Get fund NAV historical data",
)
async def get_fund_nav_history(
    code: str = Query(..., min_length=1, description="基金代码，如 '000510'"),
    days: int = Query(30, ge=1, le=365, description="历史天数"),
) -> FundNavHistoryResponse:
    """Return historical NAV data for a fund.

    On success, stores the result in MySQL for stale-data fallback.
    When all sources fail, returns the most recent cached record with stale=True.
    """
    from app.services.data_persistence_service import fund_nav_history_key

    ps = _get_persistence()
    qk = fund_nav_history_key(code, days)

    try:
        data = await run_in_threadpool(
            fund_service.fetch_fund_nav_history, code, days
        )
        if ps and data:
            try:
                ps.store("fund-nav-history", "live", qk, data)
            except Exception as store_exc:
                logger.debug("Failed to persist fund-nav-history: %s", store_exc)

        return FundNavHistoryResponse(
            fund_code=code,
            data=[FundNavHistoryPoint(**d) for d in data],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            stale=False,
        )
    except (ValueError, Exception) as exc:
        logger.warning("Live fund-nav-history failed for %s: %s", code, exc)

        if ps:
            fallback = ps.retrieve("fund-nav-history", qk)
            if fallback:
                cached_data, cached_source, cached_at, _ = fallback
                logger.info("Returning stale fund-nav-history for %s from %s", code, cached_source)
                return FundNavHistoryResponse(
                    fund_code=code,
                    data=[FundNavHistoryPoint(**d) for d in cached_data],
                    fetched_at=cached_at,
                    stale=True,
                    cached_at=cached_at,
                )

        if isinstance(exc, ValueError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch fund NAV history: {exc}",
        ) from exc
