"""Tests for fund_service.py data layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

from app.services import database, fund_service


@pytest.fixture
def db_conn(tmp_path) -> Iterator:
    conn = database.connect(tmp_path / "test.sqlite")
    database.init_db(conn)
    yield conn
    conn.close()


class TestFundNavDataclass:
    def test_fund_nav_creation(self):
        nav = fund_service.FundNav(
            fund_code="000510",
            fund_name="中证A500",
            nav=1.08,
            acc_nav=1.08,
            nav_date="2026-05-25",
            daily_return=0.5,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        assert nav.fund_code == "000510"
        assert nav.nav == 1.08
        assert nav.daily_return == 0.5


class TestFundNewsDataclass:
    def test_fund_news_creation(self):
        news = fund_service.FundNews(
            title="半导体行业利好",
            source="东方财富",
            publish_time="2026-05-25",
            url="https://example.com/news",
            summary="半导体行业迎来政策利好",
        )
        assert news.title == "半导体行业利好"
        assert news.source == "东方财富"


class TestCacheFundNav:
    def test_cache_and_retrieve_fund_nav(self, db_conn):
        now = datetime.now(timezone.utc).isoformat()
        navs = [
            fund_service.FundNav(
                fund_code="000510",
                fund_name="中证A500",
                nav=1.08,
                acc_nav=1.08,
                nav_date="2026-05-25",
                daily_return=0.5,
                fetched_at=now,
            )
        ]
        fund_service.cache_fund_nav(db_conn, navs)
        cached = fund_service.get_cached_fund_navs(db_conn)
        assert len(cached) == 1
        assert cached[0]["fund_code"] == "000510"
        assert cached[0]["nav"] == 1.08

    def test_cache_upsert_updates_existing(self, db_conn):
        now = datetime.now(timezone.utc).isoformat()
        navs_v1 = [
            fund_service.FundNav(
                fund_code="000510",
                fund_name="中证A500",
                nav=1.08,
                acc_nav=1.08,
                nav_date="2026-05-25",
                daily_return=0.5,
                fetched_at=now,
            )
        ]
        fund_service.cache_fund_nav(db_conn, navs_v1)

        now2 = datetime.now(timezone.utc).isoformat()
        navs_v2 = [
            fund_service.FundNav(
                fund_code="000510",
                fund_name="中证A500",
                nav=1.10,
                acc_nav=1.10,
                nav_date="2026-05-26",
                daily_return=1.85,
                fetched_at=now2,
            )
        ]
        fund_service.cache_fund_nav(db_conn, navs_v2)

        cached = fund_service.get_cached_fund_navs(db_conn)
        assert len(cached) == 1
        assert cached[0]["nav"] == 1.10
        assert cached[0]["daily_return"] == 1.85

    def test_cache_returns_empty_for_stale_data(self, db_conn):
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        navs = [
            fund_service.FundNav(
                fund_code="000510",
                fund_name="中证A500",
                nav=1.08,
                acc_nav=1.08,
                nav_date="2026-05-25",
                daily_return=0.5,
                fetched_at=old_time,
            )
        ]
        fund_service.cache_fund_nav(db_conn, navs)
        cached = fund_service.get_cached_fund_navs(db_conn, max_age_seconds=300)
        assert len(cached) == 0

    def test_cache_returns_fresh_data_within_ttl(self, db_conn):
        recent_time = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
        navs = [
            fund_service.FundNav(
                fund_code="000510",
                fund_name="中证A500",
                nav=1.08,
                acc_nav=1.08,
                nav_date="2026-05-25",
                daily_return=0.5,
                fetched_at=recent_time,
            )
        ]
        fund_service.cache_fund_nav(db_conn, navs)
        cached = fund_service.get_cached_fund_navs(db_conn, max_age_seconds=300)
        assert len(cached) == 1


class TestSafeHelpers:
    def test_safe_float_with_valid_value(self):
        assert fund_service._safe_float(3.14) == 3.14
        assert fund_service._safe_float("1.5") == 1.5

    def test_safe_float_with_none(self):
        assert fund_service._safe_float(None) == 0.0
        assert fund_service._safe_float(None, default=99.0) == 99.0

    def test_safe_str_with_valid_value(self):
        assert fund_service._safe_str("hello") == "hello"

    def test_safe_str_with_none(self):
        assert fund_service._safe_str(None) == ""
        assert fund_service._safe_str(None, default="N/A") == "N/A"


class TestFetchFundNavBatch:
    def test_fetch_fund_nav_batch_with_empty_list(self):
        result = fund_service.fetch_fund_nav_batch([])
        assert result == []

    def test_fetch_fund_nav_batch_with_whitespace_codes(self):
        result = fund_service.fetch_fund_nav_batch(["", "  ", ""])
        assert result == []


class TestFundServiceValidation:
    def test_fetch_fund_nav_rejects_empty_code(self):
        with pytest.raises(ValueError, match="must not be empty"):
            fund_service.fetch_fund_nav("")

    def test_fetch_fund_nav_history_rejects_empty_code(self):
        with pytest.raises(ValueError, match="must not be empty"):
            fund_service.fetch_fund_nav_history("")

    def test_fetch_fund_basic_info_rejects_empty_code(self):
        with pytest.raises(ValueError, match="must not be empty"):
            fund_service.fetch_fund_basic_info("")

    def test_fetch_fund_news_returns_empty_for_empty_code(self):
        result = fund_service.fetch_fund_news("")
        assert result == []
