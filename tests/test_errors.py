"""The error types keep their parts addressable, not just printable."""

from __future__ import annotations

import pytest

from legvise.errors import (
    BadArgument,
    Conflict,
    LegviseError,
    NotFound,
    Refused,
    StaleData,
)


def test_every_error_descends_from_the_package_base() -> None:
    for cls in (NotFound, Conflict, BadArgument, Refused, StaleData):
        assert issubclass(cls, LegviseError)


def test_not_found_keeps_the_kind_and_the_key_apart() -> None:
    err = NotFound("venue", "kraken")
    assert err.kind == "venue"
    assert err.key == "kraken"
    assert "kraken" in str(err)


def test_conflict_reads_as_a_sentence_about_the_record() -> None:
    err = Conflict("instrument", "BTC-USD")
    assert err.kind == "instrument"
    assert str(err) == "instrument 'BTC-USD' already exists"


def test_bad_argument_carries_the_field_the_value_and_the_reason() -> None:
    err = BadArgument("tick_size", "0", "must be positive")
    assert err.field == "tick_size"
    assert err.value == "0"
    assert err.why == "must be positive"


def test_refused_names_the_subject_it_turned_down() -> None:
    err = Refused("leg 2 of plan 7", "below the venue minimum notional")
    assert err.subject == "leg 2 of plan 7"
    assert "minimum notional" in err.message


def test_stale_data_reports_both_the_age_and_the_budget() -> None:
    err = StaleData("coinbase BTC-USD book", 2400, 750)
    assert err.age_ms == 2400
    assert err.budget_ms == 750
    assert "2400ms" in str(err)


def test_raising_is_catchable_through_the_base() -> None:
    with pytest.raises(LegviseError):
        raise NotFound("venue", "gone")
