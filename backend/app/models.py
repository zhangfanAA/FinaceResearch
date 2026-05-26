from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class MarketSnapshot(BaseModel):
    as_of: datetime
    vix: float | None
    source: Literal["yfinance", "mock", "unavailable"]


class RouterDecision(BaseModel):
    branch: Literal["emergency", "sleep", "deep"]
    reason: str


class HermesRawResponse(BaseModel):
    raw_json: dict[str, Any]
    source: Literal["stub"] = "stub"


class ParsedSignal(BaseModel):
    asset_code: str
    action: Literal["Buy", "Sell", "Hold"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    shares: float = Field(default=1.0, gt=0)
    cost_price: float = Field(default=1.0, gt=0)
    extreme_stop_loss: bool = False
    crash_override: bool = False


class GuardResult(BaseModel):
    allowed: bool
    final_action: Literal["Buy", "Sell", "Hold"]
    reason: str
    requested_shares: float = 0.0
    executable_shares: float = 0.0
    blocked_shares: float = 0.0
    partial: bool = False


class PaperExecution(BaseModel):
    run_id: str
    timestamp: datetime
    asset_code: str
    router_branch: str | None = None
    requested_action: str
    executed_action: str
    quantity: float | None = None
    reason: str
    paper_only: bool = True


class Lot(BaseModel):
    id: int
    asset_code: str
    buy_date: datetime
    shares: float
    cost_price: float
    status: Literal["OPEN", "CLOSED"]


class PaperExecutionLog(BaseModel):
    id: int
    run_id: str
    timestamp: datetime
    asset_code: str
    router_branch: str | None
    raw_signal: dict[str, Any]
    guard_result: dict[str, Any]
    final_action: str


class GraphState(TypedDict, total=False):
    run_id: str
    asset_code: str
    router_branch: str
    market_snapshot: dict[str, Any]
    retrieved_snippets: list[str]
    hermes_raw_json: dict[str, Any] | str | None
    parsed_signal: dict[str, Any]
    guard_result: dict[str, Any]
    paper_execution: dict[str, Any] | None
    retry_count: int
    errors: list[str]
    status: str


# ---- Stock Sector Models ----


class StockQuoteResponse(BaseModel):
    stock_code: str
    stock_name: str
    current_price: float
    open_price: float
    high_price: float
    low_price: float
    prev_close: float
    volume: float
    amount: float
    change_pct: float
    change_amount: float | None = None
    data_source: str = "unknown"


class SectorQuoteResponse(BaseModel):
    sector_code: str
    sector_name: str
    sector_type: str
    change_pct: float
    turnover_rate: float
    leading_stock: str
    rise_count: int
    fall_count: int
    data_source: str = "unknown"


class StockAnalysisRequest(BaseModel):
    sector_name: str | None = Field(default=None, max_length=100)
    stock_code: str | None = Field(default=None, max_length=20)
    sector_type: str = Field(default="industry", pattern="^(industry|concept)$")


class StockAnalysisResponse(BaseModel):
    target_sector: str
    trend: str
    momentum: str
    sentiment_score: float
    confidence: float
    reasoning: str
    key_factors: list[str]
    risk_warnings: list[str]
    technical_summary: dict[str, Any]


# ---- Fund Sector Models ----


class FundNavResponse(BaseModel):
    fund_code: str
    fund_name: str
    nav: float
    acc_nav: float
    nav_date: str
    daily_return: float
    data_source: str = "unknown"


class FundAnalysisRequest(BaseModel):
    fund_code: str = Field(min_length=1, max_length=20)
    custom_prompt: str | None = Field(default=None, max_length=20000)


class FundAnalysisResponse(BaseModel):
    fund_code: str
    fund_name: str
    judgment: str
    sentiment_score: float
    confidence: float
    reasoning: str
    nav_trend: str
    news_highlights: list[str]
    risk_factors: list[str]
    suggestion: str
    c_class_fee_warning: bool


# ---- Market Overview Models ----


class MarketOverviewResponse(BaseModel):
    vix: float | None
    major_indices: list[StockQuoteResponse]
    top_sectors: list[SectorQuoteResponse]
    bottom_sectors: list[SectorQuoteResponse]
    fetched_at: str


# ---- Analysis History Models ----


class AnalysisHistoryResponse(BaseModel):
    id: int
    analysis_type: str
    target_code: str
    target_name: str
    llm_raw_output: str | None
    parsed_result: str | None
    created_at: str


# ---- Watchlist Models ----


class WatchlistItem(BaseModel):
    id: int
    item_type: Literal["stock", "fund"]
    code: str
    name: str | None = None
    added_at: str
    sort_order: int = 0
    purchase_amount: float | None = None
    purchase_nav: float | None = None
    purchase_date: str | None = None
    shares: float | None = None


class WatchlistRequest(BaseModel):
    item_type: Literal["stock", "fund"]
    code: str = Field(min_length=1, max_length=20)
    name: str | None = Field(default=None, max_length=100)
    purchase_amount: float | None = Field(default=None, gt=0)
    purchase_nav: float | None = Field(default=None, gt=0)
    purchase_date: str | None = Field(default=None, max_length=20)
    shares: float | None = Field(default=None, gt=0)


class WatchlistReorderRequest(BaseModel):
    item_ids: list[int] = Field(min_length=1)


class ImageParseRequest(BaseModel):
    image_base64: str = Field(min_length=1)


class ParsedItem(BaseModel):
    code: str
    name: str | None = None
    item_type: Literal["stock", "fund"]


class ImageParseResponse(BaseModel):
    items: list[ParsedItem]


class FundHoldingItem(BaseModel):
    """A fund watchlist item enriched with current NAV and P&L data."""
    id: int
    code: str
    name: str | None = None
    purchase_amount: float | None = None
    purchase_nav: float | None = None
    purchase_date: str | None = None
    shares: float | None = None
    current_nav: float | None = None
    current_nav_date: str | None = None
    daily_return: float | None = None
    total_pnl: float | None = None
    total_pnl_pct: float | None = None
    data_source: str = "unknown"


# ---- Position Operation Models ----


class PositionOperationRequest(BaseModel):
    """Request body for executing a position operation."""
    operation_type: Literal["buy", "sell", "add", "reduce"]
    operation_amount: float | None = Field(default=None, ge=0)
    operation_shares: float | None = Field(default=None, ge=0)
    operation_nav: float | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=1000)


