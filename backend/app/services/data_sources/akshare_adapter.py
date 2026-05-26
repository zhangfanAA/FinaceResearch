"""AkShare adapter with proxy support and structured error handling.

Wraps ``ak.stock_zh_a_spot_em``, ``ak.stock_board_industry_name_em``,
``ak.stock_board_concept_name_em``, and ``ak.fund_open_fund_info_em``.

Reads HTTP/HTTPS proxy from environment variables ``HTTP_PROXY`` / ``HTTPS_PROXY``
or from the explicit constructor parameters.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import akshare as ak
import pandas as pd

from app.services.data_sources.base import DataSourceAdapter, DataSourceResult

logger = logging.getLogger(__name__)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_str(value: object, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except (ValueError, TypeError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply_proxy(http_proxy: str = "", https_proxy: str = "") -> None:
    """Set proxy env vars if explicit values were provided."""
    if http_proxy:
        os.environ.setdefault("HTTP_PROXY", http_proxy)
    if https_proxy:
        os.environ.setdefault("HTTPS_PROXY", https_proxy)


def _force_clear_proxy_env() -> None:
    """Remove all proxy-related env vars to guarantee direct connection.

    Called at adapter init to guard against stale proxy env vars on Windows.
    """
    for key in (
        "http_proxy", "HTTP_PROXY",
        "https_proxy", "HTTPS_PROXY",
        "all_proxy", "ALL_PROXY",
    ):
        os.environ.pop(key, None)


class AkShareAdapter(DataSourceAdapter):
    """AkShare-backed data source with optional proxy configuration.

    By default, forces direct connection (no proxy). Pass explicit proxy URLs
    to route through a proxy.
    """

    name = "akshare"
    priority = 1

    def __init__(
        self,
        http_proxy: str = "",
        https_proxy: str = "",
    ) -> None:
        self._http_proxy = http_proxy or os.environ.get("HTTP_PROXY", "")
        self._https_proxy = https_proxy or os.environ.get("HTTPS_PROXY", "")
        if self._http_proxy or self._https_proxy:
            _apply_proxy(self._http_proxy, self._https_proxy)
        else:
            # No explicit proxy requested -- ensure env vars are clean.
            _force_clear_proxy_env()

    # ---- DataSourceAdapter interface ----

    def fetch_stock_realtime(self, codes: list[str]) -> DataSourceResult:
        t0 = time.monotonic()
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning("AkShare stock_zh_a_spot_em failed: %s", exc)
            return DataSourceResult(
                data=None,
                source="akshare",
                latency_ms=round(elapsed, 2),
                error=str(exc),
            )

        if df is None or df.empty:
            elapsed = (time.monotonic() - t0) * 1000
            return DataSourceResult(
                data=None,
                source="akshare",
                latency_ms=round(elapsed, 2),
                error="Empty response from AkShare",
            )

        fetched_at = _now_iso()
        result: list[dict] = []
        for code in codes:
            row = df[df["代码"] == code]
            if row.empty:
                continue
            r = row.iloc[0]
            result.append({
                "stock_code": code,
                "stock_name": _safe_str(r.get("名称")),
                "current_price": _safe_float(r.get("最新价")),
                "open_price": _safe_float(r.get("今开")),
                "high_price": _safe_float(r.get("最高")),
                "low_price": _safe_float(r.get("最低")),
                "prev_close": _safe_float(r.get("昨收")),
                "volume": _safe_float(r.get("成交量")),
                "amount": _safe_float(r.get("成交额")),
                "change_pct": _safe_float(r.get("涨跌幅")),
                "fetched_at": fetched_at,
            })

        elapsed = (time.monotonic() - t0) * 1000
        return DataSourceResult(
            data=result,
            source="akshare",
            latency_ms=round(elapsed, 2),
        )

    def fetch_sector_list(self, sector_type: str) -> DataSourceResult:
        t0 = time.monotonic()
        try:
            if sector_type == "industry":
                df = ak.stock_board_industry_name_em()
            else:
                df = ak.stock_board_concept_name_em()
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning("AkShare sector fetch failed: %s", exc)
            return DataSourceResult(
                data=None,
                source="akshare",
                latency_ms=round(elapsed, 2),
                error=str(exc),
            )

        if df is None or df.empty:
            elapsed = (time.monotonic() - t0) * 1000
            return DataSourceResult(
                data=None,
                source="akshare",
                latency_ms=round(elapsed, 2),
                error="Empty sector response from AkShare",
            )

        fetched_at = _now_iso()
        result: list[dict] = []
        for _, r in df.iterrows():
            result.append({
                "sector_code": _safe_str(r.get("代码", r.get("板块代码", ""))),
                "sector_name": _safe_str(r.get("板块名称", "")),
                "sector_type": sector_type,
                "change_pct": _safe_float(r.get("涨跌幅", 0)),
                "turnover_rate": _safe_float(r.get("换手率", 0)),
                "leading_stock": _safe_str(r.get("领涨股票", r.get("领涨股", ""))),
                "rise_count": _safe_int(r.get("上涨家数", 0)),
                "fall_count": _safe_int(r.get("下跌家数", 0)),
                "fetched_at": fetched_at,
            })

        result.sort(key=lambda x: x["change_pct"], reverse=True)
        elapsed = (time.monotonic() - t0) * 1000
        return DataSourceResult(
            data=result,
            source="akshare",
            latency_ms=round(elapsed, 2),
        )

    def fetch_fund_nav(self, codes: list[str]) -> DataSourceResult:
        t0 = time.monotonic()
        result: list[dict] = []
        errors: list[str] = []

        for code in codes:
            try:
                df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
                if df is None or df.empty:
                    errors.append(f"No NAV data for {code}")
                    continue

                df = df.sort_values(by="净值日期", ascending=False).reset_index(drop=True)
                latest = df.iloc[0]
                nav_val = _safe_float(latest.get("单位净值"))
                acc_nav_val = _safe_float(latest.get("累计净值", nav_val))
                nav_date = _safe_str(latest.get("净值日期", ""))

                daily_return = 0.0
                if len(df) > 1:
                    prev_nav = _safe_float(df.iloc[1].get("单位净值"))
                    if prev_nav > 0:
                        daily_return = round((nav_val - prev_nav) / prev_nav * 100, 4)

                fund_name = ""
                try:
                    info_df = ak.fund_open_fund_info_em(symbol=code, indicator="基金概况")
                    if info_df is not None and not info_df.empty:
                        fund_name = _safe_str(info_df.iloc[0].get("基金简称", ""))
                except Exception:
                    pass

                result.append({
                    "fund_code": code,
                    "fund_name": fund_name,
                    "nav": nav_val,
                    "acc_nav": acc_nav_val,
                    "nav_date": nav_date,
                    "daily_return": daily_return,
                    "fetched_at": _now_iso(),
                })
            except Exception as exc:
                errors.append(f"{code}: {exc}")
                logger.warning("AkShare fund NAV fetch failed for %s: %s", code, exc)

        elapsed = (time.monotonic() - t0) * 1000

        if not result and errors:
            return DataSourceResult(
                data=None,
                source="akshare",
                latency_ms=round(elapsed, 2),
                error="; ".join(errors),
            )

        return DataSourceResult(
            data=result,
            source="akshare",
            latency_ms=round(elapsed, 2),
        )
