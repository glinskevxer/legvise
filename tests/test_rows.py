"""Pulling typed values out of a row, and refusing the ones that are wrong."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from legvise.errors import BadArgument
from legvise.ids import Symbol
from legvise.rows import (
    as_bool,
    as_decimal,
    as_int,
    as_optional_text,
    as_symbol,
    as_text,
    flag,
    has_column,
)


def one(sql: str) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row: sqlite3.Row | None = conn.execute(sql).fetchone()
    assert row is not None
    return row


def test_a_column_the_query_selected_is_present() -> None:
    row = one("SELECT 'kraken' AS code")
    assert has_column(row, "code")
    assert not has_column(row, "name")


def test_asking_for_a_column_the_query_did_not_select_is_refused() -> None:
    row = one("SELECT 'kraken' AS code")
    with pytest.raises(BadArgument) as caught:
        as_text(row, "display_name")
    assert caught.value.why == "the query did not select it"


def test_text_comes_back_as_text() -> None:
    assert as_text(one("SELECT 'kraken' AS code"), "code") == "kraken"


def test_a_null_in_a_not_null_column_is_refused() -> None:
    with pytest.raises(BadArgument):
        as_text(one("SELECT NULL AS code"), "code")


def test_an_optional_column_may_be_null() -> None:
    assert as_optional_text(one("SELECT NULL AS note"), "note") is None
    assert as_optional_text(one("SELECT 'hi' AS note"), "note") == "hi"


def test_an_optional_column_still_refuses_the_wrong_type() -> None:
    with pytest.raises(BadArgument):
        as_optional_text(one("SELECT 4 AS note"), "note")


def test_an_integer_comes_back_as_an_integer() -> None:
    assert as_int(one("SELECT 750 AS budget"), "budget") == 750


def test_text_in_an_integer_column_is_refused() -> None:
    with pytest.raises(BadArgument):
        as_int(one("SELECT 'many' AS budget"), "budget")


def test_a_flag_column_reads_as_a_boolean() -> None:
    assert as_bool(one("SELECT 1 AS active"), "active") is True
    assert as_bool(one("SELECT 0 AS active"), "active") is False


def test_a_flag_column_holding_anything_else_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        as_bool(one("SELECT 2 AS active"), "active")
    assert "0 or 1" in caught.value.why


def test_a_decimal_column_keeps_its_scale() -> None:
    value = as_decimal(one("SELECT '0.00000001' AS size"), "size")
    assert value == Decimal("0.00000001")
    assert str(value) == "1E-8"


def test_a_decimal_column_holding_junk_is_refused() -> None:
    with pytest.raises(BadArgument):
        as_decimal(one("SELECT 'about ten' AS size"), "size")


def test_a_decimal_column_holding_infinity_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        as_decimal(one("SELECT 'Infinity' AS size"), "size")
    assert caught.value.why == "must be finite"


def test_a_symbol_column_parses_into_a_symbol() -> None:
    assert as_symbol(one("SELECT 'BTC-USDT' AS symbol"), "symbol") == Symbol("BTC", "USDT")


def test_a_symbol_column_holding_a_venue_spelling_is_refused() -> None:
    with pytest.raises(BadArgument):
        as_symbol(one("SELECT 'BTCUSDT' AS symbol"), "symbol")


def test_a_boolean_going_the_other_way_becomes_an_integer() -> None:
    assert flag(True) == 1
    assert flag(False) == 0
