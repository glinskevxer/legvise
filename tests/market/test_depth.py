"""Sweeping a book: what a walk gets, and where it refuses."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from legvise.errors import BadArgument, Refused
from legvise.market.depth import (
    reachable,
    slippage_bps,
    sweep_cost,
    walk,
    walk_for_notional,
)
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


# Relationships a walk has to satisfy whatever the book and the size are.

LADDER = Book.build(
    "kraken",
    "BTC-USD",
    observed_at=AT,
    bids=(("100.00", "1"), ("99.50", "2"), ("99.00", "4"), ("95.00", "8")),
    asks=(("100.50", "1"), ("101.00", "2"), ("102.00", "4"), ("110.00", "8")),
)

TARGETS = ("0.25", "1", "1.5", "3", "6", "7", "14", "15")
LIMITS = ("1", "50", "100", "300", "1000", "5000")


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_a_walk_never_takes_more_than_it_was_asked_for(target: str, side: Side) -> None:
    assert walk(LADDER, side, dec(target)).size <= dec(target)


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_a_complete_walk_took_exactly_what_it_was_asked_for(target: str, side: Side) -> None:
    got = walk(LADDER, side, dec(target))
    if got.complete:
        assert got.size == dec(target)


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_a_walk_that_got_something_has_an_average_inside_the_book(target: str, side: Side) -> None:
    got = walk(LADDER, side, dec(target))
    if got.is_empty:
        return
    touch = LADDER.touch(side).price
    if side is Side.ASK:
        assert touch <= got.vwap <= got.worst_price
    else:
        assert got.worst_price <= got.vwap <= touch


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_a_bigger_walk_never_gets_less(target: str, side: Side) -> None:
    smaller = walk(LADDER, side, dec(target))
    bigger = walk(LADDER, side, dec(target) + dec("0.5"))
    assert bigger.size >= smaller.size
    assert bigger.levels >= smaller.levels


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_the_slippage_of_a_walk_never_reads_negative(target: str, side: Side) -> None:
    got = walk(LADDER, side, dec(target))
    if not got.is_empty:
        assert slippage_bps(LADDER, got) >= dec("0")


@pytest.mark.parametrize("limit", LIMITS)
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_a_wider_limit_never_reaches_less(limit: str, side: Side) -> None:
    tight = reachable(LADDER, side, dec(limit))
    wide = reachable(LADDER, side, dec(limit) + dec("50"))
    assert wide.size >= tight.size


@pytest.mark.parametrize("limit", LIMITS)
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_what_is_reachable_never_exceeds_the_whole_side(limit: str, side: Side) -> None:
    whole = sum((level.size for level in LADDER.side(side)), start=dec("0"))
    assert reachable(LADDER, side, dec(limit)).size <= whole


@pytest.mark.parametrize("budget", ["10", "100", "150.5", "500", "2000", "10000"])
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_a_budget_walk_never_spends_more_than_the_budget(budget: str, side: Side) -> None:
    assert walk_for_notional(LADDER, side, dec(budget)).notional <= dec(budget)


@pytest.mark.parametrize("budget", ["10", "100", "150.5", "500", "2000"])
@pytest.mark.parametrize("side", [Side.BID, Side.ASK])
def test_a_complete_budget_walk_spent_the_whole_budget(budget: str, side: Side) -> None:
    got = walk_for_notional(LADDER, side, dec(budget))
    if got.complete:
        assert got.notional == dec(budget)


@pytest.mark.parametrize("budget", ["10", "100", "500", "2000"])
def test_the_two_walks_agree_about_what_a_size_costs(budget: str) -> None:
    by_budget = walk_for_notional(LADDER, Side.ASK, dec(budget))
    if not by_budget.complete:
        return
    by_size = walk(LADDER, Side.ASK, by_budget.size)
    assert abs(by_size.notional - by_budget.notional) < dec("0.00000001")
