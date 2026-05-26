# Micro-Quant-Pipeline Architecture Upgrade Plan (V2)

**Date:** 2026-05-25
**Author:** architect
**Target readers:** pythonengineer, frontexpert
**Scope:** Stock Sector + Fund Sector + C/S formalization, preserving Paper-only constraint

---

## 1. Requirements Understanding

### 1.1 What We Are Building

Upgrade the existing paper-only MVP into a system with two new analysis engines:

1. **Stock Sector Engine** -- Real-time A-share market data fetching, technical indicator computation, AI-driven sector trend/momentum/sentiment analysis.
2. **Fund Sector Engine** -- Real-time fund NAV fetching, news/sentiment aggregation, AI-powered comprehensive fund judgment.

Plus formalizing the existing C/S architecture (already mostly in place) and ensuring all AI analysis reuses the existing `cloud_llm.py` (MIMO-V2.5-PRO).

### 1.2 Constraints That Do NOT Change

- Paper-only mode remains. No real broker/fund API integration.
- SQLite for all persistence. No PostgreSQL/MySQL.
- `cloud_llm.py` is the single LLM gateway. No second LLM client.
- LLM output is always a signal -- Python rules guard execution.
- C-class 7-day protection and FIFO lot logic are untouched.

---

## 2. Data Layer Design

### 2.1 Data Source Selection

#### A-Share Stock Data

| Need | Source | Rationale |
|------|--------|-----------|
| Real-time stock quotes | **AkShare** (`akshare` pip package) | Free, no API key, native CN market support, covers SH/SZ stocks and sector indices |
| Sector index data | **AkShare** sector board APIs | `ak.stock_board_concept_name_em()`, `ak.stock_board_industry_name_em()` |
| VIX (existing) | **yfinance** (`^VIX`) | Already working, no change |
| Technical indicators | **TA-Lib** or **pandas_ta** | Compute MA/RSI/MACD/KDJ/Bollinger locally from OHLCV data |
| Historical OHLCV | **AkShare** | `ak.stock_zh_a_hist()` for daily/weekly K-line data |

**Why AkShare over yfinance for A-shares:** yfinance uses Yahoo Finance tickers (e.g., `600519.SS`), which are often stale, missing, or rate-limited for CN market. AkShare pulls from East Money/Sina/Tencent directly, providing real-time quotes and sector data native to the Chinese market.

#### Fund NAV Data

| Need | Source | Rationale |
|------|--------|-----------|
| Fund real-time NAV | **AkShare** | `ak.fund_open_fund_info_em()` -- fetches latest NAV from East Money |
| Fund historical NAV | **AkShare** | `ak.fund_open_fund_daily_em()` |
| Fund basic info | **AkShare** | Fund name, type, manager, size |

#### News / Sentiment Data

| Need | Source | Rationale |
|------|--------|-----------|
| Financial news | **AkShare** news APIs + **LLM web_search** | AkShare provides `ak.stock_news_em()` for East Money news; cloud_llm already supports web_search tool for broader coverage |
| Sector news | **AkShare** + **LLM web_search** | AkShare sector-specific news; LLM can search broader context |
| Macro policy news | **LLM web_search** | Already working in `analyze_fund_research` via `allow_web_search_tools=True` |

### 2.2 New Dependencies (pip)

```
akshare>=1.14.0
pandas>=2.0.0
pandas_ta>=0.3.14b
```

No additional infrastructure needed. AkShare is pure Python, no binary dependencies.

### 2.3 Database Schema Additions

Add three new tables to the existing SQLite database. These are additive -- no existing tables are modified.

```sql
-- Cache for stock real-time quotes (TTL-based, refreshed on each request or periodically)
CREATE TABLE IF NOT EXISTS stock_quotes_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    current_price REAL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    prev_close REAL,
    volume REAL,
    amount REAL,
    change_pct REAL,
    sector_name TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(stock_code)
);

-- Cache for sector board data
CREATE TABLE IF NOT EXISTS sector_quotes_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_code TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    sector_type TEXT NOT NULL CHECK (sector_type IN ('industry', 'concept')),
    change_pct REAL,
    turnover_rate REAL,
    leading_stock TEXT,
    rise_count INTEGER,
    fall_count INTEGER,
    fetched_at TEXT NOT NULL,
    UNIQUE(sector_code, sector_type)
);

-- Cache for fund NAV data
CREATE TABLE IF NOT EXISTS fund_nav_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    fund_name TEXT,
    nav REAL,
    acc_nav REAL,
    nav_date TEXT,
    daily_return REAL,
    fetched_at TEXT NOT NULL,
    UNIQUE(fund_code)
);

-- AI analysis results log (for both stock and fund analysis)
CREATE TABLE IF NOT EXISTS analysis_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_type TEXT NOT NULL CHECK (analysis_type IN ('stock_sector', 'fund_sector')),
    target_code TEXT NOT NULL,
    target_name TEXT,
    llm_prompt TEXT,
    llm_raw_output TEXT,
    parsed_result TEXT,
    created_at TEXT NOT NULL
);
```

### 2.4 Database Service Additions

**File:** `backend/app/services/database.py` (modify existing)

Add to the existing `init_db()` function:

```python
def init_db(conn: sqlite3.Connection) -> None:
    # Existing tables
    conn.execute(LOTS_SCHEMA)
    conn.execute(PAPER_EXECUTION_LOGS_SCHEMA)
    conn.execute(APP_SETTINGS_SCHEMA)
    _migrate_positions_to_lots(conn)
    # New tables
    conn.execute(STOCK_QUOTES_CACHE_SCHEMA)
    conn.execute(SECTOR_QUOTES_CACHE_SCHEMA)
    conn.execute(FUND_NAV_CACHE_SCHEMA)
    conn.execute(ANALYSIS_LOGS_SCHEMA)
    conn.commit()
```

---

## 3. Backend Service Architecture

### 3.1 Module Map

```
backend/app/
    main.py                          # MODIFY -- add new route registrations
    config.py                        # MODIFY -- add DataSourceConfig
    models.py                        # MODIFY -- add new Pydantic models
    graph.py                         # NO CHANGE (existing graph untouched)
    nodes.py                         # NO CHANGE (existing graph untouched)
    core/
        __init__.py
        prompts.py                   # MODIFY -- add stock/fund analysis prompts
    services/
        __init__.py
        cloud_llm.py                 # NO CHANGE (reuse as-is)
        database.py                  # MODIFY -- add new table schemas
        market_data.py               # NO CHANGE (existing VIX fetch)
        positions.py                 # NO CHANGE
        paper_executor.py            # NO CHANGE
        retriever.py                 # NO CHANGE
        llm_settings.py              # NO CHANGE
        ollama.py                    # NO CHANGE
        dashboard.py                 # NO CHANGE
        stock_service.py             # NEW -- A-share data fetching + technical indicators
        fund_service.py              # NEW -- Fund NAV fetching + news aggregation
        stock_analysis_service.py    # NEW -- AI stock sector analysis orchestration
        fund_analysis_service.py     # NEW -- AI fund sector analysis orchestration
```

### 3.2 New Service: `stock_service.py`

**File:** `backend/app/services/stock_service.py` (NEW)

**Responsibility:** Fetch real-time A-share stock data and sector indices via AkShare. Compute technical indicators. Manage cache TTL.

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import akshare as ak
import pandas as pd


@dataclass(slots=True)
class StockQuote:
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
    fetched_at: str


@dataclass(slots=True)
class SectorQuote:
    sector_code: str
    sector_name: str
    sector_type: str       # "industry" | "concept"
    change_pct: float
    turnover_rate: float
    leading_stock: str
    rise_count: int
    fall_count: int
    fetched_at: str


CACHE_TTL_SECONDS = 60  # Real-time data considered fresh for 60 seconds


def fetch_stock_realtime(stock_code: str) -> StockQuote:
    """Fetch real-time quote for a single A-share stock via AkShare.

    Args:
        stock_code: e.g. "600519", "000001"
    Returns:
        StockQuote with current price, OHLCV, change_pct
    Raises:
        ValueError if stock_code is invalid or data unavailable
    """
    ...


def fetch_stock_realtime_batch(stock_codes: list[str]) -> list[StockQuote]:
    """Fetch real-time quotes for multiple stocks. Uses AkShare batch API where possible."""
    ...


def fetch_sector_list(sector_type: str = "industry") -> list[SectorQuote]:
    """Fetch all sector boards (industry or concept).

    Args:
        sector_type: "industry" or "concept"
    Returns:
        List of SectorQuote sorted by change_pct descending
    """
    ...


