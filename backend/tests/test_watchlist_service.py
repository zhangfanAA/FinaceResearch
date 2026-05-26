"""Tests for watchlist_service.py CRUD and ocr_service.py code extraction."""

from __future__ import annotations

from typing import Iterator

import pytest

from app.services import database, watchlist_service
from app.services.ocr_service import parse_text_for_codes


# ---- Fixtures ----


@pytest.fixture
def db_conn(tmp_path) -> Iterator:
    conn = database.connect(tmp_path / "watchlist_test.sqlite")
    database.init_db(conn)
    yield conn
    conn.close()


# ---- Watchlist CRUD Tests ----


class TestGetWatchlist:
    def test_returns_empty_when_no_items(self, db_conn):
        result = watchlist_service.get_watchlist(db_conn)
        assert result == []

    def test_returns_all_items(self, db_conn):
        watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "贵州茅台")
        watchlist_service.add_to_watchlist(db_conn, "fund", "000510", "中证A500")
        result = watchlist_service.get_watchlist(db_conn)
        assert len(result) == 2

    def test_filters_by_type_stock(self, db_conn):
        watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "贵州茅台")
        watchlist_service.add_to_watchlist(db_conn, "fund", "000510", "中证A500")
        result = watchlist_service.get_watchlist(db_conn, item_type="stock")
        assert len(result) == 1
        assert result[0]["item_type"] == "stock"

    def test_filters_by_type_fund(self, db_conn):
        watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "贵州茅台")
        watchlist_service.add_to_watchlist(db_conn, "fund", "000510", "中证A500")
        result = watchlist_service.get_watchlist(db_conn, item_type="fund")
        assert len(result) == 1
        assert result[0]["item_type"] == "fund"

    def test_returns_dicts_with_expected_keys(self, db_conn):
        watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "贵州茅台")
        result = watchlist_service.get_watchlist(db_conn)
        item = result[0]
        assert set(item.keys()) == {
            "id", "item_type", "code", "name", "added_at", "sort_order",
            "purchase_amount", "purchase_nav", "purchase_date", "shares",
        }


class TestAddToWatchlist:
    def test_adds_stock_item(self, db_conn):
        item = watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "贵州茅台")
        assert item["item_type"] == "stock"
        assert item["code"] == "600519"
        assert item["name"] == "贵州茅台"
        assert item["id"] is not None
        assert item["sort_order"] == 0

    def test_adds_fund_item(self, db_conn):
        item = watchlist_service.add_to_watchlist(db_conn, "fund", "000510", "中证A500")
        assert item["item_type"] == "fund"
        assert item["code"] == "000510"

    def test_auto_assigns_incrementing_sort_order(self, db_conn):
        i1 = watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "茅台")
        i2 = watchlist_service.add_to_watchlist(db_conn, "stock", "000001", "平安")
        assert i1["sort_order"] == 0
        assert i2["sort_order"] == 1

    def test_dedup_returns_existing_item(self, db_conn):
        first = watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "贵州茅台")
        second = watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "贵州茅台")
        assert first["id"] == second["id"]
        all_items = watchlist_service.get_watchlist(db_conn)
        assert len(all_items) == 1

    def test_same_code_different_type_allowed(self, db_conn):
        stock = watchlist_service.add_to_watchlist(db_conn, "stock", "000510", "A股")
        fund = watchlist_service.add_to_watchlist(db_conn, "fund", "000510", "基金")
        assert stock["id"] != fund["id"]
        assert len(watchlist_service.get_watchlist(db_conn)) == 2

    def test_raises_on_invalid_item_type(self, db_conn):
        with pytest.raises(ValueError, match="item_type"):
            watchlist_service.add_to_watchlist(db_conn, "bond", "123456")

    def test_raises_on_empty_code(self, db_conn):
        with pytest.raises(ValueError, match="code"):
            watchlist_service.add_to_watchlist(db_conn, "stock", "")

    def test_strips_whitespace_from_code(self, db_conn):
        item = watchlist_service.add_to_watchlist(db_conn, "stock", "  600519  ", "茅台")
        assert item["code"] == "600519"

    def test_name_is_none_when_not_provided_and_akshare_unavailable(self, db_conn, monkeypatch):
        """When AkShare is unavailable and no name provided, name should be None."""
        monkeypatch.setattr(
            watchlist_service,
            "_auto_resolve_name",
            lambda item_type, code: None,
        )
        item = watchlist_service.add_to_watchlist(db_conn, "stock", "999999")
        assert item["name"] is None


class TestRemoveFromWatchlist:
    def test_removes_existing_item(self, db_conn):
        item = watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "茅台")
        result = watchlist_service.remove_from_watchlist(db_conn, item["id"])
        assert result is True
        assert watchlist_service.get_watchlist(db_conn) == []

    def test_returns_false_for_nonexistent_id(self, db_conn):
        result = watchlist_service.remove_from_watchlist(db_conn, 9999)
        assert result is False


