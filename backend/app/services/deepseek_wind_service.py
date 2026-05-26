"""AI Wind Vane service -- DeepSeek-powered market sentiment and fund recommendations.

Provides sector-level hot topic analysis, fund direction recommendations,
and market sentiment scoring based on real-time A-share sector data combined
with user fund holdings from MySQL.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import Config, MySQLConfig
from app.services.cloud_llm import CloudLLMNoAPIKeyError, generate_with_cloud_llm
from app.services.mysql_database import get_connection
from app.services.stock_service import fetch_sector_list

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300

# Module-level in-memory cache
_cache: dict[str, Any] = {}
_cache_generated_at: datetime | None = None


@dataclass
class AIWindResult:
    """Result container for AI wind vane analysis."""

    hot_sectors: list[dict[str, Any]] = field(default_factory=list)
    fund_recommendations: list[dict[str, Any]] = field(default_factory=list)
    market_sentiment: str = "neutral"
    sentiment_score: float = 0.5
    summary: str = ""
    generated_at: str = ""
    cached: bool = False


def _get_user_fund_holdings(mysql_cfg: MySQLConfig) -> list[dict[str, Any]]:
    """Read user fund holdings from MySQL user_watchlist table.

    Returns a list of dicts with keys: code, name, shares, purchase_nav, purchase_amount.
    """
    try:
        with get_connection(
            host=mysql_cfg.host,
            port=mysql_cfg.port,
            user=mysql_cfg.user,
            password=mysql_cfg.password,
            database=mysql_cfg.database,
            pool_size=mysql_cfg.pool_size,
        ) as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT code, name, shares, purchase_nav, purchase_amount "
                "FROM user_watchlist WHERE item_type = 'fund'"
            )
            rows = cursor.fetchall()
            cursor.close()
            return rows or []
    except Exception as exc:
        logger.warning("Failed to read fund holdings from MySQL: %s", exc)
        return []


def _build_wind_prompt(
    sectors: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
) -> str:
    """Build a DeepSeek analysis prompt requesting strict JSON output.

    Args:
        sectors: Top sector dicts with keys: sector_name, change_pct, leading_stock, turnover_rate.
        holdings: User fund holdings with keys: code, name, shares, purchase_nav.

    Returns:
        Prompt string instructing the LLM to return a specific JSON structure.
    """
    sector_lines: list[str] = []
    for s in sectors[:20]:
        sector_lines.append(
            f"- {s.get('sector_name', '?')}: change_pct={s.get('change_pct', 0):.2f}%, "
            f"leading={s.get('leading_stock', '?')}, turnover={s.get('turnover_rate', 0):.2f}%"
        )
    sector_text = "\n".join(sector_lines) if sector_lines else "(no sector data available)"

    holding_lines: list[str] = []
    for h in holdings:
        holding_lines.append(
            f"- {h.get('code', '?')} ({h.get('name', '?')}): "
            f"shares={h.get('shares', 0)}, purchase_nav={h.get('purchase_nav', 0)}"
        )
    holding_text = "\n".join(holding_lines) if holding_lines else "(no fund holdings)"

    return f"""你是一位资深 A 股基金投资分析师。请根据以下实时板块数据和用户持仓基金信息，完成 AI 风向标分析。

## 实时板块数据（按涨跌幅排序，前20）
{sector_text}

## 用户持仓基金
{holding_text}

## 分析要求
1. 从板块数据中识别当前热门板块（涨幅靠前、换手率活跃），给出推荐理由。
2. 基于板块趋势和用户持仓，给出基金操作建议（加仓/减仓/持有/关注），说明理由和风险等级。
3. 判断当前市场情绪（bullish/neutral/bearish），给出 0-1 的情绪得分。
4. 综合总结当前市场风向。

## 输出要求
请严格返回以下 JSON 格式，不要包含任何其他文字或 markdown 标记：

