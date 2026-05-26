"""Fund NAV data fetching and news aggregation via AkShare.

This module provides:
- Fund NAV (current + historical) fetching
- Fund news aggregation
- Fund basic info fetching
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
from app.services.data_sources.mock_adapter import MockAdapter

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300

# Canonical fallback chain for fund NAV fetching
fallback_chain = FallbackChain([AkShareAdapter(), EastMoneyAdapter(), MockAdapter()])


@dataclass(slots=True)
class FundNav:
    fund_code: str
    fund_name: str
    nav: float
    acc_nav: float
    nav_date: str
    daily_return: float
    fetched_at: str
    data_source: str = "unknown"


@dataclass(slots=True)
class FundNews:
    title: str
    source: str
    publish_time: str
    url: str
    summary: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except (ValueError, TypeError):
        return default


def _dict_to_fund_nav(d: dict) -> FundNav:
    """Convert an adapter result dict to a FundNav dataclass."""
    return FundNav(
        fund_code=d["fund_code"],
        fund_name=d.get("fund_name", ""),
        nav=_safe_float(d.get("nav")),
        acc_nav=_safe_float(d.get("acc_nav")),
        nav_date=d.get("nav_date", ""),
        daily_return=_safe_float(d.get("daily_return")),
        fetched_at=d.get("fetched_at", _now_iso()),
        data_source=d.get("data_source", "unknown"),
    )


def fetch_fund_nav(fund_code: str) -> FundNav:
    """Fetch latest NAV for a fund via fallback chain.

    Args:
        fund_code: e.g. "000510", "008282"
    Returns:
        FundNav with current NAV, cumulative NAV, daily return, data_source
    Raises:
        ValueError if fund_code is invalid or data unavailable
    """
    fund_code = fund_code.strip()
    if not fund_code:
        raise ValueError("fund_code must not be empty")

    result = fallback_chain.execute("fetch_fund_nav", [fund_code])
    data_list = result.data if isinstance(result.data, list) else []

    if not data_list:
        raise ValueError(f"No NAV data returned for fund {fund_code}: {result.error}")

    nav_dict = data_list[0]
    nav_dict["data_source"] = result.source
    return _dict_to_fund_nav(nav_dict)


def fetch_fund_nav_batch(fund_codes: list[str]) -> list[FundNav]:
    """Fetch latest NAV for multiple funds via fallback chain."""
    codes = [c.strip() for c in fund_codes if c and c.strip()]
    if not codes:
        return []

    result = fallback_chain.execute("fetch_fund_nav", codes)
    data_list = result.data if isinstance(result.data, list) else []

    if not data_list:
        logger.warning("No fund NAV data returned, source=%s, error=%s", result.source, result.error)
        return []

    navs: list[FundNav] = []
    for d in data_list:
        d["data_source"] = result.source
        navs.append(_dict_to_fund_nav(d))
    return navs


def fetch_fund_nav_history(fund_code: str, days: int = 30) -> list[dict[str, Any]]:
    """Fetch historical NAV for trend analysis.

    Args:
        fund_code: e.g. "000510"
        days: number of days of history
    Returns:
        List of dicts with keys: date, nav, acc_nav, daily_return
    Raises:
        ValueError if data unavailable
    """
    fund_code = fund_code.strip()
    if not fund_code:
        raise ValueError("fund_code must not be empty")

    try:
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
    except Exception as exc:
        raise ValueError(f"Failed to fetch fund NAV history for {fund_code}: {exc}") from exc

    if df is None or df.empty:
        raise ValueError(f"No NAV history returned for fund {fund_code}")

    df = df.sort_values(by="净值日期", ascending=False).head(days).reset_index(drop=True)

    results: list[dict[str, Any]] = []
    nav_values = df["单位净值"].tolist()
    for i, (_, row) in enumerate(df.iterrows()):
        nav_val = _safe_float(row.get("单位净值"))
        acc_val = _safe_float(row.get("累计净值", nav_val))
        daily_ret = 0.0
        if i < len(nav_values) - 1:
            prev = _safe_float(nav_values[i + 1])
            if prev > 0:
                daily_ret = round((nav_val - prev) / prev * 100, 4)

        results.append({
            "date": _safe_str(row.get("净值日期")),
            "nav": nav_val,
            "acc_nav": acc_val,
            "daily_return": daily_ret,
        })

    return results


def fetch_fund_news(fund_code: str, limit: int = 10) -> list[FundNews]:
    """Fetch recent news related to a fund.

    Uses AkShare news APIs. Falls back to empty list if unavailable.
    """
    fund_code = fund_code.strip()
    if not fund_code:
        return []

    try:
        df = ak.fund_news_em(symbol=fund_code)
        if df is None or df.empty:
            return []

        results: list[FundNews] = []
        for _, row in df.head(limit).iterrows():
            results.append(FundNews(
                title=_safe_str(row.get("新闻标题", row.get("title", ""))),
                source=_safe_str(row.get("新闻来源", row.get("source", ""))),
                publish_time=_safe_str(row.get("发布时间", row.get("publish_time", ""))),
                url=_safe_str(row.get("新闻链接", row.get("url", ""))),
                summary=_safe_str(row.get("新闻内容", row.get("summary", "")))[:200],
            ))
        return results
    except Exception:
        return []


def fetch_fund_basic_info(fund_code: str) -> dict[str, Any]:
    """Fetch fund metadata: name, type, manager, size, inception date."""
    fund_code = fund_code.strip()
    if not fund_code:
        raise ValueError("fund_code must not be empty")

    try:
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="基金概况")
        if df is None or df.empty:
            return {"fund_code": fund_code, "fund_name": "", "error": "No data"}

        row = df.iloc[0]
        result: dict[str, Any] = {"fund_code": fund_code}
        for col in df.columns:
            val = row.get(col)
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                result[str(col)] = str(val)
        return result
    except Exception as exc:
        return {"fund_code": fund_code, "error": str(exc)}


def cache_fund_nav(conn: sqlite3.Connection, navs: list[FundNav]) -> None:
    """Upsert fund NAV into cache table."""
    for n in navs:
        conn.execute(
            """
            INSERT INTO fund_nav_cache
                (fund_code, fund_name, nav, acc_nav, nav_date, daily_return, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fund_code) DO UPDATE SET
                fund_name = excluded.fund_name,
                nav = excluded.nav,
                acc_nav = excluded.acc_nav,
                nav_date = excluded.nav_date,
                daily_return = excluded.daily_return,
                fetched_at = excluded.fetched_at
            """,
            (n.fund_code, n.fund_name, n.nav, n.acc_nav, n.nav_date, n.daily_return, n.fetched_at),
        )
    conn.commit()


def get_cached_fund_navs(
    conn: sqlite3.Connection,
    max_age_seconds: int = CACHE_TTL_SECONDS,
) -> list[dict]:
    """Read fund NAVs from cache. Fund NAV TTL is longer (5 min) since NAV updates once daily."""
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    rows = conn.execute(
        "SELECT * FROM fund_nav_cache WHERE fetched_at >= ?",
        (datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),),
    ).fetchall()
    return [dict(row) for row in rows]
