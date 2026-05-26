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
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import DEFAULT_CONFIG_PATH, Config, LLMConfig, load_config
from app.graph import run_once
from app.models import (
    AnalysisHistoryResponse,
    FundAnalysisRequest,
    FundAnalysisResponse,
    FundHoldingItem,
    FundNavResponse,
    GraphState,
    ImageParseRequest,
    ImageParseResponse,
    MarketOverviewResponse,
    ParsedItem,
    SectorQuoteResponse,
    StockAnalysisRequest,
    StockAnalysisResponse,
    StockQuoteResponse,
    WatchlistItem,
    WatchlistReorderRequest,
    WatchlistRequest,
)
from app.services import database, fund_service, positions, stock_service
from app.services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
    remove_from_watchlist,
    reorder_watchlist,
    update_watchlist_item,
)
from app.services.cloud_llm import CloudLLMError, CloudLLMNoAPIKeyError, test_cloud_llm_connection
from app.services.llm_settings import (
    LLMSettingsUpdate,
    get_effective_llm_config,
    get_llm_settings_view,
    update_llm_settings,
)
from app.services.research_service import analyze_fund_research

CONFIG_PATH = DEFAULT_CONFIG_PATH
LAST_STATE: dict[str, Any] | None = None

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


MOCK_MARKET_PRICES = {
    "008282": 1.10,
    "sh563300": 1.05,
    "000510": 1.08,
    "SEMICONDUCTOR_C": 1.12,
}


app = FastAPI(title="micro-quant-pipeline", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


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


def _mock_current_price(asset_code: str) -> float | None:
    return MOCK_MARKET_PRICES.get(asset_code)


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
                current_price=_mock_current_price(str(lot["asset_code"])),
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
    """Fetch real-time quotes for specified A-share stocks via AkShare."""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No valid stock codes provided")
    try:
        quotes = await run_in_threadpool(stock_service.fetch_stock_realtime_batch, code_list)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stock data fetch failed: {exc}") from exc
    return [StockQuoteResponse(**dataclasses.asdict(q)) for q in quotes]


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
    """Fetch sector board rankings sorted by change_pct descending."""
    try:
        sectors = await run_in_threadpool(stock_service.fetch_sector_list, type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sector data fetch failed: {exc}") from exc
    return [SectorQuoteResponse(**dataclasses.asdict(s)) for s in sectors[:limit]]


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
    """Fetch real-time NAV for specified funds via AkShare."""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No valid fund codes provided")
    try:
        navs = await run_in_threadpool(fund_service.fetch_fund_nav_batch, code_list)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fund NAV fetch failed: {exc}") from exc
    return [FundNavResponse(**dataclasses.asdict(n)) for n in navs]


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


# ---- Market Overview Endpoint ----


@app.get(
    "/api/market/overview",
    response_model=MarketOverviewResponse,
    summary="Market overview dashboard data",
)
async def get_market_overview(
    config: Config = Depends(get_config),
) -> MarketOverviewResponse:
    """Aggregate market overview: VIX + major A-share indices + top/bottom sectors."""
    from app.services.market_data import get_market_snapshot

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

    return MarketOverviewResponse(
        vix=snapshot.vix,
        major_indices=major,
        top_sectors=top,
        bottom_sectors=bottom,
        fetched_at=snapshot.as_of.isoformat(),
    )


# ---- Data Source Status Endpoint ----


@app.get(
    "/api/system/data-source-status",
    summary="Data source adapter health and stats",
)
async def get_data_source_status() -> dict:
    """Return per-adapter success/failure statistics from the stock data fallback chain."""
    stock_status = stock_service.fallback_chain.get_status()
    fund_status = fund_service.fallback_chain.get_status()
    # Merge: fund stats only add adapters not already in stock stats
    merged = {**stock_status}
    for name, stats in fund_status.items():
        if name not in merged:
            merged[name] = stats
    return merged


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
    return WatchlistItem(**found)


@app.get(
    "/api/fund-holdings",
    response_model=list[FundHoldingItem],
    summary="Get fund holdings with current NAV and P&L",
)
async def get_fund_holdings(
    config: Config = Depends(get_config),
) -> list[FundHoldingItem]:
    """Return fund watchlist items enriched with current NAV and P&L calculations."""
    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        fund_items = get_watchlist(conn, item_type="fund")
    finally:
        conn.close()

    if not fund_items:
        return []

    # Fetch current NAV for all fund codes
    codes = [item["code"] for item in fund_items]
    try:
        navs = await run_in_threadpool(fund_service.fetch_fund_nav_batch, codes)
        nav_map = {nav.fund_code: nav for nav in navs}
    except Exception:
        nav_map = {}

    result = []
    for item in fund_items:
        code = item["code"]
        nav_data = nav_map.get(code)

        current_nav = nav_data.nav if nav_data else None
        daily_return = nav_data.daily_return if nav_data else None
        nav_date = nav_data.nav_date if nav_data else None
        data_source = nav_data.data_source if nav_data else "unknown"

        # Calculate total P&L
        total_pnl = None
        total_pnl_pct = None
        purchase_nav = item.get("purchase_nav")
        shares = item.get("shares")
        purchase_amount = item.get("purchase_amount")

        if current_nav and purchase_nav and purchase_nav > 0:
            total_pnl_pct = round((current_nav - purchase_nav) / purchase_nav * 100, 4)
            if shares and shares > 0:
                total_pnl = round((current_nav - purchase_nav) * shares, 2)
            elif purchase_amount and purchase_amount > 0:
                total_pnl = round(purchase_amount * total_pnl_pct / 100, 2)

        result.append(FundHoldingItem(
            id=item["id"],
            code=code,
            name=item.get("name"),
            purchase_amount=purchase_amount,
            purchase_nav=purchase_nav,
            purchase_date=item.get("purchase_date"),
            shares=shares,
            current_nav=current_nav,
            current_nav_date=nav_date,
            daily_return=daily_return,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            data_source=data_source,
        ))

    return result
