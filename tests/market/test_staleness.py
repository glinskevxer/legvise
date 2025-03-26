"""The two staleness questions, which are not the same question."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import BadArgument, Refused
from legvise.market.staleness import (
    check_pairing,
    freshness,
    is_fresh,
    require_fresh,
    skew_ms,
)
from legvise.model.book import Book
from tests.conftest import make_venue

AT = dt.datetime(2025, 4, 2, 14, 0, tzinfo=dt.UTC)
VENUE = make_venue("kraken", staleness_budget_ms=750)


def a_book(venue: str = "kraken", *, offset_ms: int = 0) -> Book:
    return Book.build(
        venue,
        "BTC-USD",
        observed_at=AT + dt.timedelta(milliseconds=offset_ms),
        bids=(("100.0", "2"),),
        asks=(("100.1", "3"),),
    )


def test_a_book_stamped_now_has_no_age() -> None:
    measured = freshness(a_book(), VENUE, AT)
    assert measured.age_ms == 0
    assert measured.headroom_ms == 750
    assert measured.within_budget


def test_a_book_inside_the_budget_is_fresh() -> None:
    now = AT + dt.timedelta(milliseconds=700)
    assert is_fresh(a_book(), VENUE, now)
    assert freshness(a_book(), VENUE, now).headroom_ms == 50


def test_a_book_exactly_at_the_budget_is_still_fresh() -> None:
    now = AT + dt.timedelta(milliseconds=750)
    assert is_fresh(a_book(), VENUE, now)


def test_a_book_one_millisecond_past_the_budget_is_not() -> None:
    now = AT + dt.timedelta(milliseconds=751)
    assert not is_fresh(a_book(), VENUE, now)
    assert freshness(a_book(), VENUE, now).headroom_ms == -1


def test_requiring_freshness_quotes_the_clause_when_it_fails() -> None:
    with pytest.raises(Refused) as caught:
        require_fresh(a_book(), VENUE, AT + dt.timedelta(seconds=4))
    assert caught.value.why.startswith("STALE.01")
    assert "4000ms" in caught.value.subject


def test_requiring_freshness_hands_the_measurement_back_when_it_passes() -> None:
    measured = require_fresh(a_book(), VENUE, AT + dt.timedelta(milliseconds=100))
    assert measured.age_ms == 100


def test_a_venue_that_did_not_produce_the_book_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        freshness(a_book("okx"), VENUE, AT)
    assert "this book came from okx" in caught.value.why


def test_a_tighter_budget_makes_the_same_book_stale() -> None:
    tight = make_venue("kraken", staleness_budget_ms=50)
    now = AT + dt.timedelta(milliseconds=100)
    assert is_fresh(a_book(), VENUE, now)
    assert not is_fresh(a_book(), tight, now)


def test_skew_is_the_gap_between_two_observations() -> None:
    assert skew_ms(a_book(), a_book("okx", offset_ms=400)) == 400


def test_skew_does_not_care_which_book_came_first() -> None:
    first = a_book()
    second = a_book("okx", offset_ms=400)
    assert skew_ms(first, second) == skew_ms(second, first)


def test_two_books_inside_the_window_pair_up() -> None:
    assert check_pairing(a_book(), a_book("okx", offset_ms=120), 250) == 120


def test_two_books_outside_the_window_are_refused() -> None:
    with pytest.raises(Refused) as caught:
        check_pairing(a_book(), a_book("okx", offset_ms=400), 250)
    assert caught.value.why.startswith("STALE.02")
    assert "400ms apart" in caught.value.subject


def test_a_pair_that_is_each_fresh_can_still_fail_the_window() -> None:
    now = AT + dt.timedelta(milliseconds=700)
    first = a_book()
    second = a_book("okx", offset_ms=400)
    assert is_fresh(first, VENUE, now)
    assert is_fresh(second, make_venue("okx", staleness_budget_ms=750), now)
    with pytest.raises(Refused):
        check_pairing(first, second, 100)


def test_a_negative_pairing_window_is_refused() -> None:
    with pytest.raises(BadArgument):
        check_pairing(a_book(), a_book("okx"), -1)


def test_a_window_of_zero_demands_the_same_stamp() -> None:
    assert check_pairing(a_book(), a_book("okx"), 0) == 0
    with pytest.raises(Refused):
        check_pairing(a_book(), a_book("okx", offset_ms=1), 0)
