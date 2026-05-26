"""Mock data adapter -- last-resort fallback when all live sources fail.

Always returns ``DataSourceResult(is_mock=True, source="mock")``.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from app.services.data_sources.base import DataSourceAdapter, DataSourceResult

# Re-export the canonical mock dicts so the rest of the system can import
# from a single location.
MOCK_STOCK_DATA: dict[str, dict] = {
    "600519": {"name": "贵州茅台", "price": 1688.00, "change_pct": 1.25},
    "000001": {"name": "平安银行", "price": 11.85, "change_pct": -0.42},
    "000858": {"name": "五粮液", "price": 142.50, "change_pct": 0.88},
    "300750": {"name": "宁德时代", "price": 218.30, "change_pct": 2.15},
    "601318": {"name": "中国平安", "price": 48.60, "change_pct": -0.61},
}

# Separate index mock data -- market overview requests these codes as indices,
# not stocks. Keeping them separate avoids collision with stock codes (e.g. 000001).
MOCK_INDEX_DATA: dict[str, dict] = {
    "000001": {"name": "上证指数", "price": 3356.74, "change_pct": 1.15, "change_amount": 38.12},
    "399001": {"name": "深证成指", "price": 15856.61, "change_pct": 1.66, "change_amount": 259.31},
    "000300": {"name": "沪深300", "price": 3896.74, "change_pct": 0.88, "change_amount": 34.05},
    "000905": {"name": "中证500", "price": 5680.25, "change_pct": 1.02, "change_amount": 57.41},
    "000016": {"name": "上证50", "price": 2712.50, "change_pct": 0.65, "change_amount": 17.50},
}

MOCK_SECTOR_DATA: list[dict] = [
    {"code": "BK0477", "name": "半导体", "change_pct": 3.25, "turnover": 5.8, "leading": "中芯国际", "rise": 45, "fall": 8},
    {"code": "BK0478", "name": "人工智能", "change_pct": 2.88, "turnover": 4.2, "leading": "科大讯飞", "rise": 38, "fall": 12},
    {"code": "BK0479", "name": "新能源", "change_pct": 1.95, "turnover": 3.5, "leading": "宁德时代", "rise": 32, "fall": 15},
    {"code": "BK0480", "name": "白酒", "change_pct": 1.42, "turnover": 2.8, "leading": "贵州茅台", "rise": 18, "fall": 5},
    {"code": "BK0481", "name": "医药生物", "change_pct": 0.88, "turnover": 2.1, "leading": "恒瑞医药", "rise": 28, "fall": 22},
    {"code": "BK0482", "name": "银行", "change_pct": -0.35, "turnover": 1.2, "leading": "招商银行", "rise": 8, "fall": 25},
    {"code": "BK0483", "name": "房地产", "change_pct": -1.25, "turnover": 3.8, "leading": "万科A", "rise": 5, "fall": 35},
    {"code": "BK0484", "name": "钢铁", "change_pct": -0.68, "turnover": 1.5, "leading": "宝钢股份", "rise": 10, "fall": 20},
]

MOCK_FUND_DATA: dict[str, dict] = {
    "000510": {"name": "中证A500", "nav": 1.08, "acc_nav": 1.08, "daily_return": 0.5},
    "008282": {"name": "国泰半导体C", "nav": 1.10, "acc_nav": 1.10, "daily_return": -0.3},
    "SEMICONDUCTOR_C": {"name": "半导体C", "nav": 1.12, "acc_nav": 1.12, "daily_return": 0.8},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockAdapter(DataSourceAdapter):
    """Last-resort fallback that returns hardcoded mock data."""

    name = "mock"
    priority = 99

    def fetch_stock_realtime(self, codes: list[str]) -> DataSourceResult:
        t0 = time.monotonic()
        result: list[dict] = []
        for code in codes:
            # Check index data first (market overview uses these codes as indices)
            mock = MOCK_INDEX_DATA.get(code) or MOCK_STOCK_DATA.get(code)
            if mock is not None:
                price = mock["price"]
                change_pct = mock["change_pct"]
                prev_close = round(price * (1 - change_pct / 100), 2)
                change_amount = mock.get("change_amount") or round(price - prev_close, 2)
                result.append({
                    "stock_code": code,
                    "stock_name": mock["name"],
                    "current_price": price,
                    "open_price": round(price * 0.99, 2),
                    "high_price": round(price * 1.02, 2),
                    "low_price": round(price * 0.98, 2),
                    "prev_close": prev_close,
                    "volume": 1000000.0,
                    "amount": round(price * 1000000.0, 2),
                    "change_pct": change_pct,
                    "change_amount": change_amount,
                    "fetched_at": _now_iso(),
                })
        elapsed = (time.monotonic() - t0) * 1000
        return DataSourceResult(
            data=result,
            source="mock",
            is_mock=True,
            latency_ms=round(elapsed, 2),
        )

    def fetch_sector_list(self, sector_type: str) -> DataSourceResult:
        t0 = time.monotonic()
        result: list[dict] = []
        for s in MOCK_SECTOR_DATA:
            result.append({
                "sector_code": s["code"],
                "sector_name": s["name"],
                "sector_type": sector_type,
                "change_pct": s["change_pct"],
                "turnover_rate": s["turnover"],
                "leading_stock": s["leading"],
                "rise_count": s["rise"],
                "fall_count": s["fall"],
                "fetched_at": _now_iso(),
            })
        result.sort(key=lambda x: x["change_pct"], reverse=True)
        elapsed = (time.monotonic() - t0) * 1000
        return DataSourceResult(
            data=result,
            source="mock",
            is_mock=True,
            latency_ms=round(elapsed, 2),
        )

    def fetch_fund_nav(self, codes: list[str]) -> DataSourceResult:
        t0 = time.monotonic()
        result: list[dict] = []
        for code in codes:
            mock = MOCK_FUND_DATA.get(code)
            if mock is not None:
                result.append({
                    "fund_code": code,
                    "fund_name": mock["name"],
                    "nav": mock["nav"],
                    "acc_nav": mock["acc_nav"],
                    "nav_date": datetime.now().strftime("%Y-%m-%d"),
                    "daily_return": mock["daily_return"],
                    "fetched_at": _now_iso(),
                })
        elapsed = (time.monotonic() - t0) * 1000
        return DataSourceResult(
            data=result,
            source="mock",
            is_mock=True,
            latency_ms=round(elapsed, 2),
        )