def fetch_sector_stocks(sector_name: str) -> list[StockQuote]:
    """Fetch all stocks within a given sector."""
    ...


def fetch_stock_history(
    stock_code: str,
    period: str = "daily",
    days: int = 60,
) -> pd.DataFrame:
    """Fetch historical OHLCV data for technical indicator computation.

    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    """
    ...


def compute_technical_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Compute MA, RSI, MACD, KDJ, Bollinger Bands from OHLCV DataFrame.

    Returns:
        dict with keys: ma5, ma10, ma20, ma60, rsi_14, macd, macd_signal,
        macd_hist, kdj_k, kdj_d, kdj_j, boll_upper, boll_middle, boll_lower
    """
    ...


def cache_stock_quotes(conn: sqlite3.Connection, quotes: list[StockQuote]) -> None:
    """Upsert stock quotes into cache table."""
    ...


def cache_sector_quotes(conn: sqlite3.Connection, quotes: list[SectorQuote]) -> None:
    """Upsert sector quotes into cache table."""
    ...


def get_cached_stock_quotes(conn: sqlite3.Connection, max_age_seconds: int = CACHE_TTL_SECONDS) -> list[dict]:
    """Read stock quotes from cache if fresh enough."""
    ...


def get_cached_sector_quotes(
    conn: sqlite3.Connection,
    sector_type: str = "industry",
    max_age_seconds: int = CACHE_TTL_SECONDS,
) -> list[dict]:
    """Read sector quotes from cache if fresh enough."""
    ...
```

### 3.3 New Service: `fund_service.py`

**File:** `backend/app/services/fund_service.py` (NEW)

**Responsibility:** Fetch fund NAV data, fund news, and aggregate sentiment context via AkShare.

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import akshare as ak


@dataclass(slots=True)
class FundNav:
    fund_code: str
    fund_name: str
    nav: float           # Unit NAV
    acc_nav: float       # Cumulative NAV
    nav_date: str        # Date of the NAV
    daily_return: float  # Daily return %
    fetched_at: str


@dataclass(slots=True)
class FundNews:
    title: str
    source: str
    publish_time: str
    url: str
    summary: str


def fetch_fund_nav(fund_code: str) -> FundNav:
    """Fetch latest NAV for a fund via AkShare.

    Args:
        fund_code: e.g. "000510", "008282"
    Returns:
        FundNav with current NAV, cumulative NAV, daily return
    Raises:
        ValueError if fund_code is invalid
    """
    ...


def fetch_fund_nav_batch(fund_codes: list[str]) -> list[FundNav]:
    """Fetch latest NAV for multiple funds."""
    ...


def fetch_fund_nav_history(fund_code: str, days: int = 30) -> list[dict]:
    """Fetch historical NAV for trend analysis.

    Returns:
        List of dicts with keys: date, nav, acc_nav, daily_return
    """
    ...


def fetch_fund_news(fund_code: str, limit: int = 10) -> list[FundNews]:
    """Fetch recent news related to a fund or its sector.

    Uses AkShare news APIs. Falls back to empty list if unavailable.
    """
    ...


def fetch_fund_basic_info(fund_code: str) -> dict[str, Any]:
    """Fetch fund metadata: name, type, manager, size, inception date."""
    ...


def cache_fund_nav(conn: sqlite3.Connection, navs: list[FundNav]) -> None:
    """Upsert fund NAV into cache table."""
    ...


def get_cached_fund_navs(conn: sqlite3.Connection, max_age_seconds: int = 300) -> list[dict]:
    """Read fund NAVs from cache. Fund NAV TTL is longer (5 min) since NAV updates once daily."""
    ...
```

### 3.4 New Service: `stock_analysis_service.py`

**File:** `backend/app/services/stock_analysis_service.py` (NEW)

**Responsibility:** Orchestrate stock sector AI analysis. Fetch data, build prompt, call cloud_llm, parse result.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Config
from app.services.cloud_llm import generate_with_cloud_llm, parse_json_object
from app.services import stock_service


@dataclass(slots=True)
class StockAnalysisResult:
    target_sector: str
    trend: str              # "bullish" | "bearish" | "neutral"
    momentum: str           # "strong" | "weak" | "sideways"
    sentiment_score: float  # -1.0 to 1.0
    confidence: float       # 0.0 to 1.0
    reasoning: str
    key_factors: list[str]
    risk_warnings: list[str]
    technical_summary: dict[str, Any]


async def analyze_stock_sector(
    config: Config,
    sector_name: str,
    sector_type: str = "industry",
) -> StockAnalysisResult:
    """Run full stock sector analysis pipeline.

    Steps:
    1. Fetch sector overview (top stocks, change_pct, turnover)
    2. Fetch top 5 stocks' real-time quotes + technical indicators
    3. Build structured prompt with market data + technical indicators
    4. Call cloud_llm for AI analysis
    5. Parse and validate structured result
    6. Log analysis to analysis_logs table
    7. Return StockAnalysisResult
    """
    ...


async def analyze_single_stock(
    config: Config,
    stock_code: str,
) -> StockAnalysisResult:
    """Run analysis for a single stock's sector context.

    Steps:
    1. Fetch stock real-time quote + history
    2. Compute technical indicators
    3. Identify which sector(s) the stock belongs to
    4. Build prompt with stock data + sector context
    5. Call cloud_llm
    6. Parse and return result
    """
    ...


def _build_stock_analysis_prompt(
    sector_name: str,
    sector_stocks: list[dict],
    technical_data: dict[str, Any],
    market_overview: str,
) -> str:
    """Build the analysis prompt for the LLM.

    Must produce a prompt that instructs the LLM to output strict JSON:
    {
        "trend": "bullish|bearish|neutral",
        "momentum": "strong|weak|sideways",
        "sentiment_score": float,
        "confidence": float,
        "reasoning": "string (<=200 chars)",
        "key_factors": ["string", ...],
        "risk_warnings": ["string", ...]
    }
    """
    ...
```

### 3.5 New Service: `fund_analysis_service.py`

**File:** `backend/app/services/fund_analysis_service.py` (NEW)

**Responsibility:** Orchestrate fund sector AI analysis. Combine NAV data + news + sentiment for comprehensive judgment.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Config
from app.services.cloud_llm import generate_with_cloud_llm, parse_json_object
from app.services import fund_service


@dataclass(slots=True)
class FundAnalysisResult:
    fund_code: str
    fund_name: str
    judgment: str            # "positive" | "negative" | "neutral"
    sentiment_score: float   # -1.0 to 1.0
    confidence: float        # 0.0 to 1.0
    reasoning: str
    nav_trend: str           # "rising" | "falling" | "stable"
    news_highlights: list[str]
    risk_factors: list[str]
    suggestion: str          # "hold" | "watch" | "caution"
    c_class_fee_warning: bool


async def analyze_fund_sector(
    config: Config,
    fund_code: str,
    custom_prompt: str | None = None,
) -> FundAnalysisResult:
    """Run full fund analysis pipeline.

    Steps:
    1. Fetch fund NAV (current + 30-day history)
    2. Fetch fund news
    3. Compute NAV trend (3d/7d/30d returns)
    4. Build structured prompt combining NAV + news + macro context
    5. Call cloud_llm with web_search enabled
    6. Parse and validate structured JSON result
    7. Check C-class fee warning if holding < 7 days
    8. Log analysis to analysis_logs table
    9. Return FundAnalysisResult
    """
    ...


def _build_fund_analysis_prompt(
    fund_code: str,
    fund_info: dict,
    nav_history: list[dict],
    news_items: list[dict],
    custom_prompt: str | None,
) -> str:
    """Build the fund analysis prompt.

    Must instruct LLM to output strict JSON:
    {
        "judgment": "positive|negative|neutral",
        "sentiment_score": float,
        "confidence": float,
        "reasoning": "string (<=200 chars)",
        "nav_trend": "rising|falling|stable",
        "news_highlights": ["string", ...],
        "risk_factors": ["string", ...],
        "suggestion": "hold|watch|caution"
    }
    """
    ...
```

### 3.6 Prompt Design: Stock Sector Analysis

**File:** `backend/app/core/prompts.py` (MODIFY -- add new prompts)

```python
STOCK_SECTOR_ANALYSIS_SYSTEM_PROMPT = """
You are a professional A-share market sector analysis engine acting as a read-only research analyst.

Your task: Analyze the provided sector data, stock quotes, and technical indicators to produce a structured sector assessment.

