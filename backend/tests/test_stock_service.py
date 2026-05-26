"""Tests for stock_service.py data layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import pandas as pd
import pytest

from app.services import database, stock_service


@pytest.fixture
def db_conn(tmp_path) -> Iterator:
    conn = database.connect(tmp_path / "test.sqlite")
    database.init_db(conn)
    yield conn
    conn.close()


class TestStockQuoteDataclass:
    def test_stock_quote_creation(self):
        q = stock_service.StockQuote(
            stock_code="600519",
            stock_name="贵州茅台",
            current_price=1800.0,
            open_price=1790.0,
            high_price=1810.0,
            low_price=1780.0,
            prev_close=1795.0,
            volume=100000.0,
            amount=1800000000.0,
            change_pct=0.28,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        assert q.stock_code == "600519"
        assert q.stock_name == "贵州茅台"
        assert q.change_pct == 0.28


class TestSectorQuoteDataclass:
    def test_sector_quote_creation(self):
        s = stock_service.SectorQuote(
            sector_code="BK0001",
            sector_name="半导体",
            sector_type="industry",
            change_pct=3.5,
            turnover_rate=2.1,
            leading_stock="中芯国际",
            rise_count=50,
            fall_count=10,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        assert s.sector_name == "半导体"
        assert s.sector_type == "industry"
        assert s.change_pct == 3.5


class TestCacheStockQuotes:
    def test_cache_and_retrieve_stock_quotes(self, db_conn):
        now = datetime.now(timezone.utc).isoformat()
        quotes = [
            stock_service.StockQuote(
                stock_code="600519",
                stock_name="贵州茅台",
                current_price=1800.0,
                open_price=1790.0,
                high_price=1810.0,
                low_price=1780.0,
                prev_close=1795.0,
                volume=100000.0,
                amount=1800000000.0,
                change_pct=0.28,
                fetched_at=now,
            )
        ]
        stock_service.cache_stock_quotes(db_conn, quotes)
        cached = stock_service.get_cached_stock_quotes(db_conn)
        assert len(cached) == 1
        assert cached[0]["stock_code"] == "600519"
        assert cached[0]["current_price"] == 1800.0

    def test_cache_upsert_updates_existing(self, db_conn):
        now = datetime.now(timezone.utc).isoformat()
        quotes_v1 = [
            stock_service.StockQuote(
                stock_code="000001",
                stock_name="平安银行",
                current_price=10.0,
                open_price=10.0,
                high_price=10.5,
                low_price=9.8,
                prev_close=10.0,
                volume=50000.0,
                amount=500000.0,
                change_pct=0.0,
                fetched_at=now,
            )
        ]
        stock_service.cache_stock_quotes(db_conn, quotes_v1)

        now2 = datetime.now(timezone.utc).isoformat()
        quotes_v2 = [
            stock_service.StockQuote(
                stock_code="000001",
                stock_name="平安银行",
                current_price=10.5,
                open_price=10.0,
                high_price=10.8,
                low_price=9.8,
                prev_close=10.0,
                volume=60000.0,
                amount=630000.0,
                change_pct=5.0,
                fetched_at=now2,
            )
        ]
        stock_service.cache_stock_quotes(db_conn, quotes_v2)

        cached = stock_service.get_cached_stock_quotes(db_conn)
        assert len(cached) == 1
        assert cached[0]["current_price"] == 10.5
        assert cached[0]["change_pct"] == 5.0

    def test_cache_returns_empty_for_stale_data(self, db_conn):
        from datetime import timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        quotes = [
            stock_service.StockQuote(
                stock_code="600519",
                stock_name="贵州茅台",
                current_price=1800.0,
                open_price=1790.0,
                high_price=1810.0,
                low_price=1780.0,
                prev_close=1795.0,
                volume=100000.0,
                amount=1800000000.0,
                change_pct=0.28,
                fetched_at=old_time,
            )
        ]
        stock_service.cache_stock_quotes(db_conn, quotes)
        cached = stock_service.get_cached_stock_quotes(db_conn, max_age_seconds=60)
        assert len(cached) == 0


class TestCacheSectorQuotes:
    def test_cache_and_retrieve_sector_quotes(self, db_conn):
        now = datetime.now(timezone.utc).isoformat()
        quotes = [
            stock_service.SectorQuote(
                sector_code="BK0001",
                sector_name="半导体",
                sector_type="industry",
                change_pct=3.5,
                turnover_rate=2.1,
                leading_stock="中芯国际",
                rise_count=50,
                fall_count=10,
                fetched_at=now,
            )
        ]
        stock_service.cache_sector_quotes(db_conn, quotes)
        cached = stock_service.get_cached_sector_quotes(db_conn, sector_type="industry")
        assert len(cached) == 1
        assert cached[0]["sector_name"] == "半导体"

    def test_sector_type_filter(self, db_conn):
        now = datetime.now(timezone.utc).isoformat()
        quotes = [
            stock_service.SectorQuote(
                sector_code="BK0001",
                sector_name="半导体",
                sector_type="industry",
                change_pct=3.5,
                turnover_rate=2.1,
                leading_stock="中芯国际",
                rise_count=50,
                fall_count=10,
                fetched_at=now,
            ),
            stock_service.SectorQuote(
                sector_code="GN0001",
                sector_name="AI概念",
                sector_type="concept",
                change_pct=5.0,
                turnover_rate=3.0,
                leading_stock="科大讯飞",
                rise_count=30,
                fall_count=5,
                fetched_at=now,
            ),
        ]
        stock_service.cache_sector_quotes(db_conn, quotes)

        industry = stock_service.get_cached_sector_quotes(db_conn, sector_type="industry")
        concept = stock_service.get_cached_sector_quotes(db_conn, sector_type="concept")
        assert len(industry) == 1
        assert len(concept) == 1
        assert industry[0]["sector_name"] == "半导体"
        assert concept[0]["sector_name"] == "AI概念"


class TestComputeTechnicalIndicators:
    def test_compute_indicators_with_valid_data(self):
        import numpy as np

        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        close = pd.Series(np.linspace(100, 150, 100) + np.random.randn(100) * 2)
        df = pd.DataFrame({
            "date": dates,
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": pd.Series(np.random.randint(10000, 100000, 100).astype(float)),
        })

        result = stock_service.compute_technical_indicators(df)

        assert "ma5" in result
        assert "ma10" in result
        assert "ma20" in result
        assert "ma60" in result
        assert "rsi_14" in result
        assert "macd" in result
        assert "macd_signal" in result
        assert "macd_hist" in result

    def test_compute_indicators_with_empty_df(self):
        df = pd.DataFrame()
        result = stock_service.compute_technical_indicators(df)
        assert result == {}


class TestSafeHelpers:
    def test_safe_float_with_valid_value(self):
        assert stock_service._safe_float(3.14) == 3.14
        assert stock_service._safe_float(42) == 42.0
        assert stock_service._safe_float("1.5") == 1.5

    def test_safe_float_with_none(self):
        assert stock_service._safe_float(None) == 0.0
        assert stock_service._safe_float(None, default=99.0) == 99.0

    def test_safe_float_with_nan(self):
        assert stock_service._safe_float(float("nan")) == 0.0

    def test_safe_str_with_valid_value(self):
        assert stock_service._safe_str("hello") == "hello"
        assert stock_service._safe_str(42) == "42"

    def test_safe_str_with_none(self):
        assert stock_service._safe_str(None) == ""
        assert stock_service._safe_str(None, default="N/A") == "N/A"


class TestLogAnalysis:
    def test_log_analysis_inserts_entry(self, db_conn):
        stock_service.log_analysis(
            db_conn,
            analysis_type="stock_sector",
            target_code="半导体",
            target_name="半导体",
            llm_prompt="test prompt",
            llm_raw_output="test output",
            parsed_result='{"trend":"bullish"}',
        )
        rows = db_conn.execute("SELECT * FROM analysis_logs").fetchall()
        assert len(rows) == 1
        assert rows[0]["analysis_type"] == "stock_sector"
        assert rows[0]["target_code"] == "半导体"
