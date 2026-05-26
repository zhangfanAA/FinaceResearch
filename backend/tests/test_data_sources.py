"""Tests for the data source reliability layer (Phase 10A).

Covers:
- MockAdapter result format
- FallbackChain priority ordering and failover
- FallbackChain stats tracking
- EastMoney adapter field mapping (mocked HTTP)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.data_sources.base import AdapterStats, DataSourceAdapter, DataSourceResult
from app.services.data_sources.fallback_chain import FallbackChain
from app.services.data_sources.mock_adapter import MockAdapter


# ---- Helpers ----


class _StubAdapter(DataSourceAdapter):
    """Minimal adapter for testing FallbackChain logic."""

    def __init__(
        self,
        name: str = "stub",
        priority: int = 1,
        result: DataSourceResult | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self._result = result
        self._exc = exc

    def fetch_stock_realtime(self, codes: list[str]) -> DataSourceResult:
        if self._exc is not None:
            raise self._exc
        return self._result  # type: ignore[return-value]

    def fetch_sector_list(self, sector_type: str) -> DataSourceResult:
        if self._exc is not None:
            raise self._exc
        return self._result  # type: ignore[return-value]

    def fetch_fund_nav(self, codes: list[str]) -> DataSourceResult:
        if self._exc is not None:
            raise self._exc
        return self._result  # type: ignore[return-value]


# ---- MockAdapter tests ----


class TestMockAdapter:
    def test_fetch_stock_realtime_returns_mock_data(self):
        adapter = MockAdapter()
        result = adapter.fetch_stock_realtime(["600519", "000001"])

        assert result.source == "mock"
        assert result.is_mock is True
        assert result.error is None
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        first = result.data[0]
        assert first["stock_code"] == "600519"
        assert first["stock_name"] == "贵州茅台"
        assert "current_price" in first
        assert "change_pct" in first
        assert "fetched_at" in first

    def test_fetch_stock_realtime_unknown_code_returns_empty(self):
        adapter = MockAdapter()
        result = adapter.fetch_stock_realtime(["999999"])

        assert result.source == "mock"
        assert result.is_mock is True
        assert result.data == []

    def test_fetch_sector_list_industry(self):
        adapter = MockAdapter()
        result = adapter.fetch_sector_list("industry")

        assert result.source == "mock"
        assert result.is_mock is True
        assert isinstance(result.data, list)
        assert len(result.data) > 0

        first = result.data[0]
        assert "sector_code" in first
        assert "sector_name" in first
        assert first["sector_type"] == "industry"
        assert "change_pct" in first

    def test_fetch_sector_list_sorted_by_change_pct_desc(self):
        adapter = MockAdapter()
        result = adapter.fetch_sector_list("industry")

        pcts = [s["change_pct"] for s in result.data]
        assert pcts == sorted(pcts, reverse=True)

    def test_fetch_fund_nav_returns_mock(self):
        adapter = MockAdapter()
        result = adapter.fetch_fund_nav(["000510", "008282"])

        assert result.source == "mock"
        assert result.is_mock is True
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        first = result.data[0]
        assert first["fund_code"] == "000510"
        assert "nav" in first
        assert "acc_nav" in first
        assert "daily_return" in first

    def test_fetch_fund_nav_unknown_code_returns_empty(self):
        adapter = MockAdapter()
        result = adapter.fetch_fund_nav(["NOSUCH"])

        assert result.source == "mock"
        assert result.data == []


# ---- FallbackChain tests ----


class TestFallbackChain:
    def test_returns_first_success(self):
        success = DataSourceResult(data=[{"stock_code": "600519"}], source="good")
        good_adapter = _StubAdapter(name="good", priority=1, result=success)
        bad_adapter = _StubAdapter(name="bad", priority=2, result=DataSourceResult(data=None, source="bad", error="fail"))

        chain = FallbackChain([good_adapter, bad_adapter])
        result = chain.execute("fetch_stock_realtime", ["600519"])

        assert result.source == "good"
        assert result.data == [{"stock_code": "600519"}]

    def test_falls_through_to_next_on_failure(self):
        success = DataSourceResult(data=[{"stock_code": "600519"}], source="second")
        fail_adapter = _StubAdapter(name="fail", priority=1, exc=RuntimeError("boom"))
        ok_adapter = _StubAdapter(name="second", priority=2, result=success)

        chain = FallbackChain([fail_adapter, ok_adapter])
        result = chain.execute("fetch_stock_realtime", ["600519"])

        assert result.source == "second"
        assert result.data == [{"stock_code": "600519"}]

    def test_falls_through_on_error_envelope(self):
        success = DataSourceResult(data=[{"stock_code": "600519"}], source="fallback")
        err_adapter = _StubAdapter(
            name="err",
            priority=1,
            result=DataSourceResult(data=None, source="err", error="timeout"),
        )
        ok_adapter = _StubAdapter(name="fallback", priority=2, result=success)

        chain = FallbackChain([err_adapter, ok_adapter])
        result = chain.execute("fetch_stock_realtime", ["600519"])

        assert result.source == "fallback"

    def test_returns_none_data_when_all_fail(self):
        fail1 = _StubAdapter(name="a", priority=1, exc=RuntimeError("err1"))
        fail2 = _StubAdapter(name="b", priority=2, exc=RuntimeError("err2"))

        chain = FallbackChain([fail1, fail2])
        result = chain.execute("fetch_stock_realtime", ["600519"])

        assert result.source == "none"
        assert result.is_mock is True
        assert result.data is None
        assert "err1" in result.error
        assert "err2" in result.error

    def test_adapters_sorted_by_priority(self):
        a = _StubAdapter(name="low", priority=10)
        b = _StubAdapter(name="high", priority=1)
        c = _StubAdapter(name="mid", priority=5)

        chain = FallbackChain([a, b, c])
        names = [adapter.name for adapter in chain.adapters]
        assert names == ["high", "mid", "low"]


# ---- Stats tracking tests ----


class TestFallbackChainStats:
    def test_stats_track_success(self):
        success = DataSourceResult(data=[{}], source="s", latency_ms=42.5)
        adapter = _StubAdapter(name="s", priority=1, result=success)

        chain = FallbackChain([adapter])
        chain.execute("fetch_stock_realtime", [])

        stats = chain.get_status()
        assert "s" in stats
        assert stats["s"]["success_count"] == 1
        assert stats["s"]["failure_count"] == 0
        assert stats["s"]["avg_latency_ms"] == 42.5
        assert stats["s"]["last_error"] is None
        assert stats["s"]["last_success_at"] is not None

    def test_stats_track_failure(self):
        adapter = _StubAdapter(name="f", priority=1, exc=RuntimeError("oops"))

        chain = FallbackChain([adapter])
        chain.execute("fetch_stock_realtime", [])

        stats = chain.get_status()
        assert stats["f"]["success_count"] == 0
        assert stats["f"]["failure_count"] == 1
        assert "oops" in stats["f"]["last_error"]

    def test_stats_track_mixed_results(self):
        success = DataSourceResult(data=[{}], source="m", latency_ms=10.0)
        adapter = _StubAdapter(name="m", priority=1, result=success)
        fail_adapter = _StubAdapter(name="n", priority=2, exc=RuntimeError("fail"))

        chain = FallbackChain([adapter, fail_adapter])

        # First call -- succeeds via "m"
        chain.execute("fetch_stock_realtime", [])
        # Second call -- also succeeds via "m"
        chain.execute("fetch_stock_realtime", [])

        stats = chain.get_status()
        assert stats["m"]["success_count"] == 2
        assert stats["m"]["failure_count"] == 0

    def test_stats_cleared_on_error_then_success(self):
        err_result = DataSourceResult(data=None, source="r", error="timeout")
        err_adapter = _StubAdapter(name="r", priority=1, result=err_result)

        ok_result = DataSourceResult(data=[{}], source="r", latency_ms=5.0)
        ok_adapter = _StubAdapter(name="ok", priority=2, result=ok_result)

        chain = FallbackChain([err_adapter, ok_adapter])
        chain.execute("fetch_stock_realtime", [])

        stats = chain.get_status()
        # "r" failed (error envelope), "ok" succeeded
        assert stats["r"]["failure_count"] == 1
        assert stats["ok"]["success_count"] == 1


# ---- EastMoney adapter field mapping (mocked HTTP) ----


class TestEastMoneyAdapterFieldMapping:
    def _make_em_stock_response(self) -> dict:
        """Simulate EastMoney push2 clist JSON response for stocks."""
        return {
            "data": {
                "diff": [
                    {
                        "f2": 1688.00,     # current_price
                        "f3": 1.25,        # change_pct
                        "f5": 50000,       # volume
                        "f6": 84400000,    # amount
                        "f12": "600519",   # stock_code
                        "f14": "贵州茅台",  # stock_name
                        "f15": 1710.00,    # high_price
                        "f16": 1670.00,    # low_price
                        "f17": 1680.00,    # open_price
                        "f18": 1667.00,    # prev_close
                    },
                    {
                        "f2": 11.85,
                        "f3": -0.42,
                        "f5": 100000,
                        "f6": 1185000,
                        "f12": "000001",
                        "f14": "平安银行",
                        "f15": 12.00,
                        "f16": 11.70,
                        "f17": 11.90,
                        "f18": 11.90,
                    },
                ]
            }
        }

    def _make_em_sector_response(self) -> dict:
        """Simulate EastMoney push2 clist JSON response for sectors."""
        return {
            "data": {
                "diff": [
                    {
                        "f3": 3.25,       # change_pct
                        "f8": 5.8,        # turnover_rate
                        "f12": "BK0477",  # sector_code
                        "f14": "半导体",   # sector_name
                        "f104": 45,       # rise_count
                        "f105": 8,        # fall_count
                    },
                    {
                        "f3": 2.88,
                        "f8": 4.2,
                        "f12": "BK0478",
                        "f14": "人工智能",
                        "f104": 38,
                        "f105": 12,
                    },
                ]
            }
        }

    @patch("app.services.data_sources.eastmoney_adapter.requests.Session.get")
    def test_fetch_stock_realtime_maps_fields(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_em_stock_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.data_sources.eastmoney_adapter import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        result = adapter.fetch_stock_realtime(["600519", "000001"])

        assert result.source == "eastmoney"
        assert result.error is None
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        first = result.data[0]
        assert first["stock_code"] == "600519"
        assert first["stock_name"] == "贵州茅台"
        assert first["current_price"] == 1688.00
        assert first["high_price"] == 1710.00
        assert first["low_price"] == 1670.00
        assert first["open_price"] == 1680.00
        assert first["prev_close"] == 1667.00
        assert first["change_pct"] == 1.25
        assert first["volume"] == 50000
        assert first["amount"] == 84400000
        assert "fetched_at" in first

    @patch("app.services.data_sources.eastmoney_adapter.requests.Session.get")
    def test_fetch_stock_realtime_filters_requested_codes(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_em_stock_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.data_sources.eastmoney_adapter import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        result = adapter.fetch_stock_realtime(["000001"])

        assert len(result.data) == 1
        assert result.data[0]["stock_code"] == "000001"

    @patch("app.services.data_sources.eastmoney_adapter.requests.Session.get")
    def test_fetch_sector_list_maps_fields(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_em_sector_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.data_sources.eastmoney_adapter import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        result = adapter.fetch_sector_list("industry")

        assert result.source == "eastmoney"
        assert result.error is None
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        first = result.data[0]
        assert first["sector_code"] == "BK0477"
        assert first["sector_name"] == "半导体"
        assert first["sector_type"] == "industry"
        assert first["change_pct"] == 3.25
        assert first["turnover_rate"] == 5.8
        assert first["rise_count"] == 45
        assert first["fall_count"] == 8

    @patch("app.services.data_sources.eastmoney_adapter.requests.Session.get")
    def test_fetch_sector_list_sorted_desc(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_em_sector_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.data_sources.eastmoney_adapter import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        result = adapter.fetch_sector_list("industry")

        pcts = [s["change_pct"] for s in result.data]
        assert pcts == sorted(pcts, reverse=True)

    @patch("app.services.data_sources.eastmoney_adapter.requests.Session.get")
    def test_fetch_stock_realtime_handles_network_error(self, mock_get: MagicMock):
        import requests as req

        mock_get.side_effect = req.exceptions.ConnectionError("refused")

        from app.services.data_sources.eastmoney_adapter import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        result = adapter.fetch_stock_realtime(["600519"])

        assert result.source == "eastmoney"
        assert result.data is None
        assert "refused" in result.error

    @patch("app.services.data_sources.eastmoney_adapter.requests.Session.get")
    def test_fetch_sector_list_concept_uses_correct_fs(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"diff": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.data_sources.eastmoney_adapter import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        adapter.fetch_sector_list("concept")

        call_params = mock_get.call_args
        # The params dict is passed as keyword arg
        params = call_params[1].get("params") or call_params.kwargs.get("params", {})
        assert params.get("fs") == "m:90+t:3"
