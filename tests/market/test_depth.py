"""Sweeping a book: what a walk gets, and where it refuses."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from legvise.errors import BadArgument, Refused
from legvise.market.depth import reachable, slippage_bps, sweep_cost, walk
from legvise.model.book import Book, Side
from legvise.money import dec

AT = dt.datetime(2025, 4, 2, 14, 0, tzinfo=dt.UTC)

BOOK = Book.build(
    "kraken",
    "BTC-USD",
    observed_at=AT,
    bids=(("100.00", "2"), ("99.50", "5"), ("98.00", "10")),
    asks=(("100.50", "1"), ("101.00", "4"), ("104.00", "20")),
)


def test_a_walk_inside_the_touch_pays_the_touch() -> None:
    got = walk(BOOK, Side.ASK, dec("0.5"))
    assert got.size == dec("0.5")
    assert got.notional == dec("50.250")
    assert got.vwap == dec("100.50")
    assert got.levels == 1
    assert got.complete


def test_a_walk_past_the_touch_averages_across_levels() -> None:
    got = walk(BOOK, Side.ASK, dec("3"))
    assert got.size == dec("3")
    assert got.notional == dec("100.50") + dec("2") * dec("101.00")
    assert got.levels == 2
    assert got.worst_price == dec("101.00")


def test_a_walk_bigger_than_the_book_comes_back_incomplete() -> None:
    got = walk(BOOK, Side.ASK, dec("1000"))
    assert not got.complete
    assert got.size == dec("25")
    assert got.levels == 3


def test_a_walk_against_an_empty_side_gets_nothing() -> None:
    empty = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("100", "1"),))
    got = walk(empty, Side.ASK, dec("1"))
    assert got.is_empty
    assert not got.complete


def test_an_empty_sweep_has_no_average_price() -> None:
    empty = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("100", "1"),))
    got = walk(empty, Side.ASK, dec("1"))
    with pytest.raises(BadArgument):
        assert got.vwap


@pytest.mark.parametrize("target", ["0", "-1"])
def test_a_walk_needs_a_positive_size(target: str) -> None:
    with pytest.raises(BadArgument):
        walk(BOOK, Side.ASK, dec(target))


def test_selling_walks_down_the_bids() -> None:
    got = walk(BOOK, Side.BID, dec("4"))
    assert got.worst_price == dec("99.50")
    assert got.notional == dec("2") * dec("100.00") + dec("2") * dec("99.50")


def test_reachable_stops_at_the_price_limit_on_the_ask_side() -> None:
    got = reachable(BOOK, Side.ASK, dec("60"))
    assert got.size == dec("5")
    assert got.levels == 2


def test_reachable_stops_at_the_price_limit_on_the_bid_side() -> None:
    got = reachable(BOOK, Side.BID, dec("60"))
    assert got.size == dec("7")
    assert got.worst_price == dec("99.50")


def test_a_wide_enough_limit_reaches_the_whole_book() -> None:
    assert reachable(BOOK, Side.ASK, dec("1000")).size == dec("25")


def test_a_limit_that_excludes_everything_but_the_touch_still_gets_the_touch() -> None:
    got = reachable(BOOK, Side.ASK, dec("1"))
    assert got.size == dec("1")
    assert got.levels == 1


def test_reachable_needs_a_positive_limit() -> None:
    with pytest.raises(BadArgument):
        reachable(BOOK, Side.ASK, dec("0"))


def test_reachable_against_an_empty_side_gets_nothing() -> None:
    empty = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("100", "1"),))
    assert reachable(empty, Side.ASK, dec("50")).is_empty


def test_a_sweep_inside_the_limit_prices_the_whole_size() -> None:
    got = sweep_cost(BOOK, Side.ASK, dec("3"), dec("60"))
    assert got.size == dec("3")
    assert got.complete


def test_a_sweep_the_book_cannot_fill_quotes_the_depth_clause() -> None:
    with pytest.raises(Refused) as caught:
        sweep_cost(BOOK, Side.ASK, dec("100"), dec("1000"))
    assert caught.value.why.startswith("DEPTH.01")


def test_a_sweep_the_book_can_fill_but_only_too_far_out_quotes_the_other_clause() -> None:
    with pytest.raises(Refused) as caught:
        sweep_cost(BOOK, Side.ASK, dec("20"), dec("60"))
    assert caught.value.why.startswith("DEPTH.02")


def test_slippage_is_measured_from_the_touch_and_never_negative() -> None:
    got = walk(BOOK, Side.ASK, dec("3"))
    assert slippage_bps(BOOK, got) > Decimal("0")


def test_slippage_at_the_touch_is_nothing() -> None:
    got = walk(BOOK, Side.ASK, dec("0.5"))
    assert slippage_bps(BOOK, got) == Decimal("0")


def test_slippage_on_the_bid_side_is_also_positive() -> None:
    got = walk(BOOK, Side.BID, dec("4"))
    assert slippage_bps(BOOK, got) > Decimal("0")
