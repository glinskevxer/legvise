"""The floor is a wall and the ceiling is a price."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.model.inventory import Band, Position
from legvise.money import dec
from legvise.risk.bands import (
    excess_above_ceiling,
    require_room_to_spend,
    room_for,
    room_to_receive,
    room_to_spend,
)

AS_OF = "2025-06-16T07:00:00+00:00"
BAND = Band.build("kraken", "BTC", floor="1", target="5", ceiling="9")


def holding(free: str, locked: str = "0") -> Position:
    return Position.build("kraken", "BTC", free=free, locked=locked, as_of=AS_OF)


def test_room_reports_both_directions_at_once() -> None:
    room = room_for(holding("5"), BAND)
    assert room.spendable == dec("4")
    assert room.receivable == dec("4")
    assert room.holding == dec("5")
    assert room.target_gap == dec("0")


def test_the_target_gap_is_signed() -> None:
    assert room_for(holding("7"), BAND).target_gap == dec("2")
    assert room_for(holding("3"), BAND).target_gap == dec("-2")


def test_locked_balance_counts_toward_the_ceiling_but_not_the_floor() -> None:
    room = room_for(holding("2", "6"), BAND)
    assert room.spendable == dec("1")
    assert room.receivable == dec("1")


def test_a_position_under_its_floor_says_so() -> None:
    room = room_for(holding("0.5"), BAND)
    assert room.is_below_floor
    assert room_to_spend(holding("0.5"), BAND) == dec("0")


def test_a_position_over_its_ceiling_says_so() -> None:
    room = room_for(holding("12"), BAND)
    assert room.is_above_ceiling
    assert room_to_receive(holding("12"), BAND) == dec("0")


def test_room_to_spend_never_reads_negative() -> None:
    assert room_to_spend(holding("0"), BAND) == dec("0")


def test_a_leg_inside_the_floor_is_allowed_and_reports_what_is_left() -> None:
    assert require_room_to_spend(holding("5"), BAND, dec("3")) == dec("1")


def test_a_leg_that_would_break_the_floor_quotes_the_clause() -> None:
    with pytest.raises(Refused) as caught:
        require_room_to_spend(holding("5"), BAND, dec("5"))
    assert caught.value.why.startswith("BAND.01")


def test_a_leg_that_lands_exactly_on_the_floor_is_allowed() -> None:
    assert require_room_to_spend(holding("5"), BAND, dec("4")) == dec("0")


def test_a_leg_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        require_room_to_spend(holding("5"), BAND, dec("0"))


def test_arriving_inside_the_ceiling_costs_nothing() -> None:
    assert excess_above_ceiling(holding("5"), BAND, dec("3")) == dec("0")


def test_arriving_exactly_on_the_ceiling_costs_nothing() -> None:
    assert excess_above_ceiling(holding("5"), BAND, dec("4")) == dec("0")


def test_only_the_overshoot_is_charged_for() -> None:
    assert excess_above_ceiling(holding("5"), BAND, dec("6")) == dec("2")


def test_a_position_already_over_the_ceiling_charges_the_whole_arrival() -> None:
    assert excess_above_ceiling(holding("11"), BAND, dec("2")) == dec("4")


def test_a_negative_arrival_is_refused() -> None:
    with pytest.raises(BadArgument):
        excess_above_ceiling(holding("5"), BAND, dec("-1"))


def test_a_band_for_a_different_asset_is_refused() -> None:
    other = Band.build("kraken", "ETH", floor="1", target="5", ceiling="9")
    with pytest.raises(BadArgument) as caught:
        room_for(holding("5"), other)
    assert "kraken:BTC" in caught.value.why


def test_a_band_for_a_different_venue_is_refused() -> None:
    other = Band.build("okx", "BTC", floor="1", target="5", ceiling="9")
    with pytest.raises(BadArgument):
        room_for(holding("5"), other)
