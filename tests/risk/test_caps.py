"""Two caps that trim and one that stops."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.money import dec
from legvise.risk.caps import CapSet, require_trim, trim_to_caps


def caps(**changes: object) -> CapSet:
    fields: dict[str, object] = {
        "venue_cap": dec("250000"),
        "venue_used": dec("0"),
        "asset_cap": dec("400000"),
        "asset_used": dec("0"),
        "gross_cap": dec("1000000"),
        "gross_used": dec("0"),
    }
    fields.update(changes)
    return CapSet(**fields)  # type: ignore[arg-type]


def test_room_is_what_is_left_under_each_cap() -> None:
    made = caps(venue_used=dec("100000"), asset_used=dec("50000"), gross_used=dec("400000"))
    assert made.venue_room == dec("150000")
    assert made.asset_room == dec("350000")
    assert made.gross_room == dec("600000")


def test_room_never_reads_negative() -> None:
    assert caps(venue_used=dec("300000")).venue_room == dec("0")


def test_a_plan_inside_every_cap_passes_through_untouched() -> None:
    trim = trim_to_caps(caps(), dec("50000"), subject="plan 1")
    assert trim.allowed == dec("50000")
    assert not trim.was_trimmed
    assert trim.bound_by is None


def test_the_venue_cap_trims_and_says_so() -> None:
    trim = trim_to_caps(caps(venue_used=dec("210000")), dec("60000"), subject="plan 1")
    assert trim.allowed == dec("40000")
    assert trim.bound_by == "CAP.01"
    assert trim.cut == dec("20000")


def test_the_asset_cap_trims_when_it_is_the_tighter_one() -> None:
    trim = trim_to_caps(
        caps(venue_used=dec("210000"), asset_used=dec("390000")), dec("60000"), subject="plan 1"
    )
    assert trim.allowed == dec("10000")
    assert trim.bound_by == "CAP.02"


def test_the_venue_cap_wins_when_it_is_the_tighter_one() -> None:
    trim = trim_to_caps(
        caps(venue_used=dec("245000"), asset_used=dec("380000")), dec("60000"), subject="plan 1"
    )
    assert trim.allowed == dec("5000")
    assert trim.bound_by == "CAP.01"


def test_a_venue_at_its_cap_trims_to_nothing_rather_than_refusing() -> None:
    trim = trim_to_caps(caps(venue_used=dec("250000")), dec("60000"), subject="plan 1")
    assert trim.allowed == dec("0")
    assert trim.bound_by == "CAP.01"


def test_the_gross_cap_stops_rather_than_trimming() -> None:
    with pytest.raises(Refused) as caught:
        trim_to_caps(caps(gross_used=dec("980000")), dec("60000"), subject="plan 1")
    assert caught.value.why.startswith("CAP.03")


def test_a_desk_already_at_its_gross_cap_refuses_everything() -> None:
    with pytest.raises(Refused) as caught:
        trim_to_caps(caps(gross_used=dec("1000000")), dec("1"), subject="plan 1")
    assert caught.value.why.startswith("CAP.03")


def test_a_plan_exactly_filling_the_gross_room_is_allowed() -> None:
    trim = trim_to_caps(caps(gross_used=dec("940000")), dec("60000"), subject="plan 1")
    assert trim.allowed == dec("60000")


def test_a_plan_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        trim_to_caps(caps(), dec("0"), subject="plan 1")


def test_a_cap_of_zero_is_refused_as_a_way_to_switch_the_desk_off() -> None:
    with pytest.raises(BadArgument) as caught:
        caps(venue_cap=dec("0"))
    assert caught.value.field == "venue_cap"


def test_negative_used_exposure_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        caps(asset_used=dec("-1"))
    assert caught.value.field == "asset_used"


def test_requiring_a_trim_hands_back_the_allowed_notional() -> None:
    assert require_trim(caps(), dec("50000"), subject="plan 1", floor=dec("1000")) == dec("50000")


def test_a_trim_below_the_floor_refuses_with_the_cap_that_bound() -> None:
    with pytest.raises(Refused) as caught:
        require_trim(
            caps(venue_used=dec("249900")), dec("50000"), subject="plan 1", floor=dec("1000")
        )
    assert caught.value.why.startswith("CAP.01")


def test_a_trim_below_the_floor_with_no_cap_bound_still_refuses() -> None:
    with pytest.raises(Refused):
        require_trim(caps(), dec("500"), subject="plan 1", floor=dec("1000"))
