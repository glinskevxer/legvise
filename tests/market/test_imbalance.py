"""Which way a book leans, at the touch and deeper."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import BadArgument, Refused
from legvise.market.imbalance import (
    Imbalance,
    depth_imbalance,
    disagreement,
    imbalance_at,
    leans_toward,
    touch_imbalance,
)
from legvise.model.book import Book, Side
from legvise.money import dec

AT = dt.datetime(2026, 2, 24, 9, 0, tzinfo=dt.UTC)
WIDE = dec("500")


def book(bids: tuple[tuple[str, str], ...], asks: tuple[tuple[str, str], ...]) -> Book:
    return Book.build("kraken", "BTC-USD", observed_at=AT, bids=bids, asks=asks)


BALANCED = book((("99", "10"),), (("101", "10"),))
BID_HEAVY = book((("99", "30"),), (("101", "10"),))
ASK_HEAVY = book((("99", "10"),), (("101", "30"),))


def test_a_balanced_touch_reads_as_nothing() -> None:
    found = touch_imbalance(BALANCED)
    assert found.ratio == dec("0")
    assert found.is_balanced
    assert not found.leans_bid


def test_a_bid_heavy_touch_reads_positive() -> None:
    found = touch_imbalance(BID_HEAVY)
    assert found.ratio == dec("0.5")
    assert found.leans_bid


def test_an_ask_heavy_touch_reads_negative() -> None:
    assert touch_imbalance(ASK_HEAVY).ratio == dec("-0.5")


def test_the_ratio_never_leaves_the_range() -> None:
    lopsided = book((("99", "1000000"),), (("101", "1"),))
    assert touch_imbalance(lopsided).ratio < dec("1")
    assert touch_imbalance(lopsided).ratio > dec("0.99")


def test_an_imbalance_with_nothing_on_either_side_is_refused() -> None:
    empty = Imbalance(bid_size=dec("0"), ask_size=dec("0"))
    with pytest.raises(BadArgument):
        assert empty.ratio


def test_a_one_sided_book_has_no_imbalance() -> None:
    one_sided = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("99", "1"),))
    with pytest.raises(Refused) as caught:
        touch_imbalance(one_sided)
    assert caught.value.why.startswith("BOOK.02")


def test_the_depth_measure_also_needs_two_sides() -> None:
    one_sided = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("99", "1"),))
    with pytest.raises(Refused):
        depth_imbalance(one_sided, WIDE)


def test_the_depth_measure_reads_the_whole_band() -> None:
    deep = book((("99", "1"), ("98", "50")), (("101", "1"), ("102", "1")))
    assert depth_imbalance(deep, WIDE).bid_size == dec("51")
    assert touch_imbalance(deep).bid_size == dec("1")


def test_a_narrow_band_reads_only_the_touch() -> None:
    deep = book((("99", "1"), ("90", "50")), (("101", "1"), ("110", "50")))
    tight = depth_imbalance(deep, dec("1"))
    assert tight.bid_size == dec("1")
    assert tight.ask_size == dec("1")


def test_both_measures_come_back_together() -> None:
    touch, depth = imbalance_at(BID_HEAVY, WIDE)
    assert touch.ratio == depth.ratio


def test_two_measures_that_agree_are_not_apart() -> None:
    assert disagreement(BID_HEAVY, WIDE) == dec("0")


def test_two_measures_that_disagree_report_the_gap() -> None:
    trap = book((("99", "1"), ("98", "100")), (("101", "50"), ("102", "1")))
    assert disagreement(trap, WIDE) > dec("0.5")


def test_the_gap_is_never_negative() -> None:
    trap = book((("99", "50"), ("98", "1")), (("101", "1"), ("102", "100")))
    assert disagreement(trap, WIDE) > dec("0")


def test_a_book_both_measures_call_bid_heavy_leans_that_way() -> None:
    assert leans_toward(BID_HEAVY, WIDE) is Side.BID


def test_a_book_both_measures_call_ask_heavy_leans_that_way() -> None:
    assert leans_toward(ASK_HEAVY, WIDE) is Side.ASK


def test_a_balanced_book_leans_nowhere() -> None:
    assert leans_toward(BALANCED, WIDE) is None


def test_a_book_the_measures_disagree_about_leans_nowhere() -> None:
    trap = book((("99", "1"), ("98", "100")), (("101", "50"), ("102", "1")))
    assert leans_toward(trap, WIDE) is None