Rules:
1. Only use the provided data context. Do not fabricate prices, volumes, or indicators.
2. Distinguish facts from speculation. If evidence is insufficient, lower your confidence.
3. Pay attention to: sector rotation signals, volume-price divergence, momentum shifts, policy catalysts, and valuation pressure.
4. Do NOT produce trading recommendations (buy/sell/hold). You only provide analysis signals.
5. Do NOT attempt to override or evaluate any system risk rules.

Output format: You MUST output a single valid JSON object, no Markdown, no code fences, no extra text.
{
  "trend": "bullish|bearish|neutral",
  "momentum": "strong|weak|sideways",
  "sentiment_score": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<string, <=200 Chinese chars>",
  "key_factors": ["<string>", ...],
  "risk_warnings": ["<string>", ...]
}
""".strip()


FUND_ANALYSIS_SYSTEM_PROMPT = """
You are a professional fund research analysis engine acting as a read-only research analyst.

Your task: Analyze the provided fund NAV data, historical performance, and recent news to produce a comprehensive fund assessment.

Rules:
1. Only use the provided context. Do not fabricate NAV, returns, or news.
2. Distinguish confirmed facts from market rumors.
3. Pay attention to: NAV trend stability, drawdown risk, sector alignment, manager track record, and macro policy impact.
4. Do NOT produce trading recommendations. You only provide analysis signals.
5. Consider that C-class funds with < 7 days holding have redemption fees.

