"""The slope up to the staleness cliff."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import BadArgument
from legvise.market.decay import (
    confidence_at,
    confidence_in,
    scaled_size,
    skew_penalty,
    worst_of,
)
from legvise.model.book import Book
from legvise.money import dec
from tests.conftest import make_venue

AT = dt.datetime(2026, 3, 10, 9, 0, tzinfo=dt.UTC)
VENUE = make_venue("kraken", staleness_budget_ms=1000)


def a_book(venue: str = "kraken", *, offset_ms: int = 0) -> Book:
    return Book.build(
        venue,
        "BTC-USD",
        observed_at=AT + dt.timedelta(milliseconds=offset_ms),
        bids=(("99", "1"),),
        asks=(("101", "1"),),
    )


def test_a_book_stamped_now_is_believed_in_full() -> None:
    found = confidence_in(a_book(), VENUE, AT)
    assert found.factor == dec("1")
    assert found.is_fresh
    assert not found.is_spent


def test_a_book_halfway_through_its_budget_is_half_believed() -> None:
    found = confidence_in(a_book(), VENUE, AT + dt.timedelta(milliseconds=500))
    assert found.factor == dec("0.5")
    assert not found.is_fresh
    assert not found.is_spent


def test_a_book_at_its_budget_is_spent() -> None:
    found = confidence_in(a_book(), VENUE, AT + dt.timedelta(milliseconds=1000))
    assert found.factor == dec("0")
    assert found.is_spent


def test_a_book_past_its_budget_stays_at_nothing() -> None:
    assert confidence_in(a_book(), VENUE, AT + dt.timedelta(seconds=10)).factor == dec("0")


def test_a_book_stamped_in_the_future_is_believed_in_full() -> None:
    assert confidence_in(a_book(offset_ms=500), VENUE, AT).is_fresh


def test_the_confidence_carries_the_age_and_the_budget() -> None:
    found = confidence_in(a_book(), VENUE, AT + dt.timedelta(milliseconds=250))
    assert found.age_ms == 250
    assert found.budget_ms == 1000


def test_a_tighter_budget_decays_the_same_book_faster() -> None:
    tight = make_venue("kraken", staleness_budget_ms=500)
    now = AT + dt.timedelta(milliseconds=250)
    assert confidence_in(a_book(), tight, now).factor < confidence_in(a_book(), VENUE, now).factor


def test_a_budget_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        confidence_at(10, 0)
    assert caught.value.field == "budget_ms"


def test_the_slope_can_be_read_from_two_numbers() -> None:
    assert confidence_at(250, 1000).factor == dec("0.75")


def test_scaling_a_size_takes_the_decay_off_it() -> None:
    found = confidence_at(500, 1000)
    assert scaled_size(dec("10"), found) == dec("5")


def test_scaling_a_size_by_a_fresh_book_changes_nothing() -> None:
    assert scaled_size(dec("10"), confidence_at(0, 1000)) == dec("10")


def test_a_negative_size_is_refused() -> None:
    with pytest.raises(BadArgument):
        scaled_size(dec("-1"), confidence_at(0, 1000))


def test_the_worse_of_two_books_is_the_one_that_counts() -> None:
    fresh = confidence_at(0, 1000)
    tired = confidence_at(900, 1000)
    assert worst_of(fresh, tired) is tired
    assert worst_of(tired, fresh) is tired


def test_two_equally_believable_books_pick_the_first() -> None:
    first = confidence_at(100, 1000)
    second = confidence_at(100, 1000)
    assert worst_of(first, second) is first


def test_two_books_sharing_a_stamp_cost_nothing_to_pair() -> None:
    assert skew_penalty(a_book(), a_book("okx"), 500) == dec("0")


def test_two_books_a_whole_window_apart_cost_everything() -> None:
    assert skew_penalty(a_book(), a_book("okx", offset_ms=500), 500) == dec("1")


def test_a_pair_part_way_through_the_window_costs_part_of_it() -> None:
    assert skew_penalty(a_book(), a_book("okx", offset_ms=125), 500) == dec("0.25")


def test_the_penalty_does_not_care_which_book_came_first() -> None:
    forward = skew_penalty(a_book(), a_book("okx", offset_ms=200), 500)
    backward = skew_penalty(a_book("okx", offset_ms=200), a_book(), 500)
    assert forward == backward


def test_a_pairing_window_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        skew_penalty(a_book(), a_book("okx"), 0)
