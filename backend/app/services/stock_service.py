"""A-share stock data fetching and technical indicator computation via AkShare.

This module provides:
- Real-time stock quote fetching for SH/SZ A-share stocks
- Sector board (industry/concept) data fetching
- Historical OHLCV data for technical analysis
- Technical indicator computation (MA, RSI, MACD, KDJ, Bollinger)
- SQLite cache layer with TTL-based freshness
- Multi-source fallback: AkShare -> EastMoney -> Mock
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import akshare as ak
import pandas as pd

from app.services.data_sources.akshare_adapter import AkShareAdapter
from app.services.data_sources.eastmoney_adapter import EastMoneyAdapter
from app.services.data_sources.fallback_chain import FallbackChain

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

# Canonical fallback chain used by all fetch_* functions in this module.
# Order: AkShare (priority=1) -> EastMoney (priority=2)
# Mock removed -- failures surface as errors instead of fake data
fallback_chain = FallbackChain([AkShareAdapter(), EastMoneyAdapter()])


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
    data_source: str = "unknown"
    change_amount: float = 0.0


@dataclass(slots=True)
class SectorQuote:
    sector_code: str
    sector_name: str
    sector_type: str
    change_pct: float
    turnover_rate: float
    leading_stock: str
    rise_count: int
    fall_count: int
    fetched_at: str
    data_source: str = "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except (ValueError, TypeError):
        return default



def _dict_to_stock_quote(d: dict) -> StockQuote:
    """Convert an adapter result dict to a StockQuote dataclass."""
    return StockQuote(
        stock_code=d["stock_code"],
        stock_name=d.get("stock_name", ""),
        current_price=_safe_float(d.get("current_price")),
        open_price=_safe_float(d.get("open_price")),
        high_price=_safe_float(d.get("high_price")),
        low_price=_safe_float(d.get("low_price")),
        prev_close=_safe_float(d.get("prev_close")),
        volume=_safe_float(d.get("volume")),
        amount=_safe_float(d.get("amount")),
        change_pct=_safe_float(d.get("change_pct")),
        fetched_at=d.get("fetched_at", _now_iso()),
        data_source=d.get("data_source", "unknown"),
        change_amount=_safe_float(d.get("change_amount", 0)),
    )


def _dict_to_sector_quote(d: dict) -> SectorQuote:
    """Convert an adapter result dict to a SectorQuote dataclass."""
    return SectorQuote(
        sector_code=d.get("sector_code", ""),
        sector_name=d.get("sector_name", ""),
        sector_type=d.get("sector_type", ""),
        change_pct=_safe_float(d.get("change_pct")),
        turnover_rate=_safe_float(d.get("turnover_rate")),
        leading_stock=d.get("leading_stock", ""),
        rise_count=_safe_int(d.get("rise_count")),
        fall_count=_safe_int(d.get("fall_count")),
        fetched_at=d.get("fetched_at", _now_iso()),
        data_source=d.get("data_source", "unknown"),
    )


def fetch_stock_realtime(stock_code: str) -> StockQuote:
    """Fetch real-time quote for a single A-share stock via fallback chain.

    Args:
        stock_code: e.g. "600519", "000001"
    Returns:
        StockQuote with current price, OHLCV, change_pct, data_source
    Raises:
        ValueError if stock_code is invalid or data unavailable
    """
    stock_code = stock_code.strip()
    if not stock_code:
        raise ValueError("stock_code must not be empty")

    result = fallback_chain.execute("fetch_stock_realtime", [stock_code])
    if result.error and not result.data:
        raise ValueError(f"Failed to fetch stock data for {stock_code}: {result.error}")

    data_list = result.data if isinstance(result.data, list) else []
    if not data_list:
        raise ValueError(f"No data returned for stock {stock_code}")

    quote_dict = data_list[0]
    quote_dict["data_source"] = result.source
    return _dict_to_stock_quote(quote_dict)


def fetch_stock_realtime_batch(stock_codes: list[str]) -> list[StockQuote]:
    """Fetch real-time quotes for multiple stocks via fallback chain.

    Args:
        stock_codes: list of stock codes, e.g. ["600519", "000001"]
    Returns:
        list of StockQuote (may be fewer than requested if some codes not found)
    Raises:
        ValueError if fetch fails entirely
    """
    codes = [c.strip() for c in stock_codes if c and c.strip()]
    if not codes:
        return []

    result = fallback_chain.execute("fetch_stock_realtime", codes)
    data_list = result.data if isinstance(result.data, list) else []

    if not data_list:
        # Return empty list rather than raising -- callers handle empty gracefully
        logger.warning("No stock data returned for batch request, source=%s, error=%s", result.source, result.error)
        return []

    quotes: list[StockQuote] = []
    for d in data_list:
        d["data_source"] = result.source
        quotes.append(_dict_to_stock_quote(d))
    return quotes



def fetch_sector_list(sector_type: str = "industry") -> list[SectorQuote]:
    """Fetch all sector boards (industry or concept) via fallback chain.

    Args:
        sector_type: "industry" or "concept"
    Returns:
        List of SectorQuote sorted by change_pct descending
    Raises:
        ValueError if sector_type invalid or data unavailable
    """
    if sector_type not in ("industry", "concept"):
        raise ValueError(f"sector_type must be 'industry' or 'concept', got '{sector_type}'")

    result = fallback_chain.execute("fetch_sector_list", sector_type)
    data_list = result.data if isinstance(result.data, list) else []

    if not data_list:
        logger.warning("No sector data returned for %s, source=%s, error=%s", sector_type, result.source, result.error)
        return []

    quotes: list[SectorQuote] = []
    for d in data_list:
        d["data_source"] = result.source
        quotes.append(_dict_to_sector_quote(d))
    quotes.sort(key=lambda s: s.change_pct, reverse=True)
    return quotes


def fetch_sector_stocks(sector_name: str) -> list[StockQuote]:
    """Fetch all stocks within a given industry sector.

    Args:
        sector_name: e.g. "半导体", "白酒"
    Returns:
        list of StockQuote for stocks in the sector
    Raises:
        ValueError if sector not found
    """
    sector_name = sector_name.strip()
    if not sector_name:
        raise ValueError("sector_name must not be empty")

    fetched_at = _now_iso()

    try:
        df = ak.stock_board_industry_cons_em(symbol=sector_name)
    except Exception as exc:
        raise ValueError(f"Failed to fetch stocks for sector '{sector_name}': {exc}") from exc

    if df is None or df.empty:
        raise ValueError(f"No stocks found for sector '{sector_name}'")

    results: list[StockQuote] = []
    for _, r in df.iterrows():
        results.append(
            StockQuote(
                stock_code=_safe_str(r.get("代码", "")),
                stock_name=_safe_str(r.get("名称", "")),
                current_price=_safe_float(r.get("最新价")),
                open_price=_safe_float(r.get("今开")),
                high_price=_safe_float(r.get("最高")),
                low_price=_safe_float(r.get("最低")),
                prev_close=_safe_float(r.get("昨收")),
                volume=_safe_float(r.get("成交量")),
                amount=_safe_float(r.get("成交额")),
                change_pct=_safe_float(r.get("涨跌幅")),
                fetched_at=fetched_at,
            )
        )
    return results


def fetch_stock_history(
    stock_code: str,
    period: str = "daily",
    days: int = 60,
) -> pd.DataFrame:
    """Fetch historical OHLCV data for technical indicator computation.

    Args:
        stock_code: e.g. "600519"
        period: "daily", "weekly", or "monthly"
        days: number of calendar days of history to fetch
    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    Raises:
        ValueError if data unavailable
    """
    stock_code = stock_code.strip()
    if not stock_code:
        raise ValueError("stock_code must not be empty")

    from datetime import timedelta

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception as exc:
        raise ValueError(f"Failed to fetch history for {stock_code}: {exc}") from exc

    if df is None or df.empty:
        raise ValueError(f"No history data returned for {stock_code}")

    rename_map = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }
    df = df.rename(columns=rename_map)

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _get_historical_service():
    """Lazy-initialize the historical data service singleton."""
    global _historical_data_service
    if _historical_data_service is None:
        from app.services.historical_data_service import create_historical_data_service
        from app.config import load_config
        try:
            config = load_config()
            # Try to get the DeepSeek search service singleton from main
            ds_service = None
            try:
                from app.main import get_deepseek_search_service
                ds_service = get_deepseek_search_service()
            except Exception:
                pass
            _historical_data_service = create_historical_data_service(
                config, deepseek_search_service=ds_service,
            )
        except Exception as exc:
            logger.warning("Failed to initialize historical data service: %s", exc)
    return _historical_data_service


_historical_data_service = None


def fetch_sector_history(
    sector_name: str,
    sector_type: str = "industry",
    days: int = 60,
) -> list[dict[str, Any]]:
    """Fetch historical kline data for a sector (板块历史行情).

    Uses the multi-data-source historical data service with fallback chain
    (Tushare -> Baostock -> efinance -> AkShare) and SQLite caching.
    Falls back to direct AkShare call if the service is unavailable.

    Args:
        sector_name: e.g. "白酒", "半导体"
        sector_type: "industry" or "concept"
        days: number of calendar days of history
    Returns:
        List of dicts with keys: date, open, close, high, low, volume, change_pct
    Raises:
        ValueError if data unavailable
    """
    sector_name = sector_name.strip()
    if not sector_name:
        raise ValueError("sector_name must not be empty")

    service = _get_historical_service()
    if service is not None:
        return service.get_sector_history(sector_name, sector_type, days)

    # Fallback: direct AkShare call (legacy path)
    logger.warning("Historical data service unavailable, falling back to direct AkShare call")
    from datetime import timedelta

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        if sector_type == "concept":
            df = ak.stock_board_concept_hist_em(
                symbol=sector_name, period="日k",
                start_date=start_date, end_date=end_date, adjust="",
            )
        else:
            df = ak.stock_board_industry_hist_em(
                symbol=sector_name, period="日k",
                start_date=start_date, end_date=end_date, adjust="",
            )
    except Exception as exc:
        raise ValueError(f"Failed to fetch sector history for {sector_name}: {exc}") from exc

    if df is None or df.empty:
        raise ValueError(f"No history data returned for sector {sector_name}")

    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "涨跌幅": "change_pct",
    }
    df = df.rename(columns=rename_map)

    results: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        results.append({
            "date": _safe_str(row.get("date")),
            "open": _safe_float(row.get("open")),
            "close": _safe_float(row.get("close")),
            "high": _safe_float(row.get("high")),
            "low": _safe_float(row.get("low")),
            "volume": _safe_float(row.get("volume")),
            "change_pct": _safe_float(row.get("change_pct")),
        })

    return results


def fetch_index_history(
    index_code: str,
    days: int = 60,
) -> list[dict[str, Any]]:
    """Fetch historical kline data for a stock index (指数历史行情).

    Uses the multi-data-source historical data service with fallback chain
    (Tushare -> Baostock -> efinance -> AkShare) and SQLite caching.
    Falls back to direct AkShare call if the service is unavailable.

    Args:
        index_code: e.g. "000001" (上证指数), "399001" (深证成指)
        days: number of calendar days of history
    Returns:
        List of dicts with keys: date, open, close, high, low, volume, change_pct
    Raises:
        ValueError if data unavailable
    """
    index_code = index_code.strip()
    if not index_code:
        raise ValueError("index_code must not be empty")

    service = _get_historical_service()
    if service is not None:
        return service.get_index_history(index_code, days)

    # Fallback: direct AkShare call (legacy path)
    logger.warning("Historical data service unavailable, falling back to direct AkShare call")
    from datetime import timedelta

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        df = ak.index_zh_a_hist(
            symbol=index_code, period="daily",
            start_date=start_date, end_date=end_date,
        )
    except Exception as exc:
        raise ValueError(f"Failed to fetch index history for {index_code}: {exc}") from exc

    if df is None or df.empty:
        raise ValueError(f"No history data returned for index {index_code}")

    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "涨跌幅": "change_pct",
    }
    df = df.rename(columns=rename_map)

    results: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        results.append({
            "date": _safe_str(row.get("date")),
            "open": _safe_float(row.get("open")),
            "close": _safe_float(row.get("close")),
            "high": _safe_float(row.get("high")),
            "low": _safe_float(row.get("low")),
            "volume": _safe_float(row.get("volume")),
            "change_pct": _safe_float(row.get("change_pct")),
        })

    return results


def compute_technical_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Compute MA, RSI, MACD, KDJ, Bollinger Bands from OHLCV DataFrame.

    Args:
        df: DataFrame with columns: open, high, low, close, volume
    Returns:
        dict with latest values: ma5, ma10, ma20, ma60, rsi_14, macd, macd_signal,
        macd_hist, kdj_k, kdj_d, kdj_j, boll_upper, boll_middle, boll_lower
    """
    if df is None or df.empty:
        return {}

    try:
        import pandas_ta as ta
    except ImportError:
        return _compute_indicators_fallback(df)

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    result: dict[str, Any] = {}

    for period in (5, 10, 20, 60):
        ma = close.rolling(window=period).mean()
        result[f"ma{period}"] = round(float(ma.iloc[-1]), 4) if not ma.empty and pd.notna(ma.iloc[-1]) else None

    rsi = ta.rsi(close, length=14)
    result["rsi_14"] = round(float(rsi.iloc[-1]), 4) if rsi is not None and not rsi.empty and pd.notna(rsi.iloc[-1]) else None

    macd_df = ta.macd(close)
    if macd_df is not None and not macd_df.empty:
        last_row = macd_df.iloc[-1]
        result["macd"] = round(float(last_row.iloc[0]), 4) if pd.notna(last_row.iloc[0]) else None
        result["macd_signal"] = round(float(last_row.iloc[1]), 4) if pd.notna(last_row.iloc[1]) else None
        result["macd_hist"] = round(float(last_row.iloc[2]), 4) if pd.notna(last_row.iloc[2]) else None
    else:
        result["macd"] = None
        result["macd_signal"] = None
        result["macd_hist"] = None

    stoch = ta.stoch(high, low, close)
    if stoch is not None and not stoch.empty:
        last_stoch = stoch.iloc[-1]
        k_val = float(last_stoch.iloc[0]) if pd.notna(last_stoch.iloc[0]) else None
        d_val = float(last_stoch.iloc[1]) if pd.notna(last_stoch.iloc[1]) else None
        result["kdj_k"] = round(k_val, 4) if k_val is not None else None
        result["kdj_d"] = round(d_val, 4) if d_val is not None else None
        if k_val is not None and d_val is not None:
            result["kdj_j"] = round(3 * k_val - 2 * d_val, 4)
        else:
            result["kdj_j"] = None
    else:
        result["kdj_k"] = None
        result["kdj_d"] = None
        result["kdj_j"] = None

    bbands = ta.bbands(close, length=20)
    if bbands is not None and not bbands.empty:
        last_bb = bbands.iloc[-1]
        result["boll_lower"] = round(float(last_bb.iloc[0]), 4) if pd.notna(last_bb.iloc[0]) else None
        result["boll_middle"] = round(float(last_bb.iloc[1]), 4) if pd.notna(last_bb.iloc[1]) else None
        result["boll_upper"] = round(float(last_bb.iloc[2]), 4) if pd.notna(last_bb.iloc[2]) else None
    else:
        result["boll_lower"] = None
        result["boll_middle"] = None
        result["boll_upper"] = None

    return result


