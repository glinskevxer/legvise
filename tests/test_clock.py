"""The clock is a dependency, and quote age is measured in milliseconds."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.clock import (
    FixedClock,
    SystemClock,
    age_ms,
    parse_instant,
    to_millis,
    to_text,
)
from legvise.errors import BadArgument

AT = dt.datetime(2025, 3, 4, 9, 15, tzinfo=dt.UTC)


def test_the_system_clock_answers_in_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == dt.timedelta(0)


def test_a_fixed_clock_stays_where_it_was_put() -> None:
    clock = FixedClock(AT)
    assert clock.now() == AT
    assert clock.now() == AT


def test_advancing_a_fixed_clock_moves_it_by_milliseconds() -> None:
    clock = FixedClock(AT)
    landed = clock.advance_ms(1500)
    assert landed == AT + dt.timedelta(milliseconds=1500)
    assert clock.now() == landed


def test_a_fixed_clock_refuses_to_run_backwards_by_accident() -> None:
    clock = FixedClock(AT)
    with pytest.raises(BadArgument):
        clock.advance_ms(-1)


def test_a_fixed_clock_can_be_jumped_on_purpose() -> None:
    clock = FixedClock(AT)
    clock.set_to(AT - dt.timedelta(hours=2))
    assert clock.now() == AT - dt.timedelta(hours=2)


def test_a_naive_instant_is_refused_everywhere() -> None:
    naive = dt.datetime(2025, 3, 4, 9, 15)
    with pytest.raises(BadArgument):
        FixedClock(naive)
    with pytest.raises(BadArgument):
        to_text(naive)


def test_an_offset_instant_is_normalised_to_utc() -> None:
    parsed = parse_instant("2025-03-04T10:15:00+01:00")
    assert parsed == AT
    assert to_text(parsed) == "2025-03-04T09:15:00+00:00"


def test_text_that_is_not_an_instant_is_refused() -> None:
    with pytest.raises(BadArgument):
        parse_instant("yesterday afternoon")


def test_an_instant_without_an_offset_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        parse_instant("2025-03-04T09:15:00")
    assert "timezone" in caught.value.why


def test_milliseconds_since_the_epoch_truncate() -> None:
    at = AT + dt.timedelta(microseconds=1999)
    assert to_millis(at) - to_millis(AT) == 1


def test_age_is_the_gap_between_the_stamp_and_now() -> None:
    assert age_ms(AT, AT + dt.timedelta(milliseconds=430)) == 430


def test_a_quote_stamped_in_the_future_reads_as_fresh() -> None:
    assert age_ms(AT + dt.timedelta(seconds=5), AT) == 0