Output format: You MUST output a single valid JSON object, no Markdown, no code fences, no extra text.
{
  "judgment": "positive|negative|neutral",
  "sentiment_score": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<string, <=200 Chinese chars>",
  "nav_trend": "rising|falling|stable",
  "news_highlights": ["<string>", ...],
  "risk_factors": ["<string>", ...],
  "suggestion": "hold|watch|caution"
}
""".strip()
```

### 3.7 New Pydantic Models

**File:** `backend/app/models.py` (MODIFY -- add at the end)

```python
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


class SectorQuoteResponse(BaseModel):
    sector_code: str
    sector_name: str
    sector_type: str
    change_pct: float
    turnover_rate: float
    leading_stock: str
    rise_count: int
    fall_count: int


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
```

### 3.8 New API Endpoints

**File:** `backend/app/main.py` (MODIFY -- add new route registrations)

| Method | Path | Request Body | Response Model | Description |
|--------|------|-------------|----------------|-------------|
| `GET`  | `/api/stocks/realtime?codes=600519,000001` | Query: `codes` (comma-separated) | `list[StockQuoteResponse]` | Fetch real-time quotes for specified stocks |
| `GET`  | `/api/stocks/sectors?type=industry&limit=20` | Query: `type`, `limit` | `list[SectorQuoteResponse]` | Fetch sector board rankings |
| `POST` | `/api/stocks/analyze` | `StockAnalysisRequest` | `StockAnalysisResponse` | AI sector analysis |
| `GET`  | `/api/funds/nav?codes=000510,008282` | Query: `codes` (comma-separated) | `list[FundNavResponse]` | Fetch real-time fund NAV |
| `POST` | `/api/funds/analyze` | `FundAnalysisRequest` | `FundAnalysisResponse` | AI fund comprehensive judgment |
| `GET`  | `/api/market/overview` | -- | `MarketOverviewResponse` | Market overview dashboard data |

#### Endpoint Implementation Sketches

```python
# ---- Stock Endpoints ----

@app.get("/api/stocks/realtime", response_model=list[StockQuoteResponse])
async def get_stock_realtime(
    codes: str = Query(..., min_length=1, description="Comma-separated stock codes"),
    config: Config = Depends(get_config),
) -> list[StockQuoteResponse]:
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No valid stock codes provided")
    try:
        quotes = await run_in_threadpool(stock_service.fetch_stock_realtime_batch, code_list)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stock data fetch failed: {exc}") from exc
    return [StockQuoteResponse(**q.__dict__) for q in quotes]


@app.get("/api/stocks/sectors", response_model=list[SectorQuoteResponse])
async def get_stock_sectors(
    type: str = Query(default="industry", pattern="^(industry|concept)$"),
    limit: int = Query(default=20, ge=1, le=100),
    config: Config = Depends(get_config),
) -> list[SectorQuoteResponse]:
    try:
        sectors = await run_in_threadpool(stock_service.fetch_sector_list, type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sector data fetch failed: {exc}") from exc
    return [SectorQuoteResponse(**s.__dict__) for s in sectors[:limit]]


@app.post("/api/stocks/analyze", response_model=StockAnalysisResponse)
async def post_stock_analyze(
    request: StockAnalysisRequest,
    config: Config = Depends(get_config),
) -> StockAnalysisResponse:
    try:
        if request.sector_name:
            result = await stock_analysis_service.analyze_stock_sector(
                config, request.sector_name, request.sector_type
            )
        elif request.stock_code:
            result = await stock_analysis_service.analyze_single_stock(config, request.stock_code)
        else:
            raise HTTPException(status_code=400, detail="Provide either sector_name or stock_code")
    except CloudLLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return StockAnalysisResponse(**result.__dict__)


# ---- Fund Endpoints ----

@app.get("/api/funds/nav", response_model=list[FundNavResponse])
async def get_fund_nav(
    codes: str = Query(..., min_length=1, description="Comma-separated fund codes"),
    config: Config = Depends(get_config),
) -> list[FundNavResponse]:
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No valid fund codes provided")
    try:
        navs = await run_in_threadpool(fund_service.fetch_fund_nav_batch, code_list)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fund NAV fetch failed: {exc}") from exc
    return [FundNavResponse(**n.__dict__) for n in navs]


@app.post("/api/funds/analyze", response_model=FundAnalysisResponse)
async def post_fund_analyze(
    request: FundAnalysisRequest,
    config: Config = Depends(get_config),
) -> FundAnalysisResponse:
    try:
        result = await fund_analysis_service.analyze_fund_sector(
            config, request.fund_code, request.custom_prompt
        )
    except CloudLLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return FundAnalysisResponse(**result.__dict__)


# ---- Market Overview Endpoint ----

@app.get("/api/market/overview", response_model=MarketOverviewResponse)
async def get_market_overview(
    config: Config = Depends(get_config),
) -> MarketOverviewResponse:
    """Aggregate market overview: VIX + major indices + top/bottom sectors."""
    from app.services.market_data import get_market_snapshot
    snapshot = get_market_snapshot(config)
    try:
        # Fetch SSE Index, SZSE Index, CSI 300, CSI 500
        major = await run_in_threadpool(
            stock_service.fetch_stock_realtime_batch,
            ["000001", "399001", "000300", "000905"],
        )
        sectors = await run_in_threadpool(stock_service.fetch_sector_list, "industry")
    except Exception:
        major, sectors = [], []
    top = sorted(sectors, key=lambda s: s.change_pct, reverse=True)[:5]
    bottom = sorted(sectors, key=lambda s: s.change_pct)[:5]
    return MarketOverviewResponse(
        vix=snapshot.vix,
        major_indices=[StockQuoteResponse(**m.__dict__) for m in major],
        top_sectors=[SectorQuoteResponse(**s.__dict__) for s in top],
        bottom_sectors=[SectorQuoteResponse(**s.__dict__) for s in bottom],
        fetched_at=snapshot.as_of.isoformat(),
    )
```

---

## 4. Frontend Component Architecture

### 4.1 Navigation Structure

Current tabs: `dashboard` | `research`

New tabs:

```
dashboard       -- existing (Status, Settings, Trigger, Lots, Logs)
stock-sector    -- NEW: real-time stock quotes + sector rankings + AI analysis
fund-sector     -- NEW: fund NAV + news + AI analysis (upgrade existing ResearchDashboard)
market-overview -- NEW: aggregated market view
```

### 4.2 File Structure

```
frontend/src/
    main.jsx                           # NO CHANGE
    App.jsx                            # MODIFY -- add new tabs + route logic
    styles.css                         # MODIFY -- add new component styles
    api/
        client.js                      # MODIFY -- add new API functions
    views/
        ResearchDashboard.jsx          # KEEP (becomes FundSector view)
        StockSector.jsx                # NEW
        FundSector.jsx                 # NEW (replaces ResearchDashboard usage)
        MarketOverview.jsx             # NEW
    components/
        StockQuoteCard.jsx             # NEW
        SectorRankingTable.jsx         # NEW
        TechnicalIndicatorPanel.jsx    # NEW
        FundNavCard.jsx                # NEW
        FundAnalysisResult.jsx         # NEW
        MarketOverviewCards.jsx        # NEW
        AnalysisLoadingState.jsx       # NEW (shared loading animation)
        SentimentMeter.jsx             # EXTRACT from ResearchDashboard.jsx (shared)
```

### 4.3 API Client Additions

**File:** `frontend/src/api/client.js` (MODIFY -- add at the end)

```javascript
// ---- Stock Sector API ----

export function getStockRealtime(codes) {
  const encoded = encodeURIComponent(codes.join(','));
  return request(`/api/stocks/realtime?codes=${encoded}`);
}

export function getStockSectors(type = 'industry', limit = 20) {
  return request(`/api/stocks/sectors?type=${encodeURIComponent(type)}&limit=${limit}`);
}

export function analyzeStockSector({ sectorName, stockCode, sectorType = 'industry' }) {
  const body = {};
  if (sectorName) body.sector_name = sectorName;
  if (stockCode) body.stock_code = stockCode;
  body.sector_type = sectorType;
  return request('/api/stocks/analyze', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ---- Fund Sector API ----

export function getFundNav(codes) {
  const encoded = encodeURIComponent(codes.join(','));
  return request(`/api/funds/nav?codes=${encoded}`);
}

export function analyzeFundSector(fundCode, customPrompt = '') {
  const body = { fund_code: fundCode };
  if (customPrompt?.trim()) {
    body.custom_prompt = customPrompt.trim();
  }
  return request('/api/funds/analyze', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ---- Market Overview API ----

export function getMarketOverview() {
  return request('/api/market/overview');
}
```

### 4.4 App.jsx Tab Changes

**File:** `frontend/src/App.jsx` (MODIFY)

```javascript
const NAV_TABS = [
  { key: 'dashboard', label: '概览面板' },
  { key: 'stock-sector', label: '📈 股票板块' },
  { key: 'fund-sector', label: '📊 基金研判' },
  { key: 'market-overview', label: '🌐 市场总览' },
];
```

### 4.5 Component Designs

#### `StockSector.jsx`

**Layout:**
```
+--------------------------------------------------+
| Sector Type Selector: [行业板块] [概念板块]       |
+--------------------------------------------------+
| Sector Ranking Table (top 20)                     |
| +---------+------+------+----------+----------+   |
| | 板块名称 | 涨跌幅 | 换手率 | 领涨股    | 涨/跌家数 |   |
| +---------+------+------+----------+----------+   |
| | ...      | ...  | ...  | ...      | ...      |   |
+--------------------------------------------------+
| AI Sector Analysis Panel                          |
| [Select a sector from table above to analyze]     |
| OR: [Enter stock code: _______] [分析]            |
|                                                   |
| Result:                                           |
|  - Trend: bullish/bearish/neutral                 |
|  - Momentum: strong/weak/sideways                 |
|  - Sentiment Meter (bar visualization)            |
|  - Key Factors (list)                             |
|  - Risk Warnings (list)                           |
|  - Technical Summary (table)                      |
+--------------------------------------------------+
```

**State management:**
```javascript
const [sectorType, setSectorType] = useState('industry');
const [sectors, setSectors] = useState([]);
const [sectorsLoading, setSectorsLoading] = useState(false);
const [selectedSector, setSelectedSector] = useState(null);
const [stockInput, setStockInput] = useState('');
const [analysis, setAnalysis] = useState(null);
const [analyzing, setAnalyzing] = useState(false);
const [error, setError] = useState('');
```

#### `FundSector.jsx` (upgraded from ResearchDashboard.jsx)

**Layout:**
```
+--------------------------------------------------+
| Fund Code Input: [______] [查询净值] [AI研判]     |
+--------------------------------------------------+
| Saved Watchlist (from config assets)              |
| +---------+------+------+--------+---------+      |
| | 基金代码 | 基金名称 | 最新净值 | 日涨跌   | 累计净值  |      |
| +---------+------+------+--------+---------+      |
+--------------------------------------------------+
| Fund Analysis Panel (after AI analysis)           |
|  - Judgment: positive/negative/neutral            |
|  - Sentiment Meter                                |
|  - NAV Trend: rising/falling/stable               |
|  - News Highlights (list)                         |
|  - Risk Factors (list)                            |
|  - Suggestion: hold/watch/caution                 |
|  - C-class fee warning (if applicable)            |
+--------------------------------------------------+
```

#### `MarketOverview.jsx`

**Layout:**
```
+--------------------------------------------------+
| VIX: 18.5 | SSE: 3,200 | SZSE: 10,500           |
| CSI 300: 3,800 | CSI 500: 5,600                   |
+--------------------------------------------------+
| Top 5 Sectors (green cards)                       |
| +----------+--------+                             |
| | 半导体    | +3.2%  |                             |
| | AI       | +2.8%  |                             |
| +----------+--------+                             |
+--------------------------------------------------+
| Bottom 5 Sectors (red cards)                      |
+--------------------------------------------------+
| Last Updated: 2026-05-25 14:30:00                 |
+--------------------------------------------------+
```

### 4.6 Shared Components

#### `SentimentMeter.jsx` (extracted from ResearchDashboard.jsx)

Reusable across StockSector and FundSector. Takes `score` (-1.0 to 1.0) and renders a horizontal bar with color gradient.

#### `AnalysisLoadingState.jsx`

Shared loading animation for AI analysis calls. Takes `steps` array and `currentStep` index.

---

## 5. Data Flow: Stock Sector Analysis

```
User clicks sector row OR enters stock code
    |
    v
Frontend: POST /api/stocks/analyze
    |
    v
Backend: stock_analysis_service.analyze_stock_sector()
    |
    +-- stock_service.fetch_sector_stocks(sector_name)
    |       |
    |       +-- AkShare: ak.stock_board_industry_cons_em()
    |
    +-- stock_service.fetch_stock_history(top_stock, days=60)
    |       |
    |       +-- AkShare: ak.stock_zh_a_hist()
    |
    +-- stock_service.compute_technical_indicators(df)
    |       |
    |       +-- pandas_ta: RSI, MACD, KDJ, Bollinger, MA
    |
    +-- _build_stock_analysis_prompt(sector_name, stocks, technicals, market)
    |       |
    |       +-- Includes STOCK_SECTOR_ANALYSIS_SYSTEM_PROMPT
    |
    +-- cloud_llm.generate_with_cloud_llm(config, prompt)
    |       |
    |       +-- MIMO-V2.5-PRO via OpenAI-compatible API
    |
    +-- Parse JSON response -> StockAnalysisResult
    |
    +-- Log to analysis_logs table
    |
    +-- Return StockAnalysisResponse
```

## 6. Data Flow: Fund Sector Analysis

```
User enters fund code OR clicks from watchlist
    |
    v
Frontend: POST /api/funds/analyze
    |
    v
Backend: fund_analysis_service.analyze_fund_sector()
    |
    +-- fund_service.fetch_fund_nav(fund_code)
    |       |
    |       +-- AkShare: ak.fund_open_fund_info_em()
    |
    +-- fund_service.fetch_fund_nav_history(fund_code, days=30)
    |       |
    |       +-- AkShare: ak.fund_open_fund_daily_em()
    |
    +-- fund_service.fetch_fund_news(fund_code)
    |       |
    |       +-- AkShare: ak.stock_news_em() or similar
    |
    +-- _build_fund_analysis_prompt(fund_info, nav_history, news, custom_prompt)
    |       |
    |       +-- Includes FUND_ANALYSIS_SYSTEM_PROMPT
    |
    +-- cloud_llm.generate_with_cloud_llm(config, prompt)
    |       |
    |       +-- MIMO-V2.5-PRO with web_search enabled
    |
    +-- Parse JSON response -> FundAnalysisResult
    |
    +-- Check C-class fee warning (holding_days < 7)
    |
    +-- Log to analysis_logs table
    |
    +-- Return FundAnalysisResponse
```

---

## 7. Implementation Priority and Dependencies

### Phase 1: Data Layer (pythonengineer) -- Estimated: 2-3 days

| Task | File | Dependencies | Complexity |
|------|------|-------------|------------|
| Install akshare, pandas, pandas_ta | requirements.txt | None | Low |
| Add new DB schemas | database.py | None | Low |
| Implement stock_service.py | stock_service.py | akshare installed | Medium |
| Implement fund_service.py | fund_service.py | akshare installed | Medium |
| Test data fetching independently | tests/test_stock_service.py | stock_service.py | Medium |
| Test fund data fetching | tests/test_fund_service.py | fund_service.py | Medium |

### Phase 2: AI Analysis Services (pythonengineer) -- Estimated: 2 days

| Task | File | Dependencies | Complexity |
|------|------|-------------|------------|
| Add new prompts | core/prompts.py | None | Low |
| Implement stock_analysis_service.py | stock_analysis_service.py | stock_service.py, prompts.py | Medium |
| Implement fund_analysis_service.py | fund_analysis_service.py | fund_service.py, prompts.py | Medium |
| Add new models | models.py | None | Low |
| Test analysis services | tests/test_stock_analysis.py | analysis services | Medium |

### Phase 3: API Endpoints (pythonengineer) -- Estimated: 1-2 days

| Task | File | Dependencies | Complexity |
|------|------|-------------|------------|
| Add stock endpoints | main.py | stock services | Low |
| Add fund endpoints | main.py | fund services | Low |
| Add market overview endpoint | main.py | stock_service | Low |
| API integration tests | tests/test_main_api.py | endpoints | Medium |

### Phase 4: Frontend (frontexpert) -- Estimated: 3-4 days

| Task | File | Dependencies | Complexity |
|------|------|-------------|------------|
| Add API client functions | api/client.js | Backend endpoints live | Low |
| Create StockSector.jsx | views/StockSector.jsx | API client | Medium |
| Create FundSector.jsx | views/FundSector.jsx | API client | Medium |
| Create MarketOverview.jsx | views/MarketOverview.jsx | API client | Low |
| Extract shared components | components/* | None | Low |
| Update App.jsx tabs | App.jsx | New views | Low |
| Add new styles | styles.css | New components | Medium |

### Dependency Graph

```
Phase 1 (Data Layer)
    |
    v
Phase 2 (AI Services) ----> Phase 3 (API Endpoints)
                                    |
                                    v
                             Phase 4 (Frontend)
```

Phases 1 and the prompt part of Phase 2 can start immediately in parallel.
Phase 3 depends on Phase 2 services being functional.
Phase 4 depends on Phase 3 endpoints being live.

---

## 8. Configuration Additions

**File:** `backend/config.yaml` (MODIFY -- add data source section)

```yaml
# New section for data source configuration
data_sources:
  akshare:
    enabled: true
    stock_cache_ttl_seconds: 60
    sector_cache_ttl_seconds: 60
    fund_cache_ttl_seconds: 300
    request_timeout_seconds: 15
```

**File:** `backend/app/config.py` (MODIFY -- add DataSourceConfig)

```python
class AkShareConfig(BaseModel):
    enabled: bool = True
    stock_cache_ttl_seconds: int = 60
    sector_cache_ttl_seconds: int = 60
    fund_cache_ttl_seconds: int = 300
    request_timeout_seconds: int = 15


class DataSourceConfig(BaseModel):
    akshare: AkShareConfig = Field(default_factory=AkShareConfig)


class Config(BaseModel):
    # ... existing fields ...
    data_sources: DataSourceConfig = Field(default_factory=DataSourceConfig)
```

---

## 9. Verification Checklist

### 9.1 Self-Check: State Key Safety

The existing LangGraph graph (graph.py, nodes.py) is NOT modified. The new stock/fund analysis services are standalone, not wired into the existing StateGraph. This means:
- No risk of breaking the existing paper trading pipeline.
- No new GraphState keys needed.
- The new analysis endpoints are purely additive REST endpoints.

### 9.2 Termination and Error Handling

- All new `async` functions use try/except and return HTTP 502 on data source failure.
- AkShare calls are wrapped in `run_in_threadpool` (AkShare is synchronous).
- LLM failures are caught and return HTTP 502 (same pattern as existing `/api/research/analyze`).
- Cache TTL prevents stale data; cache miss triggers fresh fetch.

### 9.3 Testing Strategy

| Test Target | What to Test |
|-------------|-------------|
| stock_service.py | AkShare data parsing, cache upsert/read, technical indicator computation |
| fund_service.py | AkShare fund NAV parsing, news fetching, cache behavior |
| stock_analysis_service.py | Prompt construction, JSON parsing, LLM error handling |
| fund_analysis_service.py | Prompt construction, C-class fee warning logic |
| API endpoints | Request validation, error codes, response schema compliance |

### 9.4 Security Check

- Paper-only constraint: No real trading APIs called. New services only fetch market data and call LLM.
- API key: Only the existing cloud_llm.py key is used. No new secrets.
- Input validation: All stock/fund codes validated before passing to AkShare.
- Rate limiting: Not implemented in Phase 1 (local-only use). Consider for cloud deployment.

---

## 10. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| AkShare API rate limiting | Cache layer with TTL; batch requests where possible |
| AkShare data unavailable for some stocks | Graceful fallback with error message; mock data option for development |
| LLM output not valid JSON | Same retry-with-fallback pattern as existing validate_llm_json node |
| Technical indicator computation heavy | Compute only for top-5 stocks per sector, not all stocks |
| Large response payloads | Limit sector lists to top 20; limit news to 10 items |

---

## 11. Summary of All File Changes

### New Files (8)

| File | Owner |
|------|-------|
| `backend/app/services/stock_service.py` | pythonengineer |
| `backend/app/services/fund_service.py` | pythonengineer |
| `backend/app/services/stock_analysis_service.py` | pythonengineer |
| `backend/app/services/fund_analysis_service.py` | pythonengineer |
| `backend/tests/test_stock_service.py` | pythonengineer |
| `backend/tests/test_fund_service.py` | pythonengineer |
| `frontend/src/views/StockSector.jsx` | frontexpert |
| `frontend/src/views/MarketOverview.jsx` | frontexpert |

### Modified Files (9)

| File | Change Summary |
|------|---------------|
| `backend/app/config.py` | Add DataSourceConfig, AkShareConfig |
| `backend/app/models.py` | Add Stock/Sector/Fund/Analysis Pydantic models |
| `backend/app/main.py` | Add 6 new API endpoints |
| `backend/app/services/database.py` | Add 4 new table schemas in init_db |
| `backend/app/core/prompts.py` | Add STOCK_SECTOR and FUND_ANALYSIS prompts |
| `backend/requirements.txt` | Add akshare, pandas, pandas_ta |
| `backend/config.yaml` | Add data_sources section |
| `frontend/src/App.jsx` | Add 2 new tabs, import new views |
| `frontend/src/api/client.js` | Add 5 new API functions |

### Unchanged Files

All existing graph logic, paper executor, positions, FIFO, C-class protection, retriever, LLM settings remain untouched. The upgrade is purely additive.

---

# Architecture Upgrade V2.1 -- Optimization Phases

**Date:** 2026-05-25
**Scope:** i18n, User Watchlist, Data Source Reliability, UX Optimization
**Prerequisite:** V2 Phase 1-6 completed (90 tests, 48 modules, 5 tabs)

---

## 12. Internationalization (i18n) Architecture

### 12.1 Technology Selection

| Criterion | react-i18next | react-intl (FormatJS) | Custom solution |
|-----------|--------------|----------------------|-----------------|
| React integration | Hook-based `useTranslation` | Provider + `useIntl` | Manual |
| Namespace support | Built-in | Via explicit IDs | Manual |
| Lazy loading | Built-in | Manual | Manual |
| Plurals/interpolation | Built-in | Built-in | Manual |
| Bundle size | ~15KB gzipped | ~40KB gzipped | Minimal |
| Community | 10K+ stars | 14K+ stars | N/A |

**Decision:** Use `react-i18next` -- lighter weight, hook-based API fits our functional component style, built-in namespace support for tab-scoped language keys.

### 12.2 Language Key Structure

Flat namespace per tab/feature scope. Keys use dot notation: `{scope}.{component}.{element}`.

```json
// zh.json -- Chinese language pack (default)
{
  "common": {
    "loading": "加载中...",
    "error": "出错了",
    "retry": "重试",
    "refresh": "刷新",
    "noData": "暂无数据",
    "analysis": "分析",
    "analyzing": "分析中...",
    "save": "保存",
    "cancel": "取消",
    "delete": "删除",
    "add": "添加",
    "search": "搜索",
    "export": "导出"
  },
  "banner": {
    "paperOnly": "仅限模拟交易",
    "description": "本客户端仅用于 Paper 模式观察和手动触发运行，不涉及真实交易、认证或券商执行。"
  },
  "nav": {
    "dashboard": "概览面板",
    "research": "投研大厅",
    "stockSector": "股票板块",
    "fundSector": "基金研判",
    "marketOverview": "市场总览"
  },
  "dashboard": {
    "status": {
      "title": "系统状态",
      "description": "后端和运行时可见性",
      "backend": "后端",
      "database": "数据库",
      "langgraph": "LangGraph",
      "chromadb": "ChromaDB",
      "llmRuntime": "LLM 运行时",
      "refreshAll": "刷新全部",
      "lastRun": "最近运行摘要",
      "runId": "运行 ID",
      "asset": "资产",
      "route": "路由",
      "finalAction": "最终操作"
    },
    "settings": {
      "title": "设置",
      "description": "管理 LLM 请求设置。已保存的 API 密钥在 UI 中保持遮罩。",
      "saveSettings": "保存设置",
      "testing": "测试中...",
      "testLlm": "测试 LLM 连接"
    },
    "trigger": {
      "title": "触发运行",
      "description": "手动触发一次 Paper-only 管线运行。",
      "assetCode": "资产代码",
      "triggerRun": "触发运行"
    },
    "lots": {
      "title": "持仓批次",
      "openLots": "当前持仓",
      "id": "ID",
      "asset": "资产",
      "buyDate": "买入日期",
      "shares": "份额",
      "costPrice": "成本价",
      "holdingDays": "持有天数",
      "status": "状态"
    },
    "logs": {
      "title": "执行日志",
      "recentLogs": "最近执行日志"
    }
  },
  "stockSector": {
    "title": "股票板块分析",
    "subtitle": "实时板块行情排名 + AI 深度研判",
    "industry": "行业板块",
    "concept": "概念板块",
    "sectorName": "板块名称",
    "changePct": "涨跌幅",
    "turnoverRate": "换手率",
    "leadingStock": "领涨股",
    "riseFall": "涨/跌家数",
    "analyze": "分析",
    "aiAnalysis": "AI 板块研判",
    "inputStockCode": "输入股票代码，如 600519",
    "orInputStockCode": "或输入股票代码进行分析",
    "selectOrInput": "请从上方板块列表选择一个板块，或输入股票代码开始 AI 分析",
    "trend": { "bullish": "看涨", "bearish": "看跌", "neutral": "中性" },
    "momentum": { "strong": "强势", "weak": "弱势", "sideways": "震荡" },
    "sentiment": "情绪指标",
    "reasoning": "分析逻辑",
    "keyFactors": "关键因素",
    "riskWarnings": "风险提示",
    "technicalSummary": "技术指标摘要",
    "steps": ["获取板块数据", "计算技术指标", "AI 深度分析"]
  },
  "fundSector": {
    "title": "基金研判",
    "subtitle": "基金净值查询 + AI 综合深度研判",
    "holdings": "持仓概览",
    "fundCodeQuery": "基金代码查询",
    "inputFundCode": "输入基金代码，如 000510",
    "queryNav": "查询净值",
    "aiJudgment": "AI 研判",
    "customPrompt": "自定义 Prompt",
    "customPromptPlaceholder": "留空则使用默认基金研判 Prompt",
    "selectOrInput": "请从左侧选择持仓基金或输入基金代码开始 AI 研判",
    "fundCode": "基金代码",
    "fundName": "基金名称",
    "nav": "最新净值",
    "dailyReturn": "日涨跌",
    "accNav": "累计净值",
    "navDate": "净值日期",
    "holdingDays": "天",
    "holdingShares": "持有份额",
    "pnlRatio": "盈亏比例",
    "judgment": { "positive": "积极", "negative": "消极", "neutral": "中性" },
    "suggestion": { "hold": "持有", "watch": "观望", "caution": "谨慎" },
    "navTrend": { "rising": "上升", "falling": "下降", "stable": "稳定" },
    "newsHighlights": "新闻要点",
    "riskFactors": "风险因素",
    "feeWarning": "7天内赎回费风险: 该基金持有不足7天，赎回将产生手续费。建议持有超过7天后再操作。",
    "suggestionLabel": "操作建议",
    "steps": ["获取基金净值", "检索新闻资讯", "AI 综合研判"]
  },
  "marketOverview": {
    "title": "市场总览",
    "subtitle": "VIX + 主要指数 + 板块涨跌排行",
    "vixLabel": "VIX 恐慌指数",
    "vixLow": "低波动",
    "vixNormal": "正常区间",
    "vixHigh": "高波动",
    "topSectors": "涨幅前5板块",
    "bottomSectors": "跌幅前5板块",
    "updatedAt": "数据更新时间"
  },
  "history": {
    "title": "分析历史",
    "all": "全部",
    "stockSector": "股票板块",
    "fundSector": "基金研判",
    "target": "分析目标",
    "type": "类型",
    "time": "时间",
    "view": "查看"
  },
  "watchlist": {
    "title": "自选列表",
    "addStock": "添加自选股票",
    "addFund": "添加自选基金",
    "inputCode": "输入代码",
    "confirmDelete": "确认删除此自选?",
    "empty": "暂无自选，点击上方按钮添加"
  }
}
```

```json
// en.json -- English language pack
{
  "common": {
    "loading": "Loading...",
    "error": "Error occurred",
    "retry": "Retry",
    "refresh": "Refresh",
    "noData": "No data available",
    "analysis": "Analyze",
    "analyzing": "Analyzing...",
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "add": "Add",
    "search": "Search",
    "export": "Export"
  },
  "banner": {
    "paperOnly": "PAPER / DRY-RUN ONLY",
    "description": "This client is for paper-mode observation and manual dry-run triggering only. No live trading, auth, or brokerage execution is exposed here."
  },
  "nav": {
    "dashboard": "Dashboard",
    "research": "Research",
    "stockSector": "Stock Sector",
    "fundSector": "Fund Sector",
    "marketOverview": "Market Overview"
  },
  "...": "(full English translations following same key structure)"
}
```

### 12.3 i18n Initialization

**File:** `frontend/src/i18n/index.js` (NEW)

```javascript
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import zh from './locales/zh.json';
import en from './locales/en.json';

const resources = {
  zh: { translation: zh },
  en: { translation: en },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'zh',
    lng: localStorage.getItem('language') || 'zh',
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'language',
      caches: ['localStorage'],
    },
  });

export default i18n;
```

### 12.4 Language Switcher Component

**File:** `frontend/src/components/LanguageSwitcher.jsx` (NEW)

```javascript
import { useTranslation } from 'react-i18next';

const LANGUAGES = [
  { code: 'zh', label: '中文', flag: 'CN' },
  { code: 'en', label: 'English', flag: 'EN' },
];

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();

  function handleChange(lang) {
    i18n.changeLanguage(lang);
    localStorage.setItem('language', lang);
  }

  return (
    <div className="language-switcher" role="group" aria-label="Language">
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          type="button"
          className={`language-switcher__btn ${
            i18n.language === lang.code ? 'language-switcher__btn--active' : ''
          }`}
          onClick={() => handleChange(lang.code)}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}
```

### 12.5 Migration Pattern

Each component migrates from hardcoded strings to `useTranslation()`:

```javascript
// BEFORE (hardcoded Chinese)
<h2>股票板块分析</h2>
<p>实时板块行情排名 + AI 深度研判</p>

// AFTER (i18n)
import { useTranslation } from 'react-i18next';

function StockSector() {
  const { t } = useTranslation();
  return (
    <>
      <h2>{t('stockSector.title')}</h2>
      <p>{t('stockSector.subtitle')}</p>
    </>
  );
}
```

---

## 13. User Watchlist Management System

### 13.1 Database Schema

**File:** `backend/app/services/database.py` (MODIFY -- add new schema)

```sql
CREATE TABLE IF NOT EXISTS user_watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL CHECK (item_type IN ('stock', 'fund')),
    code TEXT NOT NULL,
    name TEXT DEFAULT '',
    added_at TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    UNIQUE(item_type, code)
);
```

### 13.2 Backend Service

**File:** `backend/app/services/watchlist_service.py` (NEW)

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class WatchlistItem:
    id: int
    item_type: str      # "stock" | "fund"
    code: str
    name: str
    added_at: str
    sort_order: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_to_watchlist(
    conn: sqlite3.Connection,
    item_type: str,
    code: str,
    name: str = "",
) -> WatchlistItem:
    """Add a stock or fund to the watchlist. Returns existing item if duplicate."""
    code = code.strip()
    if not code:
        raise ValueError("code must not be empty")
    if item_type not in ("stock", "fund"):
        raise ValueError(f"item_type must be 'stock' or 'fund', got '{item_type}'")

    now = _now_iso()
    # Get max sort_order
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM user_watchlist WHERE item_type = ?",
        (item_type,),
    ).fetchone()
    next_order = row[0] if row else 1

    conn.execute(
        """
        INSERT INTO user_watchlist (item_type, code, name, added_at, sort_order)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(item_type, code) DO UPDATE SET name = excluded.name
        """,
        (item_type, code, name, now, next_order),
    )
    conn.commit()

    # Return the item
    row = conn.execute(
        "SELECT * FROM user_watchlist WHERE item_type = ? AND code = ?",
        (item_type, code),
    ).fetchone()
    return WatchlistItem(**dict(row))


def remove_from_watchlist(conn: sqlite3.Connection, item_id: int) -> bool:
    """Remove an item from the watchlist by ID."""
    cursor = conn.execute("DELETE FROM user_watchlist WHERE id = ?", (item_id,))
    conn.commit()
    return cursor.rowcount > 0


def list_watchlist(
    conn: sqlite3.Connection,
    item_type: str | None = None,
) -> list[WatchlistItem]:
    """List all watchlist items, optionally filtered by type."""
    if item_type and item_type != "all":
        rows = conn.execute(
            "SELECT * FROM user_watchlist WHERE item_type = ? ORDER BY sort_order, added_at",
            (item_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM user_watchlist ORDER BY item_type, sort_order, added_at"
        ).fetchall()
    return [WatchlistItem(**dict(r)) for r in rows]


def reorder_watchlist(
    conn: sqlite3.Connection,
    items: list[dict[str, int]],
) -> None:
    """Batch update sort orders. items: [{id: int, sort_order: int}, ...]"""
    for item in items:
        conn.execute(
            "UPDATE user_watchlist SET sort_order = ? WHERE id = ?",
            (item["sort_order"], item["id"]),
        )
    conn.commit()
```

### 13.3 API Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| `GET` | `/api/watchlist?type=all` | Query: `type` (all/stock/fund) | `list[WatchlistItemResponse]` | Get watchlist |
| `POST` | `/api/watchlist` | `{item_type, code, name?}` | `WatchlistItemResponse` | Add item |
| `DELETE` | `/api/watchlist/{id}` | -- | `{ok: true}` | Remove item |
| `PUT` | `/api/watchlist/reorder` | `{items: [{id, sort_order}]}` | `{ok: true}` | Reorder items |

### 13.4 Frontend Integration

The watchlist sidebar appears in StockSector and FundSector views:

```
+--------------------------------------------------+
| [股票板块] [概念板块] [查看历史]  [自选管理]        |
+--------------------------------------------------+
| Sidebar (left):          | Main (right):          |
| +------------------+     | Sector Ranking Table    |
| | 自选股票 (3)      |     | or AI Analysis Panel    |
| | 600519 贵州茅台   |     |                         |
| | 000001 平安银行   |     |                         |
| | 300750 宁德时代   |     |                         |
| | [+ 添加自选]      |     |                         |
| +------------------+     |                         |
+--------------------------------------------------+
```

---

## 14. Data Source Reliability Architecture

### 14.1 Problem Statement

AkShare's `stock_zh_a_spot_em()` fails in environments with HTTP proxies (common in corporate/China networks). The function uses `requests` internally but does not respect `HTTP_PROXY`/`HTTPS_PROXY` environment variables consistently. Fund NAV APIs (`fund_open_fund_info_em`) work because they use different endpoints.

### 14.2 Adapter Pattern Design

```
                      FallbackChain
                           |
           +---------------+----------------+
           |               |                |
    AkShareAdapter   EastMoneyAdapter   MockAdapter
    (priority=1)     (priority=2)       (priority=99)
           |               |
    [akshare lib]    [requests + parse]
```

**Base Interface:**

```python
# backend/app/services/data_sources/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DataSourceResult:
    data: Any
    source: str          # adapter name
    is_mock: bool = False
    latency_ms: float = 0.0
    error: str | None = None


class DataSourceAdapter(ABC):
    """Abstract base for all data source adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique adapter name for logging/monitoring."""
        ...

    @property
    @abstractmethod
    def priority(self) -> int:
        """Lower number = higher priority. Fallback chain tries in order."""
        ...

    @abstractmethod
    def fetch_stock_realtime(self, stock_code: str) -> DataSourceResult:
        ...

    @abstractmethod
    def fetch_stock_batch(self, stock_codes: list[str]) -> DataSourceResult:
        ...

    @abstractmethod
    def fetch_sector_list(self, sector_type: str) -> DataSourceResult:
        ...

    @abstractmethod
    def fetch_fund_nav(self, fund_code: str) -> DataSourceResult:
        ...

    def is_available(self) -> bool:
        """Health check. Override to implement connectivity test."""
        return True
```

**Fallback Chain:**

```python
# backend/app/services/data_sources/fallback_chain.py

import logging
import time
from typing import Callable, Any

from .base import DataSourceAdapter, DataSourceResult

logger = logging.getLogger(__name__)


class FallbackChain:
    """Tries adapters in priority order, falling back on failure."""

    def __init__(self, adapters: list[DataSourceAdapter]):
        self.adapters = sorted(adapters, key=lambda a: a.priority)
        self._stats: dict[str, dict] = {}

    def execute(self, method_name: str, *args, **kwargs) -> DataSourceResult:
        """Execute a method across adapters with fallback.

        Args:
            method_name: e.g. "fetch_stock_realtime"
            *args, **kwargs: arguments to pass to the method
        Returns:
            DataSourceResult from the first successful adapter
        """
        last_error = None
        for adapter in self.adapters:
            method = getattr(adapter, method_name, None)
            if method is None:
                continue
            try:
                start = time.monotonic()
                result = method(*args, **kwargs)
                elapsed = (time.monotonic() - start) * 1000
                result.latency_ms = elapsed
                self._record_success(adapter.name, method_name, elapsed)
                return result
            except Exception as exc:
                last_error = exc
                self._record_failure(adapter.name, method_name, str(exc))
                logger.warning(
                    "Adapter %s.%s failed: %s, trying next",
                    adapter.name, method_name, exc,
                )
                continue

        # All adapters failed
        return DataSourceResult(
            data=None,
            source="none",
            is_mock=True,
            error=f"All data sources failed. Last error: {last_error}",
        )

    def get_stats(self) -> dict[str, dict]:
        """Return success/failure stats per adapter per method."""
        return self._stats

    def _record_success(self, adapter: str, method: str, latency: float):
        key = f"{adapter}.{method}"
        if key not in self._stats:
            self._stats[key] = {"success": 0, "failure": 0, "avg_latency_ms": 0}
        s = self._stats[key]
        s["success"] += 1
        n = s["success"]
        s["avg_latency_ms"] = (s["avg_latency_ms"] * (n - 1) + latency) / n

    def _record_failure(self, adapter: str, method: str, error: str):
        key = f"{adapter}.{method}"
        if key not in self._stats:
            self._stats[key] = {"success": 0, "failure": 0, "avg_latency_ms": 0, "last_error": ""}
        self._stats[key]["failure"] += 1
        self._stats[key]["last_error"] = error
```

### 14.3 AkShare Adapter with Proxy Support

```python
# backend/app/services/data_sources/akshare_adapter.py

import os
import akshare as ak
from .base import DataSourceAdapter, DataSourceResult


class AkShareAdapter(DataSourceAdapter):
    """AkShare data source with proxy support."""

    @property
    def name(self) -> str:
        return "akshare"

    @property
    def priority(self) -> int:
        return 1

    def _configure_proxy(self):
        """Configure proxy for AkShare's underlying requests."""
        # AkShare uses requests internally; setting env vars should work
        # for most AkShare functions
        proxy = os.environ.get("AKSHARE_PROXY") or os.environ.get("HTTP_PROXY")
        if proxy:
            os.environ.setdefault("HTTP_PROXY", proxy)
            os.environ.setdefault("HTTPS_PROXY", proxy)

    def fetch_stock_realtime(self, stock_code: str) -> DataSourceResult:
        self._configure_proxy()
        df = ak.stock_zh_a_spot_em()
        # ... parse as before ...
        return DataSourceResult(data=parsed, source=self.name)

    # ... other methods ...
