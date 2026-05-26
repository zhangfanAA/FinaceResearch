"""Direct East Money push-API adapter -- primary fallback when AkShare fails.

Uses the public ``push2.eastmoney.com`` HTTP endpoints that do **not** require
authentication and are less likely to be blocked by proxies than the AkShare
scraping layer.

Endpoints:
- Stock realtime:  ``/api/qt/clist/get`` with ``fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23``
- Industry sector: ``/api/qt/clist/get`` with ``fs=m:90+t:2``
- Concept sector:  ``/api/qt/clist/get`` with ``fs=m:90+t:3``
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from app.services.data_sources.base import DataSourceAdapter, DataSourceResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_TIMEOUT = 10  # seconds

# Common query params for the push2 clist endpoint.
_COMMON_PARAMS: dict[str, str | int] = {
    "pn": 1,
    "pz": 5000,
    "po": 1,
    "np": 1,
    "fltt": 2,
    "invt": 2,
    "fid": "f3",
}

# Field mapping: EastMoney f-code -> our internal key
_STOCK_FIELD_MAP = {
    "f2": "current_price",
    "f3": "change_pct",
    "f5": "volume",
    "f6": "amount",
    "f7": "amplitude",
    "f12": "stock_code",
    "f14": "stock_name",
    "f15": "high_price",
    "f16": "low_price",
    "f17": "open_price",
    "f18": "prev_close",
}

# Sector field mapping
_SECTOR_FIELD_MAP = {
    "f12": "sector_code",
    "f14": "sector_name",
    "f3": "change_pct",
    "f8": "turnover_rate",
    "f104": "rise_count",
    "f105": "fall_count",
}

# A-share market filter: SH main + SZ main + GEM + STAR
_STOCK_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "-":
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


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None or value == "-":
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


class EastMoneyAdapter(DataSourceAdapter):
    """Direct East Money HTTP API adapter -- no AkShare dependency."""

    name = "eastmoney"
    priority = 2

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout
        self._session = requests.Session()
        # Force direct connection -- never use system/stale proxy env vars.
        self._session.trust_env = False
        self._session.proxies = {}
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })

    # ---- helpers ----

    def _get_json(self, params: dict) -> dict | None:
        """Issue GET to the push2 clist endpoint and return parsed JSON."""
        merged = {**_COMMON_PARAMS, **params}
        resp = self._session.get(_BASE_URL, params=merged, timeout=self._timeout)
        resp.raise_for_status()
        body = resp.json()
        return body

    # ---- DataSourceAdapter interface ----

    def fetch_stock_realtime(self, codes: list[str]) -> DataSourceResult:
        t0 = time.monotonic()
        try:
            body = self._get_json({"fs": _STOCK_FS, "fields": "f2,f3,f5,f6,f7,f12,f14,f15,f16,f17,f18"})
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning("EastMoney stock fetch failed: %s", exc)
            return DataSourceResult(
                data=None,
                source="eastmoney",
                latency_ms=round(elapsed, 2),
                error=str(exc),
            )

        data_list = (body.get("data") or {}).get("diff") or []
        if not data_list:
            elapsed = (time.monotonic() - t0) * 1000
            return DataSourceResult(
                data=None,
                source="eastmoney",
                latency_ms=round(elapsed, 2),
                error="Empty diff array from EastMoney",
            )

        # Index by stock code for O(1) lookup
        code_set = set(codes)
        by_code: dict[str, dict] = {}
        for item in data_list:
            em_code = _safe_str(item.get("f12"))
            if em_code in code_set:
                by_code[em_code] = item

        fetched_at = _now_iso()
        result: list[dict] = []
        for code in codes:
            item = by_code.get(code)
            if item is None:
                continue
            result.append({
                "stock_code": code,
                "stock_name": _safe_str(item.get("f14")),
                "current_price": _safe_float(item.get("f2")),
                "open_price": _safe_float(item.get("f17")),
                "high_price": _safe_float(item.get("f15")),
                "low_price": _safe_float(item.get("f16")),
                "prev_close": _safe_float(item.get("f18")),
                "volume": _safe_float(item.get("f5")),
                "amount": _safe_float(item.get("f6")),
                "change_pct": _safe_float(item.get("f3")),
                "fetched_at": fetched_at,
            })

        elapsed = (time.monotonic() - t0) * 1000
        return DataSourceResult(
            data=result,
            source="eastmoney",
            latency_ms=round(elapsed, 2),
        )

    def fetch_sector_list(self, sector_type: str) -> DataSourceResult:
        t0 = time.monotonic()

        if sector_type == "industry":
            fs = "m:90+t:2"
        elif sector_type == "concept":
            fs = "m:90+t:3"
        else:
            elapsed = (time.monotonic() - t0) * 1000
            return DataSourceResult(
                data=None,
                source="eastmoney",
                latency_ms=round(elapsed, 2),
                error=f"Invalid sector_type: {sector_type}",
            )

        try:
            body = self._get_json({"fs": fs, "fields": "f3,f8,f12,f14,f104,f105"})
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning("EastMoney sector fetch failed: %s", exc)
            return DataSourceResult(
                data=None,
                source="eastmoney",
                latency_ms=round(elapsed, 2),
                error=str(exc),
            )

        data_list = (body.get("data") or {}).get("diff") or []
        if not data_list:
            elapsed = (time.monotonic() - t0) * 1000
            return DataSourceResult(
                data=None,
                source="eastmoney",
                latency_ms=round(elapsed, 2),
                error="Empty sector diff from EastMoney",
            )

        fetched_at = _now_iso()
        result: list[dict] = []
        for item in data_list:
            result.append({
                "sector_code": _safe_str(item.get("f12")),
                "sector_name": _safe_str(item.get("f14")),
                "sector_type": sector_type,
                "change_pct": _safe_float(item.get("f3")),
                "turnover_rate": _safe_float(item.get("f8")),
                "leading_stock": "",  # EastMoney push API does not include leading stock
                "rise_count": _safe_int(item.get("f104")),
                "fall_count": _safe_int(item.get("f105")),
                "fetched_at": fetched_at,
            })

        result.sort(key=lambda x: x["change_pct"], reverse=True)
        elapsed = (time.monotonic() - t0) * 1000
        return DataSourceResult(
            data=result,
            source="eastmoney",
            latency_ms=round(elapsed, 2),
        )

    def fetch_fund_nav(self, codes: list[str]) -> DataSourceResult:
        """Fetch fund NAV from East Money fund API.

        Uses ``fundgz.1234567.com.cn`` for real-time estimated NAV.
        """
        t0 = time.monotonic()
        result: list[dict] = []
        errors: list[str] = []

        for code in codes:
            try:
                url = f"https://fundgz.1234567.com.cn/js/{code}.js"
                resp = self._session.get(url, timeout=self._timeout)
                resp.raise_for_status()
                text = resp.text
                # Response format: jsonpgz({...});
                if "(" not in text:
                    errors.append(f"Unexpected fund response for {code}")
                    continue
                import json

                json_str = text[text.index("(") + 1 : text.rindex(")")]
                data = json.loads(json_str)

                nav_val = _safe_float(data.get("dwjz"))
                acc_nav_val = _safe_float(data.get("gsz", nav_val))
                nav_date = _safe_str(data.get("gztime", ""))
                fund_name = _safe_str(data.get("name", ""))

                # Estimated change
                daily_return = _safe_float(data.get("gszzl"))

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
                logger.warning("EastMoney fund NAV fetch failed for %s: %s", code, exc)

        elapsed = (time.monotonic() - t0) * 1000

        if not result and errors:
            return DataSourceResult(
                data=None,
                source="eastmoney",
                latency_ms=round(elapsed, 2),
                error="; ".join(errors),
            )

        return DataSourceResult(
            data=result,
            source="eastmoney",
            latency_ms=round(elapsed, 2),
        )
