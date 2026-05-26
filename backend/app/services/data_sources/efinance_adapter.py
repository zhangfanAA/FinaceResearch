"""efinance historical data adapter (priority=3).

Uses the ``efinance`` package for A-share sector and index historical data.
Simple API, good fallback when other sources fail.

Supported methods:
- ``fetch_sector_history``: ``ef.stock.get_quote_history(sector_code)``
- ``fetch_index_history``: ``ef.stock.get_quote_history(index_code)``
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


class EfinanceAdapter(HistoricalDataAdapter):
    """efinance historical data adapter for A-share sectors and indices.

    The ``efinance`` package provides a simple interface to EastMoney data.
    """

    @property
    def name(self) -> str:
        return "efinance"

    @property
    def priority(self) -> int:
        return 3

    def fetch_sector_history(
        self,
        sector_name: str,
        sector_type: str = "industry",
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical kline data for a sector via efinance.

        Args:
            sector_name: e.g. "白酒", "半导体"
            sector_type: "industry" or "concept"
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]
        """
        try:
            import efinance as ef
        except ImportError:
            raise ImportError("efinance package is not installed. Run: pip install efinance")

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        logger.info(
            "efinance: fetching sector history for %s (type=%s, %s to %s)",
            sector_name, sector_type, start_date, end_date,
        )

        # efinance uses the sector name directly for board queries
        try:
            df = ef.stock.get_quote_history(
                sector_name,
                beg=start_date,
                end=end_date,
                klt=101,  # daily
            )
        except Exception as exc:
            raise ValueError(
                f"efinance failed to fetch sector history for {sector_name}: {exc}"
            ) from exc

        if df is None or df.empty:
            raise ValueError(f"No sector history data returned from efinance for {sector_name}")

        # efinance returns columns: 股票名称, 股票代码, 日期, 开盘, 收盘, 最高, 最低, 成交量, ...
        # Column names may vary; handle both Chinese and English
        results: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            date_val = _safe_str(row.get("日期", row.get("date", "")))
            open_val = _safe_float(row.get("开盘", row.get("open", 0)))
            close_val = _safe_float(row.get("收盘", row.get("close", 0)))
            high_val = _safe_float(row.get("最高", row.get("high", 0)))
            low_val = _safe_float(row.get("最低", row.get("low", 0)))
            volume_val = _safe_float(row.get("成交量", row.get("volume", 0)))
            change_val = _safe_float(row.get("涨跌幅", row.get("change_pct", 0)))

            results.append({
                "date": date_val,
                "open": open_val,
                "close": close_val,
                "high": high_val,
                "low": low_val,
                "volume": volume_val,
                "change_pct": change_val,
            })

        return results

    def fetch_index_history(
        self,
        code: str,
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical daily data for a stock index via efinance.

        Args:
            code: e.g. "000001" (上证指数)
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]
        """
        try:
            import efinance as ef
        except ImportError:
            raise ImportError("efinance package is not installed. Run: pip install efinance")

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        logger.info("efinance: fetching index history for %s (%s to %s)", code, start_date, end_date)

        try:
            df = ef.stock.get_quote_history(
                code,
                beg=start_date,
                end=end_date,
                klt=101,  # daily
            )
        except Exception as exc:
            raise ValueError(
                f"efinance failed to fetch index history for {code}: {exc}"
            ) from exc

        if df is None or df.empty:
            raise ValueError(f"No index history data returned from efinance for {code}")

        results: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            date_val = _safe_str(row.get("日期", row.get("date", "")))
            open_val = _safe_float(row.get("开盘", row.get("open", 0)))
            close_val = _safe_float(row.get("收盘", row.get("close", 0)))
            high_val = _safe_float(row.get("最高", row.get("high", 0)))
            low_val = _safe_float(row.get("最低", row.get("low", 0)))
            volume_val = _safe_float(row.get("成交量", row.get("volume", 0)))
            change_val = _safe_float(row.get("涨跌幅", row.get("change_pct", 0)))

            results.append({
                "date": date_val,
                "open": open_val,
                "close": close_val,
                "high": high_val,
                "low": low_val,
                "volume": volume_val,
                "change_pct": change_val,
            })

        return results