```

### 14.4 EastMoney Direct Adapter

```python
# backend/app/services/data_sources/eastmoney_adapter.py

import requests
from .base import DataSourceAdapter, DataSourceResult


EASTMONEY_STOCK_API = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_FUND_NAV_API = "https://fundgz.1234567.com.cn/js/{code}.js"


class EastMoneyAdapter(DataSourceAdapter):
    """Direct East Money API adapter as AkShare fallback."""

    @property
    def name(self) -> str:
        return "eastmoney"

    @property
    def priority(self) -> int:
        return 2

    def fetch_stock_realtime(self, stock_code: str) -> DataSourceResult:
        # Direct HTTP request to East Money push API
        # Parse JSON response into StockQuote format
        ...

    def fetch_fund_nav(self, fund_code: str) -> DataSourceResult:
        # Direct HTTP request to fundgz.1234567.com.cn
        # Parse JavaScript callback response
        ...

    # ... other methods ...
```

### 14.5 Configuration Extension

**File:** `backend/config.yaml` (MODIFY)

```yaml
data_sources:
  akshare:
    enabled: true
    stock_cache_ttl_seconds: 60
    sector_cache_ttl_seconds: 60
    fund_cache_ttl_seconds: 300
    request_timeout_seconds: 15
    proxy: ""                    # NEW: explicit proxy URL, e.g. "http://127.0.0.1:7890"
  eastmoney:                     # NEW
    enabled: true
    request_timeout_seconds: 10
  fallback:                      # NEW
    max_retries: 2
    extended_cache_ttl_seconds: 300  # When all sources fail, use cache up to 5 min
