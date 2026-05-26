"""AkShare historical data adapter (priority=4).

Wraps the existing AkShare historical data logic that was previously
inlined in ``stock_service.py`` and ``fund_service.py``. This adapter
is the lowest-priority fallback, used when Tushare, Baostock, and
efinance all fail.

Supported methods:
- ``fetch_sector_history``: ``ak.stock_board_industry_hist_em`` / ``ak.stock_board_concept_hist_em``
- ``fetch_index_history``: ``ak.index_zh_a_hist``
- ``fetch_fund_nav_history``: ``ak.fund_open_fund_info_em``
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from app.services.data_sources.historical_base import HistoricalDataAdapter

logger = logging.getLogger(__name__)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        import pandas as pd
        if isinstance(value, float) and pd.isna(value):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_str(value: object, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except (ValueError, TypeError):
        return default


class AkShareHistoricalAdapter(HistoricalDataAdapter):
    """AkShare historical data adapter.

    This is the lowest-priority adapter, preserving the existing AkShare
    logic for backward compatibility.
    """

    @property
    def name(self) -> str:
        return "akshare"

    @property
    def priority(self) -> int:
        return 4

    def fetch_sector_history(
        self,
        sector_name: str,
        sector_type: str = "industry",
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical kline data for a sector via AkShare.

        Args:
            sector_name: e.g. "白酒", "半导体"
            sector_type: "industry" or "concept"
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]
        """
        import akshare as ak

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        logger.info(
            "AkShare: fetching sector history for %s (type=%s, %s to %s)",
            sector_name, sector_type, start_date, end_date,
        )

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
            raise ValueError(
                f"AkShare failed to fetch sector history for {sector_name}: {exc}"
            ) from exc

        if df is None or df.empty:
            raise ValueError(f"No sector history data returned from AkShare for {sector_name}")

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
        self,
        code: str,
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical daily data for a stock index via AkShare.

        Args:
            code: e.g. "000001" (上证指数), "399001" (深证成指)
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]
        """
        import akshare as ak

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        logger.info("AkShare: fetching index history for %s (%s to %s)", code, start_date, end_date)

        try:
            df = ak.index_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date,
            )
        except Exception as exc:
            raise ValueError(
                f"AkShare failed to fetch index history for {code}: {exc}"
            ) from exc

        if df is None or df.empty:
            raise ValueError(f"No index history data returned from AkShare for {code}")

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

    def fetch_fund_nav_history(
        self,
        code: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Fetch historical NAV data for a fund via AkShare.

        Args:
            code: fund code, e.g. "000510"
            days: number of days of history

        Returns:
            List of dicts: [{date, nav, acc_nav, daily_return}]
        """
        import akshare as ak
        import pandas as pd

        logger.info("AkShare: fetching fund NAV history for %s (last %d days)", code, days)

        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        except Exception as exc:
            raise ValueError(
                f"AkShare failed to fetch fund NAV history for {code}: {exc}"
            ) from exc

        if df is None or df.empty:
            raise ValueError(f"No fund NAV history returned from AkShare for {code}")

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
