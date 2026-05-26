"""DeepSeek web search data source service.

Calls DeepSeek API with web-search-capable prompts to fetch financial data
when traditional data sources (AkShare, EastMoney, etc.) are unavailable.

Features:
- Rate limiting (token-bucket, per-minute and daily caps)
- Circuit breaker (opens after N consecutive failures, cooldown after M seconds)
- Structured prompt templates for each data type
- JSON response parsing with markdown fence stripping
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx

from app.services.deepseek_date_guard import date_guard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket rate limiter with per-minute and daily caps."""

    def __init__(self, requests_per_minute: int = 20, daily_limit: int = 500):
        self.rpm = requests_per_minute
        self.daily_limit = daily_limit
        self.minute_tokens = float(requests_per_minute)
        self.daily_count = 0
        self.last_refill = time.time()
        self.day_start = time.time()

    async def acquire(self) -> None:
        """Wait until a request token is available, then consume one."""
        now = time.time()
        # Reset daily counter at midnight-ish
        if now - self.day_start > 86400:
            self.daily_count = 0
            self.day_start = now
        if self.daily_count >= self.daily_limit:
            raise RuntimeError("Daily DeepSeek API limit reached")
        # Refill minute tokens
        elapsed = now - self.last_refill
        self.minute_tokens = min(
            float(self.rpm), self.minute_tokens + elapsed * self.rpm / 60
        )
        self.last_refill = now
        if self.minute_tokens < 1:
            await asyncio.sleep(1)
            return await self.acquire()
        self.minute_tokens -= 1
        self.daily_count += 1


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Opens after N consecutive failures, auto-recovers after cooldown."""

    def __init__(self, fail_threshold: int = 5, cooldown_seconds: int = 300):
        self.fail_count = 0
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown_seconds
        self.opened_at = 0.0

    @property
    def is_open(self) -> bool:
        if self.fail_count >= self.fail_threshold:
            if time.time() - self.opened_at > self.cooldown:
                self.fail_count = 0
                return False
            return True
        return False

    def record_success(self) -> None:
        self.fail_count = 0

    def record_failure(self) -> None:
        self.fail_count += 1
        if self.fail_count >= self.fail_threshold:
            self.opened_at = time.time()


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

PROMPT_SECTOR_HISTORY = (
    '请搜索"{sector_name}"板块近{days}个交易日的K线数据，'
    "当前真实日期是{today}，搜索时必须使用此绝对日期。"
    "返回JSON数组格式，每个元素包含: date(YYYY-MM-DD), open, close, high, low, volume, change_pct。\n"
    "只返回JSON数组，不要其他文字。示例: "
    '[{{"date":"{today_iso}","open":100.5,"close":101.2,"high":102.0,"low":99.8,"volume":1234567,"change_pct":0.7}}]'
)

PROMPT_INDEX_HISTORY = (
    "请搜索上证指数(代码{code})近{days}个交易日的K线数据，"
    "当前真实日期是{today}，搜索时必须使用此绝对日期。"
    "返回JSON数组格式，每个元素包含: date(YYYY-MM-DD), open, close, high, low, volume, change_pct。\n"
    "只返回JSON数组，不要其他文字。"
)

PROMPT_FUND_NAV_HISTORY = (
    "请搜索基金{code}近{days}天的净值数据，"
    "当前真实日期是{today}，搜索时必须使用此绝对日期。"
    "返回JSON数组格式，每个元素包含: date(YYYY-MM-DD), nav(单位净值), acc_nav(累计净值)。\n"
    "只返回JSON数组，不要其他文字。"
)

PROMPT_SECTOR_REALTIME = (
    "请搜索{today}A股行业板块涨跌幅排行前{limit}名，"
    "返回JSON数组格式，每个元素包含: name(板块名称), change_pct(涨跌幅%), leader_stock(领涨股), leader_change(领涨股涨幅%)。\n"
    "只返回JSON数组，不要其他文字。"
)

PROMPT_MARKET_OVERVIEW = (
    '请搜索{today}A股市场概况，返回JSON格式: {{"vix":数值,"shanghai_index":{{"code":"000001","name":"上证指数","price":数值,"change_pct":数值}},'
    '"top_sectors":[{{"name":"板块名","change_pct":数值}}],"bottom_sectors":[{{"name":"板块名","change_pct":数值}}]}}。\n'
    "只返回JSON，不要其他文字。"
)


# ---------------------------------------------------------------------------
# DeepSeek Search Service
# ---------------------------------------------------------------------------


class DeepSeekSearchService:
    """Async service that calls DeepSeek API with web search prompts.

    Args:
        base_url: DeepSeek API base URL (e.g. ``http://model.mify.ai.srv/v1``).
        api_key: Bearer token for authentication.
        model: Model identifier (default ``deepseek-chat``).
        timeout: HTTP request timeout in seconds.
        requests_per_minute: Rate-limiter RPM cap.
        daily_limit: Rate-limiter daily request cap.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "deepseek-chat",
        timeout: int = 30,
        requests_per_minute: int = 20,
        daily_limit: int = 500,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.rate_limiter = RateLimiter(
            requests_per_minute=requests_per_minute,
            daily_limit=daily_limit,
        )
        self.circuit_breaker = CircuitBreaker()

    # ---- internal API caller ----

    async def _call_api(self, prompt: str) -> str:
        """Call DeepSeek chat completions endpoint and return raw response text.

        Enables web search via the ``tools`` parameter so DeepSeek can retrieve
        real-time financial data.  If the API rejects the ``tools`` parameter
        (e.g. the model/endpoint does not support it), the call is retried
        without it.

        The date guard injects the real CST date into the system prompt and
        replaces vague date words in the user prompt.
        """
        if self.circuit_breaker.is_open:
            raise RuntimeError("DeepSeek circuit breaker is open")
        await self.rate_limiter.acquire()

        # --- Date guard: inject real date into system prompt + clean user prompt ---
        system_content = (
            "你是一个专业的金融数据分析师，具备联网搜索能力。"
            "请务必使用联网搜索功能获取最新的市场数据来回答问题。"
            "返回要求的JSON格式数据，不要包含多余文字。"
        )
        system_content, prompt = date_guard.process_request(system_content, prompt)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "tools": [
                {
                    "type": "web_search",
                    "web_search": {
                        "enable": True,
                    },
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=body, headers=headers
            )
            # If the API rejects the tools parameter, retry without it
            if resp.status_code == 400:
                logger.warning(
                    "DeepSeek API rejected tools parameter, retrying without web search"
                )
                body.pop("tools", None)
                resp = await client.post(
                    f"{self.base_url}/chat/completions", json=body, headers=headers
                )
            resp.raise_for_status()
            data = resp.json()

        # Extract content, handling tool_calls if present
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

        self.circuit_breaker.record_success()
        return content

    # ---- JSON parsing ----

    @staticmethod
    def _parse_json_response(text: str) -> Any:
        """Extract JSON array or object from DeepSeek response text.

        Handles markdown code fences and partial JSON embedded in prose.
        """
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"[\[\{].*[\]\}]", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Cannot parse JSON from response: {text[:200]}")

    # ---- public search methods ----

    def _get_date_kwargs(self) -> dict[str, str]:
        """Return date-related keyword arguments for prompt formatting."""
        full_cn, iso, _ = date_guard.get_real_date()
        return {"today": full_cn, "today_iso": iso}

    def _validate_and_warn(self, raw: str, context: str) -> None:
        """Log a warning if the response contains stale dates."""
        is_valid, reason = date_guard.process_response(raw)
        if not is_valid:
            logger.warning("DeepSeek %s response has stale dates: %s", context, reason)

    async def search_sector_history(
        self, sector_name: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Search for sector kline data via DeepSeek web search."""
        prompt = PROMPT_SECTOR_HISTORY.format(
            sector_name=sector_name, days=days, **self._get_date_kwargs()
        )
        raw = await self._call_api(prompt)
        self._validate_and_warn(raw, "sector_history")
        data = self._parse_json_response(raw)
        result: list[dict[str, Any]] = []
        for item in data:
            result.append(
                {
                    "date": str(item.get("date", "")),
                    "open": float(item.get("open", 0)),
                    "close": float(item.get("close", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "volume": int(item.get("volume", 0)),
                    "change_pct": float(item.get("change_pct", 0)),
                }
            )
        return result

    async def search_index_history(
        self, code: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Search for index kline data via DeepSeek web search."""
        prompt = PROMPT_INDEX_HISTORY.format(
            code=code, days=days, **self._get_date_kwargs()
        )
        raw = await self._call_api(prompt)
        self._validate_and_warn(raw, "index_history")
        data = self._parse_json_response(raw)
        result: list[dict[str, Any]] = []
        for item in data:
            result.append(
                {
                    "date": str(item.get("date", "")),
                    "open": float(item.get("open", 0)),
                    "close": float(item.get("close", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "volume": int(item.get("volume", 0)),
                    "change_pct": float(item.get("change_pct", 0)),
                }
            )
        return result

    async def search_fund_nav_history(
        self, code: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Search for fund NAV history via DeepSeek web search."""
        prompt = PROMPT_FUND_NAV_HISTORY.format(
            code=code, days=days, **self._get_date_kwargs()
        )
        raw = await self._call_api(prompt)
        self._validate_and_warn(raw, "fund_nav_history")
        data = self._parse_json_response(raw)
        result: list[dict[str, Any]] = []
        for item in data:
            result.append(
                {
                    "date": str(item.get("date", "")),
                    "nav": float(item.get("nav", 0)),
                    "acc_nav": float(item.get("acc_nav", 0)),
                }
            )
        return result

    async def search_sector_realtime(self, limit: int = 20) -> list[dict[str, Any]]:
        """Search for today's sector rankings via DeepSeek web search."""
        prompt = PROMPT_SECTOR_REALTIME.format(limit=limit, **self._get_date_kwargs())
        raw = await self._call_api(prompt)
        self._validate_and_warn(raw, "sector_realtime")
        return self._parse_json_response(raw)

    async def search_market_overview(self) -> dict[str, Any]:
        """Search for market overview data via DeepSeek web search."""
        prompt = PROMPT_MARKET_OVERVIEW.format(**self._get_date_kwargs())
        raw = await self._call_api(prompt)
        self._validate_and_warn(raw, "market_overview")
        return self._parse_json_response(raw)

    # ---- status ----

    def get_status(self) -> dict[str, Any]:
        """Return rate limiter and circuit breaker status."""
        return {
            "rate_limiter": {
                "remaining_today": self.rate_limiter.daily_limit
                - self.rate_limiter.daily_count,
                "daily_limit": self.rate_limiter.daily_limit,
                "remaining_minute": int(self.rate_limiter.minute_tokens),
            },
            "circuit_breaker": {
                "is_open": self.circuit_breaker.is_open,
                "fail_count": self.circuit_breaker.fail_count,
            },
        }
