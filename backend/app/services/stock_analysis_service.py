"""Stock sector AI analysis orchestration service.

Orchestrates the full stock sector analysis pipeline:
1. Fetch sector overview (top stocks, change_pct, turnover)
2. Fetch top stocks' real-time quotes + technical indicators
3. Build structured prompt with market data + technical indicators
4. Call cloud_llm for AI analysis
5. Parse and validate structured result
6. Log analysis to analysis_logs table
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import Config
from app.core.prompts import build_stock_analysis_prompt
from app.services import database, stock_service
from app.services.cloud_llm import CloudLLMError, generate_with_cloud_llm, parse_json_object


@dataclass(slots=True)
class StockAnalysisResult:
    target_sector: str
    trend: str
    momentum: str
    sentiment_score: float
    confidence: float
    reasoning: str
    key_factors: list[str]
    risk_warnings: list[str]
    technical_summary: dict[str, Any]


def _validate_analysis_json(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the LLM JSON output."""
    valid_trends = {"bullish", "bearish", "neutral"}
    valid_momentum = {"strong", "weak", "sideways"}

    trend = str(parsed.get("trend", "neutral")).lower()
    if trend not in valid_trends:
        trend = "neutral"

    momentum = str(parsed.get("momentum", "sideways")).lower()
    if momentum not in valid_momentum:
        momentum = "sideways"

    sentiment_score = parsed.get("sentiment_score", 0.0)
    try:
        sentiment_score = max(-1.0, min(1.0, float(sentiment_score)))
    except (ValueError, TypeError):
        sentiment_score = 0.0

    confidence = parsed.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (ValueError, TypeError):
        confidence = 0.0

    reasoning = str(parsed.get("reasoning", ""))[:200]

    key_factors = parsed.get("key_factors", [])
    if not isinstance(key_factors, list):
        key_factors = []
    key_factors = [str(f) for f in key_factors[:10]]

    risk_warnings = parsed.get("risk_warnings", [])
    if not isinstance(risk_warnings, list):
        risk_warnings = []
    risk_warnings = [str(w) for w in risk_warnings[:10]]

    return {
        "trend": trend,
        "momentum": momentum,
        "sentiment_score": round(sentiment_score, 4),
        "confidence": round(confidence, 4),
        "reasoning": reasoning,
        "key_factors": key_factors,
        "risk_warnings": risk_warnings,
    }


async def analyze_stock_sector(
    config: Config,
    sector_name: str,
    sector_type: str = "industry",
) -> StockAnalysisResult:
    """Run full stock sector analysis pipeline.

    Args:
        config: application configuration
        sector_name: name of the sector to analyze
        sector_type: "industry" or "concept"
    Returns:
        StockAnalysisResult with trend, momentum, sentiment, etc.
    Raises:
        CloudLLMError if LLM call fails
        ValueError if data fetching fails
    """
    sector_stocks = stock_service.fetch_sector_stocks(sector_name)
    top_stocks = sector_stocks[:5]

    technical_data: dict[str, Any] = {}
    if top_stocks:
        try:
            df = stock_service.fetch_stock_history(top_stocks[0].stock_code, days=60)
            technical_data = stock_service.compute_technical_indicators(df)
        except ValueError:
            technical_data = {}

    market_overview = f"Sector: {sector_name} ({sector_type}), Stocks: {len(sector_stocks)}"

    prompt = build_stock_analysis_prompt(
        sector_name=sector_name,
        sector_stocks=[s.__dict__ for s in top_stocks],
        technical_data=technical_data,
        market_overview=market_overview,
    )

    try:
        raw_output = await generate_with_cloud_llm(config, prompt, allow_web_search_tools=False)
    except CloudLLMError:
        raise

    try:
        parsed = parse_json_object(raw_output)
    except (ValueError, Exception) as exc:
        parsed = {
            "trend": "neutral",
            "momentum": "sideways",
            "sentiment_score": 0.0,
            "confidence": 0.0,
            "reasoning": f"Failed to parse LLM output: {exc}",
            "key_factors": [],
            "risk_warnings": ["LLM output parsing failed"],
        }

    validated = _validate_analysis_json(parsed)

    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        stock_service.log_analysis(
            conn,
            analysis_type="stock_sector",
            target_code=sector_name,
            target_name=sector_name,
            llm_prompt=prompt[:5000],
            llm_raw_output=raw_output[:5000],
            parsed_result=json.dumps(validated, ensure_ascii=False),
        )
    finally:
        conn.close()

    return StockAnalysisResult(
        target_sector=sector_name,
        technical_summary=technical_data,
        **validated,
    )


async def analyze_single_stock(
    config: Config,
    stock_code: str,
) -> StockAnalysisResult:
    """Run analysis for a single stock's sector context.

    Args:
        config: application configuration
        stock_code: e.g. "600519"
    Returns:
        StockAnalysisResult
    Raises:
        CloudLLMError if LLM call fails
        ValueError if data fetching fails
    """
    quotes = stock_service.fetch_stock_realtime_batch([stock_code])
    if not quotes:
        raise ValueError(f"Stock {stock_code} not found")

    stock_quote = quotes[0]

    try:
        df = stock_service.fetch_stock_history(stock_code, days=60)
        technical_data = stock_service.compute_technical_indicators(df)
    except ValueError:
        technical_data = {}

    sector_name = f"Stock {stock_code} ({stock_quote.stock_name})"
    market_overview = f"Stock: {stock_code} {stock_quote.stock_name}, Price: {stock_quote.current_price}, Change: {stock_quote.change_pct}%"

    prompt = build_stock_analysis_prompt(
        sector_name=sector_name,
        sector_stocks=[stock_quote.__dict__],
        technical_data=technical_data,
        market_overview=market_overview,
    )

    try:
        raw_output = await generate_with_cloud_llm(config, prompt, allow_web_search_tools=False)
    except CloudLLMError:
        raise

    try:
        parsed = parse_json_object(raw_output)
    except (ValueError, Exception) as exc:
        parsed = {
            "trend": "neutral",
            "momentum": "sideways",
            "sentiment_score": 0.0,
            "confidence": 0.0,
            "reasoning": f"Failed to parse LLM output: {exc}",
            "key_factors": [],
            "risk_warnings": ["LLM output parsing failed"],
        }

    validated = _validate_analysis_json(parsed)

    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        stock_service.log_analysis(
            conn,
            analysis_type="stock_sector",
            target_code=stock_code,
            target_name=stock_quote.stock_name,
            llm_prompt=prompt[:5000],
            llm_raw_output=raw_output[:5000],
            parsed_result=json.dumps(validated, ensure_ascii=False),
        )
    finally:
        conn.close()

    return StockAnalysisResult(
        target_sector=sector_name,
        technical_summary=technical_data,
        **validated,
    )
