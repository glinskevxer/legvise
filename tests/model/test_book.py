"""What a book snapshot refuses, and which clause it quotes when it does."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from legvise.errors import BadArgument, Refused
from legvise.model.book import Book, Level, Side

AT = dt.datetime(2025, 4, 2, 14, 0, tzinfo=dt.UTC)

BIDS = (("100.0", "2"), ("99.9", "5"), ("99.8", "12"))
ASKS = (("100.1", "3"), ("100.2", "7"), ("100.4", "20"))


def a_book(**changes: object) -> Book:
    fields: dict[str, object] = {
        "venue": "kraken",
        "symbol": "BTC-USD",
        "observed_at": AT,
        "bids": BIDS,
        "asks": ASKS,
    }
    fields.update(changes)
    return Book.build(**fields)  # type: ignore[arg-type]


def test_a_level_knows_what_it_is_worth() -> None:
    assert Level.build("100.5", "2").notional == Decimal("201.0")


@pytest.mark.parametrize(("price", "size"), [("0", "1"), ("1", "0"), ("-1", "1"), ("1", "-1")])
def test_a_level_has_to_carry_a_positive_price_and_size(price: str, size: str) -> None:
    with pytest.raises(Refused) as caught:
        Level.build(price, size)
    assert caught.value.why.startswith("BOOK.03")


def test_the_touch_is_the_first_level_on_each_side() -> None:
    book = a_book()
    assert book.touch(Side.BID).price == Decimal("100.0")
    assert book.touch(Side.ASK).price == Decimal("100.1")


def test_the_best_levels_are_available_without_raising() -> None:
    book = a_book()
    assert book.best_bid is not None
    assert book.best_ask is not None
    assert book.best_bid.size == Decimal("2")


def test_an_empty_side_answers_nothing_rather_than_raising() -> None:
    book = a_book(asks=())
    assert book.best_ask is None
    assert not book.is_two_sided()


def test_asking_for_the_touch_of_an_empty_side_quotes_the_clause() -> None:
    with pytest.raises(Refused) as caught:
        a_book(asks=()).touch(Side.ASK)
    assert caught.value.why.startswith("BOOK.02")


def test_bids_out_of_order_are_refused() -> None:
    with pytest.raises(Refused) as caught:
        a_book(bids=(("99.9", "1"), ("100.0", "1")))
    assert caught.value.why.startswith("BOOK.01")


def test_asks_out_of_order_are_refused() -> None:
    with pytest.raises(Refused) as caught:
        a_book(asks=(("100.4", "1"), ("100.2", "1")))
    assert caught.value.why.startswith("BOOK.01")


def test_two_levels_at_the_same_price_are_out_of_order() -> None:
    with pytest.raises(Refused):
        a_book(bids=(("100.0", "1"), ("100.0", "1")))


def test_a_crossed_book_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        a_book(bids=(("100.5", "1"),), asks=(("100.1", "1"),))
    assert caught.value.why.startswith("BOOK.04")


def test_a_locked_book_is_refused_as_well() -> None:
    with pytest.raises(Refused) as caught:
        a_book(bids=(("100.1", "1"),), asks=(("100.1", "1"),))
    assert caught.value.why.startswith("BOOK.04")


def test_a_one_sided_book_cannot_be_crossed() -> None:
    assert a_book(bids=()).best_bid is None


def test_a_naive_observation_time_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_book(observed_at=dt.datetime(2025, 4, 2, 14, 0))


def test_a_negative_sequence_number_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_book(sequence=-1)


def test_a_venue_code_is_normalised_on_the_way_in() -> None:
    assert a_book(venue=" Kraken ").venue == "kraken"


def test_sides_are_addressable_by_the_enum() -> None:
    book = a_book()
    assert book.side(Side.BID) == book.bids
    assert book.side(Side.ASK) == book.asks


def test_a_side_knows_its_opposite() -> None:
    assert Side.BID.other is Side.ASK
    assert Side.ASK.other is Side.BID
    assert Side.BID.takes is Side.ASK


def test_a_book_is_immutable() -> None:
    book = a_book()
    with pytest.raises(AttributeError):
        book.sequence = 4  # type: ignore[misc]