```

---

## 15. UX Optimization Architecture

### 15.1 Global Search Component

**File:** `frontend/src/components/GlobalSearch.jsx` (NEW)

A command-palette style search triggered by `Ctrl+K`:

```
+--------------------------------------------------+
| [Ctrl+K] Search stocks, funds, or commands...     |
+--------------------------------------------------+
| Recent searches                                   |
|   600519 贵州茅台 - Stock                         |
|   000510 中证A500 - Fund                          |
+--------------------------------------------------+
| Quick actions                                     |
|   > Open Stock Sector tab                         |
|   > Open Fund Sector tab                          |
|   > Open Market Overview                          |
+--------------------------------------------------+
```

**State:**
```javascript
const [query, setQuery] = useState('');
const [isOpen, setIsOpen] = useState(false);
const [results, setResults] = useState([]);
```

**Behavior:**
- Type a stock/fund code or name
- Auto-detect type (6-digit starting with 0/3 = SZ stock, 6 = SH stock, else fund)
- Enter navigates to the appropriate tab and triggers analysis
- Escape closes the palette

### 15.2 Responsive Breakpoints

```css
/* Mobile-first responsive design */
/* styles.css additions */

/* Mobile: < 768px */
@media (max-width: 767px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
  .research-layout {
    flex-direction: column;
  }
  .research-layout__sidebar {
    width: 100%;
  }
  .market-indices-grid {
    grid-template-columns: 1fr 1fr;
  }
  .sector-table-wrap {
    overflow-x: auto;
  }
  /* Convert tables to card lists on mobile */
  .sector-table tbody tr {
    display: block;
    margin-bottom: 8px;
    border-radius: 8px;
    padding: 12px;
  }
}

