"""Touch arithmetic, and the optimistic number a scan filters on."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import Refused
from legvise.market.spread import (
    crosses,
    microprice,
    mid,
    raw_cross_bps,
    spread_bps,
    touch_of,
    two_sided,
)
from legvise.model.book import Book, Side
from legvise.money import dec

AT = dt.datetime(2025, 4, 8, 11, 0, tzinfo=dt.UTC)


def book(venue: str, bid: str, ask: str, *, symbol: str = "BTC-USD", sizes: str = "1") -> Book:
    return Book.build(
        venue,
        symbol,
        observed_at=AT,
        bids=((bid, sizes),),
        asks=((ask, sizes),),
    )


def test_the_touch_carries_a_price_and_a_size() -> None:
    found = touch_of(book("kraken", "100", "101"), Side.BID)
    assert found.price == dec("100")
    assert found.size == dec("1")


def test_both_touches_come_back_together() -> None:
    sides = two_sided(book("kraken", "100", "101"))
    assert sides.bid.price == dec("100")
    assert sides.ask.price == dec("101")
    assert sides.spread == dec("1")


def test_the_mid_sits_halfway_between_the_touches() -> None:
    assert mid(book("kraken", "100", "101")) == dec("100.5")


def test_a_one_sided_book_has_no_mid() -> None:
    one_sided = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("100", "1"),))
    with pytest.raises(Refused) as caught:
        mid(one_sided)
    assert caught.value.why.startswith("BOOK.02")


def test_the_spread_reads_in_basis_points_of_the_mid() -> None:
    assert spread_bps(book("kraken", "99.95", "100.05")) == dec("10")


def test_a_tighter_book_reads_narrower() -> None:
    wide = spread_bps(book("kraken", "99.5", "100.5"))
    tight = spread_bps(book("kraken", "99.95", "100.05"))
    assert tight < wide


def test_the_microprice_matches_the_mid_when_the_sizes_match() -> None:
    balanced = book("kraken", "100", "101")
    assert microprice(balanced) == mid(balanced)


def test_the_microprice_leans_toward_the_thin_side() -> None:
    heavy_bid = Book.build(
        "kraken",
        "BTC-USD",
        observed_at=AT,
        bids=(("100", "40"),),
        asks=(("101", "1"),),
    )
    assert microprice(heavy_bid) > mid(heavy_bid)


def test_two_books_that_cross_read_positive() -> None:
    cheap = book("kraken", "99.0", "99.5")
    rich = book("okx", "100.0", "100.5")
    assert raw_cross_bps(cheap, rich) > dec("0")
    assert crosses(cheap, rich)


def test_the_same_pair_the_other_way_round_reads_negative() -> None:
    cheap = book("kraken", "99.0", "99.5")
    rich = book("okx", "100.0", "100.5")
    assert raw_cross_bps(rich, cheap) < dec("0")
    assert not crosses(rich, cheap)


def test_two_books_that_do_not_cross_are_not_an_error() -> None:
    assert raw_cross_bps(book("kraken", "100", "101"), book("okx", "100", "101")) < dec("0")


def test_the_edge_is_measured_from_the_ask_paid_to_the_bid_hit() -> None:
    cheap = book("kraken", "99.0", "100.0")
    rich = book("okx", "101.0", "102.0")
    assert raw_cross_bps(cheap, rich) == dec("100")


def test_comparing_two_different_markets_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        raw_cross_bps(book("kraken", "100", "101"), book("okx", "10", "11", symbol="SOL-USD"))
    assert caught.value.why.startswith("EDGE.02")


def test_a_book_with_no_ask_cannot_be_bought_from() -> None:
    no_ask = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("100", "1"),))
    with pytest.raises(Refused):
        raw_cross_bps(no_ask, book("okx", "100", "101"))
