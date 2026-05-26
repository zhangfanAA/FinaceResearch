"""Fund sector AI analysis orchestration service.

Orchestrates the full fund analysis pipeline:
1. Fetch fund NAV (current + 30-day history)
2. Fetch fund news
3. Compute NAV trend (3d/7d/30d returns)
4. Build structured prompt combining NAV + news + macro context
5. Call cloud_llm with web_search enabled
6. Parse and validate structured JSON result
7. Check C-class fee warning if holding < 7 days
8. Log analysis to analysis_logs table
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import Config
from app.core.prompts import build_fund_analysis_prompt
from app.services import database, fund_service, stock_service
from app.services.cloud_llm import CloudLLMError, generate_with_cloud_llm, parse_json_object


@dataclass(slots=True)
class FundAnalysisResult:
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


def _validate_fund_json(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the LLM JSON output for fund analysis."""
    valid_judgments = {"positive", "negative", "neutral"}
    valid_trends = {"rising", "falling", "stable"}
    valid_suggestions = {"hold", "watch", "caution"}

    judgment = str(parsed.get("judgment", "neutral")).lower()
    if judgment not in valid_judgments:
        judgment = "neutral"

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

    nav_trend = str(parsed.get("nav_trend", "stable")).lower()
    if nav_trend not in valid_trends:
        nav_trend = "stable"

    news_highlights = parsed.get("news_highlights", [])
    if not isinstance(news_highlights, list):
        news_highlights = []
    news_highlights = [str(h) for h in news_highlights[:10]]

    risk_factors = parsed.get("risk_factors", [])
    if not isinstance(risk_factors, list):
        risk_factors = []
    risk_factors = [str(r) for r in risk_factors[:10]]

    suggestion = str(parsed.get("suggestion", "hold")).lower()
    if suggestion not in valid_suggestions:
        suggestion = "hold"

    return {
        "judgment": judgment,
        "sentiment_score": round(sentiment_score, 4),
        "confidence": round(confidence, 4),
        "reasoning": reasoning,
        "nav_trend": nav_trend,
        "news_highlights": news_highlights,
        "risk_factors": risk_factors,
        "suggestion": suggestion,
    }


def _compute_nav_trend_stats(nav_history: list[dict]) -> dict[str, float]:
    """Compute return statistics from NAV history."""
    if not nav_history or len(nav_history) < 2:
        return {"return_3d": 0.0, "return_7d": 0.0, "return_30d": 0.0}

    navs = [n["nav"] for n in nav_history if n.get("nav")]
    if len(navs) < 2:
        return {"return_3d": 0.0, "return_7d": 0.0, "return_30d": 0.0}

    latest = navs[0]
    stats: dict[str, float] = {}

    for days, key in [(3, "return_3d"), (7, "return_7d"), (30, "return_30d")]:
        if len(navs) > days:
            base = navs[days]
            if base > 0:
                stats[key] = round((latest - base) / base * 100, 4)
            else:
                stats[key] = 0.0
        else:
            stats[key] = 0.0

    return stats


def _check_c_class_fee_warning(config: Config, fund_code: str) -> bool:
    """Check if the fund is a C-class fund with < 7 days holding."""
    asset = config.assets.get(fund_code)
    if asset is None:
        return False
    return asset.fund_class == "C"


async def analyze_fund_sector(
    config: Config,
    fund_code: str,
    custom_prompt: str | None = None,
) -> FundAnalysisResult:
    """Run full fund analysis pipeline.

    Args:
        config: application configuration
        fund_code: e.g. "000510"
        custom_prompt: optional user-provided additional context
    Returns:
        FundAnalysisResult with judgment, sentiment, suggestion, etc.
    Raises:
        CloudLLMError if LLM call fails
        ValueError if data fetching fails
    """
    fund_nav = fund_service.fetch_fund_nav(fund_code)

    try:
        nav_history = fund_service.fetch_fund_nav_history(fund_code, days=30)
    except ValueError:
        nav_history = []

    news_items = fund_service.fetch_fund_news(fund_code, limit=10)

    nav_stats = _compute_nav_trend_stats(nav_history)

    fund_info: dict[str, Any] = {
        "fund_code": fund_nav.fund_code,
        "fund_name": fund_nav.fund_name,
        "nav": fund_nav.nav,
        "acc_nav": fund_nav.acc_nav,
        "nav_date": fund_nav.nav_date,
        "daily_return": fund_nav.daily_return,
        **nav_stats,
    }

    prompt = build_fund_analysis_prompt(
        fund_code=fund_code,
        fund_info=fund_info,
        nav_history=nav_history,
        news_items=[n.__dict__ for n in news_items],
        custom_prompt=custom_prompt,
    )

    try:
        raw_output = await generate_with_cloud_llm(config, prompt, allow_web_search_tools=True)
    except CloudLLMError:
        raise

    try:
        parsed = parse_json_object(raw_output)
    except (ValueError, Exception) as exc:
        parsed = {
            "judgment": "neutral",
            "sentiment_score": 0.0,
            "confidence": 0.0,
            "reasoning": f"Failed to parse LLM output: {exc}",
            "nav_trend": "stable",
            "news_highlights": [],
            "risk_factors": ["LLM output parsing failed"],
            "suggestion": "hold",
        }

    validated = _validate_fund_json(parsed)

    c_class_warning = _check_c_class_fee_warning(config, fund_code)

    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        stock_service.log_analysis(
            conn,
            analysis_type="fund_sector",
            target_code=fund_code,
            target_name=fund_nav.fund_name,
            llm_prompt=prompt[:5000],
            llm_raw_output=raw_output[:5000],
            parsed_result=json.dumps(validated, ensure_ascii=False),
        )
    finally:
        conn.close()

    return FundAnalysisResult(
        fund_code=fund_code,
        fund_name=fund_nav.fund_name,
        c_class_fee_warning=c_class_warning,
        **validated,
    )