{{
  "hot_sectors": [
    {{"sector_name": "板块名", "change_pct": 1.23, "reason": "推荐理由"}}
  ],
  "fund_recommendations": [
    {{"direction": "加仓/减仓/持有/关注", "reason": "理由", "fund_codes": ["000510"], "fund_names": ["基金名"], "risk_level": "low/medium/high"}}
  ],
  "market_sentiment": "bullish/neutral/bearish",
  "sentiment_score": 0.65,
  "summary": "综合总结文字"
}}"""


def _validate_wind_json(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize LLM JSON output.

    Applies fallback defaults for missing or malformed fields.
    """
    result: dict[str, Any] = {}

    # hot_sectors
    raw_sectors = parsed.get("hot_sectors")
    if isinstance(raw_sectors, list):
        result["hot_sectors"] = [
            {
                "sector_name": str(item.get("sector_name", "")),
                "change_pct": float(item.get("change_pct", 0)),
                "reason": str(item.get("reason", "")),
            }
            for item in raw_sectors
            if isinstance(item, dict)
        ]
    else:
        result["hot_sectors"] = []

    # fund_recommendations
    raw_recs = parsed.get("fund_recommendations")
    if isinstance(raw_recs, list):
        result["fund_recommendations"] = [
            {
                "direction": str(item.get("direction", "持有")),
                "reason": str(item.get("reason", "")),
                "fund_codes": item.get("fund_codes", []) if isinstance(item.get("fund_codes"), list) else [],
                "fund_names": item.get("fund_names", []) if isinstance(item.get("fund_names"), list) else [],
                "risk_level": str(item.get("risk_level", "medium")),
            }
            for item in raw_recs
            if isinstance(item, dict)
        ]
    else:
        result["fund_recommendations"] = []

    # market_sentiment
    raw_sentiment = parsed.get("market_sentiment", "neutral")
    if raw_sentiment in ("bullish", "neutral", "bearish"):
        result["market_sentiment"] = raw_sentiment
    else:
        result["market_sentiment"] = "neutral"

    # sentiment_score
    try:
        score = float(parsed.get("sentiment_score", 0.5))
        result["sentiment_score"] = max(0.0, min(1.0, score))
    except (ValueError, TypeError):
        result["sentiment_score"] = 0.5

    # summary
    result["summary"] = str(parsed.get("summary", ""))

    return result


def _is_cache_valid() -> bool:
    """Check whether the in-memory cache is still within TTL."""
    if not _cache or _cache_generated_at is None:
        return False
    elapsed = (datetime.now(timezone.utc) - _cache_generated_at).total_seconds()
    return elapsed < _CACHE_TTL_SECONDS


async def analyze_ai_wind(config: Config, force_refresh: bool = False) -> AIWindResult:
    """Run the AI wind vane analysis pipeline.

    1. Check in-memory cache (TTL=300s) unless force_refresh is True.
    2. Fetch sector data via stock_service.fetch_sector_list("industry").
    3. Read user fund holdings from MySQL.
    4. Build prompt and call DeepSeek.
    5. Parse, validate, and cache the result.

    Args:
        config: Application config with deepseek and mysql settings.
        force_refresh: If True, bypass the cache.

    Returns:
        AIWindResult with analysis data.

    Raises:
        CloudLLMNoAPIKeyError: If DeepSeek API key is not configured.
        CloudLLMError: If DeepSeek call fails (caller should return 502).
    """
    global _cache, _cache_generated_at

    # Cache check
    if not force_refresh and _is_cache_valid():
        logger.debug("Returning cached AI wind result")
        result = AIWindResult(**_cache)
        result.cached = True
        return result

    # Fetch sector data
    sectors_raw = fetch_sector_list("industry")
    sectors = [
        {
            "sector_name": s.sector_name,
            "change_pct": s.change_pct,
            "leading_stock": s.leading_stock,
            "turnover_rate": s.turnover_rate,
        }
        for s in sectors_raw
    ]

    # Read user fund holdings
    holdings = _get_user_fund_holdings(config.mysql)

    # Build prompt and call DeepSeek
    prompt = _build_wind_prompt(sectors, holdings)
    raw_text = await generate_with_cloud_llm(config, prompt)

    # Parse JSON
    from app.services.cloud_llm import strip_markdown_code_fences

    cleaned = strip_markdown_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("LLM output is not a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse DeepSeek wind JSON, using fallback: %s", exc)
        parsed = {}

    # Validate and normalize
    validated = _validate_wind_json(parsed)

    now_iso = datetime.now(timezone.utc).isoformat()
    result = AIWindResult(
        hot_sectors=validated["hot_sectors"],
        fund_recommendations=validated["fund_recommendations"],
        market_sentiment=validated["market_sentiment"],
        sentiment_score=validated["sentiment_score"],
        summary=validated["summary"],
        generated_at=now_iso,
        cached=False,
    )

    # Update cache
    _cache = {
        "hot_sectors": result.hot_sectors,
        "fund_recommendations": result.fund_recommendations,
        "market_sentiment": result.market_sentiment,
        "sentiment_score": result.sentiment_score,
        "summary": result.summary,
        "generated_at": now_iso,
    }
    _cache_generated_at = datetime.now(timezone.utc)

    return result