/* Tablet: 768px - 1023px */
@media (min-width: 768px) and (max-width: 1023px) {
  .layout-grid {
    grid-template-columns: 1fr 1fr;
  }
  .market-indices-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Desktop: >= 1024px (current layout) */
@media (min-width: 1024px) {
  .layout-grid {
    grid-template-columns: 1fr 1fr 1fr;
  }
}
```

### 15.3 Analysis Export

**File:** `frontend/src/components/ExportButton.jsx` (NEW)

```javascript
import { useTranslation } from 'react-i18next';

function exportToJSON(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportToMarkdown(data, type) {
  let md = '';
  if (type === 'stock') {
    md = `# Stock Analysis: ${data.target_sector}\n\n`;
    md += `- Trend: ${data.trend}\n`;
    md += `- Momentum: ${data.momentum}\n`;
    md += `- Sentiment: ${data.sentiment_score}\n`;
    md += `- Confidence: ${data.confidence}\n\n`;
    md += `## Reasoning\n${data.reasoning}\n\n`;
    md += `## Key Factors\n${data.key_factors.map(f => `- ${f}`).join('\n')}\n\n`;
    md += `## Risk Warnings\n${data.risk_warnings.map(w => `- ${w}`).join('\n')}\n`;
  }
  // ... similar for fund type
  const blob = new Blob([md], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `analysis_${data.target_sector || data.fund_code}_${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExportButton({ data, type = 'stock' }) {
  const { t } = useTranslation();
  return (
    <div className="export-buttons">
      <button onClick={() => exportToJSON(data, `analysis_${Date.now()}.json`)}>
        {t('common.export')} JSON
      </button>
      <button onClick={() => exportToMarkdown(data, type)}>
        {t('common.export')} Markdown
      </button>
    </div>
  );
}
```

### 15.4 Theme System

CSS custom properties approach:

```css
/* styles.css -- Theme variables */

:root,
[data-theme="dark"] {
  --bg-primary: #08111f;
  --bg-secondary: #0e1a2e;
  --bg-card: rgba(14, 26, 46, 0.8);
  --text-primary: #e5eefb;
  --text-secondary: #8b9dc3;
  --border-color: rgba(255, 255, 255, 0.08);
  --accent: #3b82f6;
  --up-color: #22c55e;
  --down-color: #ef4444;
  --warn-color: #f59e0b;
}

[data-theme="light"] {
  --bg-primary: #f8fafc;
  --bg-secondary: #ffffff;
  --bg-card: #ffffff;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --border-color: rgba(0, 0, 0, 0.08);
  --accent: #2563eb;
  --up-color: #16a34a;
  --down-color: #dc2626;
  --warn-color: #d97706;
}
```

---

## 16. Phase 8-11 Implementation Summary

### 16.1 New Files (Phase 8-11)

| File | Phase | Owner |
|------|-------|-------|
| `frontend/src/i18n/index.js` | 8 | frontexpert |
| `frontend/src/i18n/locales/zh.json` | 8 | frontexpert |
| `frontend/src/i18n/locales/en.json` | 8 | frontexpert |
| `frontend/src/components/LanguageSwitcher.jsx` | 8 | frontexpert |
| `backend/app/services/watchlist_service.py` | 9 | pythonengineer |
| `backend/app/services/data_sources/__init__.py` | 10 | pythonengineer |
| `backend/app/services/data_sources/base.py` | 10 | pythonengineer |
| `backend/app/services/data_sources/akshare_adapter.py` | 10 | pythonengineer |
| `backend/app/services/data_sources/eastmoney_adapter.py` | 10 | pythonengineer |
| `backend/app/services/data_sources/sina_adapter.py` | 10 | pythonengineer |
| `backend/app/services/data_sources/mock_adapter.py` | 10 | pythonengineer |
| `backend/app/services/data_sources/fallback_chain.py` | 10 | pythonengineer |
| `frontend/src/components/GlobalSearch.jsx` | 11 | frontexpert |
| `frontend/src/components/ExportButton.jsx` | 11 | frontexpert |
| `frontend/src/components/WatchlistManager.jsx` | 9 | frontexpert |
| `frontend/src/hooks/useTheme.js` | 11 | frontexpert |
| `frontend/src/hooks/useKeyboardShortcut.js` | 11 | frontexpert |

### 16.2 Modified Files (Phase 8-11)

| File | Phase | Changes |
|------|-------|---------|
| `frontend/src/main.jsx` | 8 | Import i18n initialization |
| `frontend/src/App.jsx` | 8, 9, 11 | i18n hooks, LanguageSwitcher, GlobalSearch, theme |
| `frontend/src/views/StockSector.jsx` | 8, 9 | i18n, watchlist sidebar |
| `frontend/src/views/FundSector.jsx` | 8, 9 | i18n, watchlist sidebar |
| `frontend/src/views/MarketOverview.jsx` | 8, 9 | i18n, watchlist summary |
| `frontend/src/components/*.jsx` | 8 | All components: replace hardcoded strings with t() |
| `frontend/src/styles.css` | 8, 11 | Language switcher styles, responsive breakpoints, theme vars |
| `frontend/src/api/client.js` | 9 | Add watchlist API functions; fix analyzeFund to use /api/funds/analyze |
| `backend/app/main.py` | 9, 10 | Watchlist endpoints, data source status endpoint |
| `backend/app/models.py` | 9 | WatchlistRequest/Response models |
| `backend/app/services/database.py` | 9 | user_watchlist table |
| `backend/app/services/stock_service.py` | 10 | Use FallbackChain instead of direct akshare |
| `backend/app/services/fund_service.py` | 10 | Use FallbackChain instead of direct akshare |
| `backend/app/config.py` | 10 | Proxy config, fallback config |
| `backend/config.yaml` | 10 | Proxy and fallback settings |
