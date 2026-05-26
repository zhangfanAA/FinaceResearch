"""Baostock historical data adapter (priority=2).

Uses the ``baostock`` package for A-share index historical data.
Requires login/logout lifecycle management.

Supported methods:
- ``fetch_index_history``: ``bs.query_history_k_data_plus(code, fields=...)``

Code format: "sh.000001" for 上证指数, "sz.399001" for 深证成指.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.data_sources.historical_base import HistoricalDataAdapter

logger = logging.getLogger(__name__)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
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


def _to_baostock_code(code: str) -> str:
    """Convert a bare index code like '000001' to Baostock format 'sh.000001'.

    If the code already contains a dot, return as-is.
    """
    code = code.strip()
    if "." in code:
        return code.lower()
    # Heuristic: codes starting with 0/3 are SZ, starting with 8/9 are SH
    if code.startswith(("0", "3")):
        return f"sz.{code}"
    return f"sh.{code}"


class BaostockAdapter(HistoricalDataAdapter):
    """Baostock historical data adapter for A-share indices.

    Manages login/logout lifecycle automatically. The ``baostock`` package
    requires an explicit ``bs.login()`` before any data queries.
    """

    @property
    def name(self) -> str:
        return "baostock"

    @property
    def priority(self) -> int:
        return 2

    def fetch_index_history(
        self,
        code: str,
        days: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical daily data for a stock index via Baostock.

        Args:
            code: e.g. "000001" or "sh.000001"
            days: number of calendar days of history

        Returns:
            List of dicts: [{date, open, close, high, low, volume, change_pct}]
        """
        try:
            import baostock as bs
        except ImportError:
            raise ImportError("baostock package is not installed. Run: pip install baostock")

        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        bs_code = _to_baostock_code(code)

        logger.info("Baostock: fetching index history for %s (%s to %s)", bs_code, start_date, end_date)

        lg = bs.login()
        if lg.error_code != "0":
            raise ConnectionError(f"Baostock login failed: {lg.error_msg}")

        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,pctChg",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3",  # No adjustment for indices
            )

            if rs.error_code != "0":
                raise ValueError(f"Baostock query failed for {bs_code}: {rs.error_msg}")

            results: list[dict[str, Any]] = []
            while rs.next():
                row = rs.get_row_data()
                # row order: date, open, high, low, close, volume, pctChg
                if len(row) >= 7:
                    results.append({
                        "date": _safe_str(row[0]),
                        "open": _safe_float(row[1]),
                        "close": _safe_float(row[4]),
                        "high": _safe_float(row[2]),
                        "low": _safe_float(row[3]),
                        "volume": _safe_float(row[5]),
                        "change_pct": _safe_float(row[6]),
                    })

            if not results:
                raise ValueError(f"No data returned from Baostock for {bs_code}")

            return results
        finally:
            bs.logout()
