"""How much of the desk is in one asset, and how much of that on one venue."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.model.inventory import Position
from legvise.money import dec
from legvise.risk.concentration import ConcentrationLimits, measure, require_within

AS_OF = "2026-02-24T09:00:00+00:00"
MARKS = {"BTC": dec("100000"), "ETH": dec("4000"), "USD": dec("1")}

LOOSE = ConcentrationLimits(
    most_of_desk_in_one_asset=dec("0.9"),
    most_of_an_asset_on_one_venue=dec("0.9"),
)


def holding(venue: str, asset: str, free: str, locked: str = "0") -> Position:
    return Position.build(venue, asset, free=free, locked=locked, as_of=AS_OF)


def a_desk() -> tuple[Position, ...]:
    """Half a million in BTC and half a million in cash, both split evenly."""
    return (
        holding("kraken", "BTC", "2.5"),
        holding("okx", "BTC", "2.5"),
        holding("kraken", "USD", "250000"),
        holding("okx", "USD", "250000"),
    )


def test_the_desk_is_valued_at_the_marks_given() -> None:
    found = measure(a_desk(), MARKS)
    assert found.total_value == dec("1000000")


def test_an_asset_share_is_its_value_over_the_whole_desk() -> None:
    assert measure(a_desk(), MARKS).asset_share("BTC") == dec("0.5")


def test_an_asset_the_desk_does_not_hold_is_no_share_of_it() -> None:
    assert measure(a_desk(), MARKS).asset_share("SOL") == dec("0")


def test_a_venue_share_is_measured_against_the_asset_not_the_desk() -> None:
    assert measure(a_desk(), MARKS).venue_share("BTC", "kraken") == dec("0.5")


def test_a_venue_holding_none_of_an_asset_is_no_share_of_it() -> None:
    assert measure(a_desk(), MARKS).venue_share("BTC", "bitstamp") == dec("0")


def test_a_venue_share_of_an_asset_nobody_holds_is_nothing() -> None:
    assert measure(a_desk(), MARKS).venue_share("SOL", "kraken") == dec("0")


def test_locked_balance_counts_toward_the_value() -> None:
    with_locked = (holding("kraken", "BTC", "1", "1"),)
    assert measure(with_locked, MARKS).total_value == dec("200000")


def test_the_busiest_asset_is_the_one_worth_most() -> None:
    heavy = (holding("kraken", "BTC", "9"), holding("kraken", "USD", "1000"))
    assert measure(heavy, MARKS).busiest_asset == "BTC"


def test_an_empty_desk_has_no_busiest_asset() -> None:
    found = measure((), MARKS)
    assert found.busiest_asset is None
    assert found.total_value == dec("0")


def test_an_empty_desk_reports_no_shares() -> None:
    assert measure((), MARKS).asset_share("BTC") == dec("0")


def test_a_held_asset_with_no_mark_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        measure((holding("kraken", "SOL", "100"),), MARKS)
    assert caught.value.why == "no mark price for a held asset"


def test_a_negative_mark_is_refused() -> None:
    with pytest.raises(BadArgument):
        measure((holding("kraken", "BTC", "1"),), {"BTC": dec("-1")})


def test_a_share_limit_of_zero_is_refused() -> None:
    with pytest.raises(BadArgument):
        ConcentrationLimits(
            most_of_desk_in_one_asset=dec("0"),
            most_of_an_asset_on_one_venue=dec("0.9"),
        )


def test_a_share_limit_above_one_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        ConcentrationLimits(
            most_of_desk_in_one_asset=dec("1.1"),
            most_of_an_asset_on_one_venue=dec("0.9"),
        )
    assert caught.value.field == "most_of_desk_in_one_asset"


def test_a_desk_inside_both_limits_passes() -> None:
    assert require_within(measure(a_desk(), MARKS), LOOSE).total_value == dec("1000000")


def test_a_desk_too_heavy_in_one_asset_is_refused() -> None:
    tight = ConcentrationLimits(
        most_of_desk_in_one_asset=dec("0.4"),
        most_of_an_asset_on_one_venue=dec("0.9"),
    )
    with pytest.raises(Refused) as caught:
        require_within(measure(a_desk(), MARKS), tight)
    assert caught.value.why.startswith("CAP.02")
    assert "of the desk" in caught.value.subject


def test_a_desk_holding_one_asset_all_in_one_place_is_refused() -> None:
    all_on_kraken = (holding("kraken", "BTC", "5"), holding("okx", "USD", "500000"))
    tight = ConcentrationLimits(
        most_of_desk_in_one_asset=dec("0.9"),
        most_of_an_asset_on_one_venue=dec("0.6"),
    )
    with pytest.raises(Refused) as caught:
        require_within(measure(all_on_kraken, MARKS), tight)
    assert "on kraken" in caught.value.subject