class TestReorderWatchlist:
    def test_reorder_changes_sort_order(self, db_conn):
        i1 = watchlist_service.add_to_watchlist(db_conn, "stock", "600519", "茅台")
        i2 = watchlist_service.add_to_watchlist(db_conn, "stock", "000001", "平安")
        i3 = watchlist_service.add_to_watchlist(db_conn, "stock", "000858", "五粮液")

        # Reverse order
        watchlist_service.reorder_watchlist(db_conn, [i3["id"], i2["id"], i1["id"]])

        items = watchlist_service.get_watchlist(db_conn)
        assert items[0]["code"] == "000858"
        assert items[0]["sort_order"] == 0
        assert items[1]["code"] == "000001"
        assert items[1]["sort_order"] == 1
        assert items[2]["code"] == "600519"
        assert items[2]["sort_order"] == 2


# ---- OCR / Text Parsing Tests ----


class TestParseTextForCodes:
    def test_extracts_stock_code(self):
        result = parse_text_for_codes("贵州茅台 600519 买入")
        assert len(result) == 1
        assert result[0]["code"] == "600519"
        assert result[0]["item_type"] == "stock"

    def test_extracts_fund_code(self):
        result = parse_text_for_codes("基金代码 000510")
        assert len(result) == 1
        assert result[0]["code"] == "000510"
        # 000 prefix maps to stock by heuristic
        assert result[0]["item_type"] in ("stock", "fund")

    def test_extracts_multiple_codes(self):
        result = parse_text_for_codes("600519 和 000858 五粮液 300750")
        assert len(result) == 3
        codes = {r["code"] for r in result}
        assert codes == {"600519", "000858", "300750"}

    def test_deduplicates_codes(self):
        result = parse_text_for_codes("600519 茅台 600519 再次")
        assert len(result) == 1

    def test_returns_empty_for_no_codes(self):
        result = parse_text_for_codes("no codes here")
        assert result == []

    def test_returns_empty_for_empty_string(self):
        result = parse_text_for_codes("")
        assert result == []

    def test_returns_empty_for_none(self):
        result = parse_text_for_codes(None)
        assert result == []

    def test_classifies_chinext_as_stock(self):
        result = parse_text_for_codes("300750 宁德时代")
        assert len(result) == 1
        assert result[0]["item_type"] == "stock"

    def test_classifies_star_market_as_stock(self):
        result = parse_text_for_codes("688001 科创")
        assert len(result) == 1
        assert result[0]["item_type"] == "stock"


class TestDatabaseWatchlistHelpers:
    """Direct tests for database-level watchlist CRUD helpers."""

    def test_insert_and_get(self, db_conn):
        item_id = database.insert_watchlist_item(
            db_conn, "stock", "600519", "茅台", "2026-05-25T10:00:00", 0
        )
        assert item_id > 0
        rows = database.get_watchlist(db_conn)
        assert len(rows) == 1
        assert rows[0]["code"] == "600519"

    def test_insert_duplicate_raises_integrity_error(self, db_conn):
        database.insert_watchlist_item(
            db_conn, "stock", "600519", "茅台", "2026-05-25T10:00:00", 0
        )
        with pytest.raises(Exception):
            database.insert_watchlist_item(
                db_conn, "stock", "600519", "茅台", "2026-05-25T10:00:01", 1
            )

    def test_delete_existing_returns_true(self, db_conn):
        item_id = database.insert_watchlist_item(
            db_conn, "stock", "600519", "茅台", "2026-05-25T10:00:00", 0
        )
        assert database.delete_watchlist_item(db_conn, item_id) is True
        assert database.get_watchlist(db_conn) == []

    def test_delete_nonexistent_returns_false(self, db_conn):
        assert database.delete_watchlist_item(db_conn, 999) is False

    def test_update_sort_order(self, db_conn):
        id1 = database.insert_watchlist_item(
            db_conn, "stock", "600519", "茅台", "2026-05-25T10:00:00", 0
        )
        id2 = database.insert_watchlist_item(
            db_conn, "stock", "000001", "平安", "2026-05-25T10:00:01", 1
        )
        database.update_watchlist_sort_order(db_conn, [id2, id1])
        rows = database.get_watchlist(db_conn)
        assert rows[0]["code"] == "000001"
        assert rows[0]["sort_order"] == 0
        assert rows[1]["code"] == "600519"
        assert rows[1]["sort_order"] == 1

    def test_get_by_code(self, db_conn):
        database.insert_watchlist_item(
            db_conn, "stock", "600519", "茅台", "2026-05-25T10:00:00", 0
        )
        found = database.get_watchlist_item_by_code(db_conn, "stock", "600519")
        assert found is not None
        assert found["code"] == "600519"

    def test_get_by_code_not_found(self, db_conn):
        assert database.get_watchlist_item_by_code(db_conn, "stock", "999999") is None