def _compute_indicators_fallback(df: pd.DataFrame) -> dict[str, Any]:
    """Fallback indicator computation without pandas_ta."""
    close = df["close"].astype(float)
    result: dict[str, Any] = {}

    for period in (5, 10, 20, 60):
        ma = close.rolling(window=period).mean()
        result[f"ma{period}"] = round(float(ma.iloc[-1]), 4) if not ma.empty and pd.notna(ma.iloc[-1]) else None

    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    result["rsi_14"] = round(float(rsi.iloc[-1]), 4) if not rsi.empty and pd.notna(rsi.iloc[-1]) else None

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    result["macd"] = round(float(macd_line.iloc[-1]), 4) if not macd_line.empty else None
    result["macd_signal"] = round(float(signal_line.iloc[-1]), 4) if not signal_line.empty else None
    result["macd_hist"] = round(float(macd_hist.iloc[-1]), 4) if not macd_hist.empty else None

    result["kdj_k"] = None
    result["kdj_d"] = None
    result["kdj_j"] = None

    result["boll_upper"] = None
    result["boll_middle"] = None
    result["boll_lower"] = None

    return result


def cache_stock_quotes(conn: sqlite3.Connection, quotes: list[StockQuote]) -> None:
    """Upsert stock quotes into cache table."""
    for q in quotes:
        conn.execute(
            """
            INSERT INTO stock_quotes_cache
                (stock_code, stock_name, current_price, open_price, high_price,
                 low_price, prev_close, volume, amount, change_pct, sector_name, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_code) DO UPDATE SET
                stock_name = excluded.stock_name,
                current_price = excluded.current_price,
                open_price = excluded.open_price,
                high_price = excluded.high_price,
                low_price = excluded.low_price,
                prev_close = excluded.prev_close,
                volume = excluded.volume,
                amount = excluded.amount,
                change_pct = excluded.change_pct,
                sector_name = excluded.sector_name,
                fetched_at = excluded.fetched_at
            """,
            (
                q.stock_code, q.stock_name, q.current_price, q.open_price,
                q.high_price, q.low_price, q.prev_close, q.volume, q.amount,
                q.change_pct, None, q.fetched_at,
            ),
        )
    conn.commit()