class PositionOperationResponse(BaseModel):
    """Response for a single position operation."""
    id: int
    watchlist_id: int
    operation_type: str
    operation_amount: float | None = None
    operation_shares: float | None = None
    operation_nav: float | None = None
    operation_date: str
    note: str | None = None
    created_at: str | None = None


class PositionSummaryItem(BaseModel):
    """A watchlist item enriched with operation metadata for summary view."""
    id: int
    item_type: str
    code: str
    name: str | None = None
    added_at: str | None = None
    sort_order: int = 0
    purchase_amount: float | None = None
    purchase_nav: float | None = None
    purchase_date: str | None = None
    shares: float | None = None
    current_nav: float | None = None
    current_nav_date: str | None = None
    daily_return: float | None = None
    total_pnl: float | None = None
    total_pnl_pct: float | None = None
    operation_count: int = 0
    latest_operation: dict[str, Any] | None = None


class PositionSummaryResponse(BaseModel):
    """Portfolio-level position summary."""
    total_items: int
    total_purchase_amount: float
    total_shares: float
    total_pnl: float
    total_pnl_pct: float
    total_current_value: float
    items: list[PositionSummaryItem]


# ---- AI Wind Vane Models ----


class HotSectorItem(BaseModel):
    sector_name: str
    change_pct: float
    reason: str


class FundRecommendationItem(BaseModel):
    direction: str
    reason: str
    fund_codes: list[str]
    fund_names: list[str]
    risk_level: str


class AIWindRequest(BaseModel):
    force_refresh: bool = False


class AIWindResponse(BaseModel):
    hot_sectors: list[HotSectorItem]
    fund_recommendations: list[FundRecommendationItem]
    market_sentiment: str
    sentiment_score: float
    summary: str
    generated_at: str
    cached: bool
