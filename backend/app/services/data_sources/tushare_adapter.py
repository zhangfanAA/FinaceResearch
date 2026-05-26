"""Tushare Pro historical data adapter (priority=1).

Requires a Tushare Pro API token configured in ``historical_data.tushare_token``.
Uses the ``tushare`` Python package to access index daily data and fund NAV history.

Supported methods:
- ``fetch_index_history``: ``pro.index_daily(ts_code=code)``
- ``fetch_fund_nav_history``: ``pro.fund_nav(ts_code=code)``

Tushare code format: "000001.SH" for 上证指数, "399001.SZ" for 深证成指.
"""

from __future__ import annotations

import logging
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


def _to_tushare_index_code(code: str) -> str:
    """Convert a bare index code like '000001' to Tushare format '000001.SH'.

    If the code already contains a dot (e.g. '000001.SH'), return as-is.
    """
    code = code.strip()
    if "." in code:
        return code
    # Heuristic: codes starting with 0/3 are SZ, starting with 8/9 are SH
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    return f"{code}.SH"


class TushareAdapter(HistoricalDataAdapter):
    """Tushare Pro historical data adapter.

    Requires a valid API token. If the token is empty or the ``tushare``
    package is not installed, all methods will raise on invocation.
    """

    def __init__(self, token: str = "") -> None:
        self._token = token
        self._pro = None

    @property
    def name(self) -> str:
        return "tushare"

    @property
    def priority(self) -> int:
        return 1

    def _get_pro(self):
        """Lazy-initialize the Tushare pro API client."""
        if self._pro is not None:
            return self._pro
        if not self._token:
            raise ValueError("Tushare API token is not configured (historical_data.tushare_token)")
        try:
            import tushare as ts
            ts.set_token(self._token)
            self._pro = ts.pro_api()
            return self._pro
        except ImportError:
            raise ImportError("tushare package is not installed. Run: pip install tushare")

    def fetch_index_history(
        self,
        code: str,
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical daily data for a stock index via Tushare Pro.

        Args:
            code: e.g. "000001" or "000001.SH"
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]
        """
        pro = self._get_pro()
        ts_code = _to_tushare_index_code(code)

        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        logger.info("Tushare: fetching index history for %s (%s to %s)", ts_code, start_date, end_date)

        df = pro.index_daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        if df is None or df.empty:
            raise ValueError(f"No data returned from Tushare for index {ts_code}")

        # Sort by trade_date ascending
        df = df.sort_values("trade_date", ascending=True).reset_index(drop=True)

        results: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            results.append({
                "date": _safe_str(row.get("trade_date")),
                "open": _safe_float(row.get("open")),
                "close": _safe_float(row.get("close")),
                "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")),
                "volume": _safe_float(row.get("vol")),
                "change_pct": _safe_float(row.get("pct_chg")),
            })

        return results

    def fetch_fund_nav_history(
        self,
        code: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Fetch historical NAV data for a fund via Tushare Pro.

        Args:
            code: fund code, e.g. "000510"
            days: number of days of history

        Returns:
            List of dicts: [{date, nav, acc_nav, daily_return}]
        """
        pro = self._get_pro()

        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        logger.info("Tushare: fetching fund NAV history for %s (%s to %s)", code, start_date, end_date)

        # Tushare fund NAV uses ts_code format like "000510.OF"
        ts_code = code.strip()
        if "." not in ts_code:
            ts_code = f"{ts_code}.OF"

        df = pro.fund_nav(
            ts_code=ts_code,
            begin_date=start_date,
            end_date=end_date,
        )

        if df is None or df.empty:
            raise ValueError(f"No fund NAV data returned from Tushare for {ts_code}")

        # Sort by nav_date ascending
        df = df.sort_values("nav_date", ascending=True).reset_index(drop=True)

        results: list[dict[str, Any]] = []
        nav_values = df["unit_nav"].tolist() if "unit_nav" in df.columns else []
        for i, (_, row) in enumerate(df.iterrows()):
            nav_val = _safe_float(row.get("unit_nav"))
            acc_val = _safe_float(row.get("accum_nav", nav_val))
            daily_ret = 0.0
            if i > 0 and len(nav_values) > i:
                prev = _safe_float(nav_values[i - 1])
                if prev > 0:
                    daily_ret = round((nav_val - prev) / prev * 100, 4)

            results.append({
                "date": _safe_str(row.get("nav_date")),
                "nav": nav_val,
                "acc_nav": acc_val,
                "daily_return": daily_ret,
            })

        return results