def cache_sector_quotes(conn: sqlite3.Connection, quotes: list[SectorQuote]) -> None:
    """Upsert sector quotes into cache table."""
    for s in quotes:
        conn.execute(
            """
            INSERT INTO sector_quotes_cache
                (sector_code, sector_name, sector_type, change_pct, turnover_rate,
                 leading_stock, rise_count, fall_count, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sector_code, sector_type) DO UPDATE SET
                sector_name = excluded.sector_name,
                change_pct = excluded.change_pct,
                turnover_rate = excluded.turnover_rate,
                leading_stock = excluded.leading_stock,
                rise_count = excluded.rise_count,
                fall_count = excluded.fall_count,
                fetched_at = excluded.fetched_at
            """,
            (
                s.sector_code, s.sector_name, s.sector_type, s.change_pct,
                s.turnover_rate, s.leading_stock, s.rise_count, s.fall_count,
                s.fetched_at,
            ),
        )
    conn.commit()


def get_cached_stock_quotes(
    conn: sqlite3.Connection,
    max_age_seconds: int = CACHE_TTL_SECONDS,
) -> list[dict]:
    """Read stock quotes from cache if fresh enough."""
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    rows = conn.execute(
        "SELECT * FROM stock_quotes_cache WHERE fetched_at >= ?",
        (datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_cached_sector_quotes(
    conn: sqlite3.Connection,
    sector_type: str = "industry",
    max_age_seconds: int = CACHE_TTL_SECONDS,
) -> list[dict]:
    """Read sector quotes from cache if fresh enough."""
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    rows = conn.execute(
        "SELECT * FROM sector_quotes_cache WHERE sector_type = ? AND fetched_at >= ?",
        (sector_type, datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def log_analysis(
    conn: sqlite3.Connection,
    analysis_type: str,
    target_code: str,
    target_name: str,
    llm_prompt: str,
    llm_raw_output: str,
    parsed_result: str,
) -> None:
    """Insert an analysis log entry."""
    conn.execute(
        """
        INSERT INTO analysis_logs (analysis_type, target_code, target_name, llm_prompt, llm_raw_output, parsed_result, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (analysis_type, target_code, target_name, llm_prompt, llm_raw_output, parsed_result, _now_iso()),
    )
    conn.commit()


def get_analysis_logs(
    conn: sqlite3.Connection,
    analysis_type: str = "all",
    limit: int = 20,
) -> list[dict]:
    """Read analysis logs from the analysis_logs table.

    Args:
        conn: SQLite connection with row_factory set.
        analysis_type: filter by ``"stock_sector"``, ``"fund_sector"``, or ``"all"``.
        limit: maximum number of rows to return (1-100).
    Returns:
        List of dicts ordered by ``created_at`` descending.
    """
    if analysis_type == "all":
        rows = conn.execute(
            "SELECT id, analysis_type, target_code, target_name, llm_raw_output, parsed_result, created_at "
            "FROM analysis_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, analysis_type, target_code, target_name, llm_raw_output, parsed_result, created_at "
            "FROM analysis_logs WHERE analysis_type = ? ORDER BY created_at DESC LIMIT ?",
            (analysis_type, limit),
        ).fetchall()
    return [dict(row) for row in rows]
