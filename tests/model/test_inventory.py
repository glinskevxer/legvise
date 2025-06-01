"""Positions and the bands the desk keeps them inside."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.model.inventory import Band, Position
from legvise.money import dec

AS_OF = "2025-05-20T07:00:00+00:00"


def a_position(**changes: object) -> Position:
    fields: dict[str, object] = {
        "venue": "kraken",
        "asset": "BTC",
        "free": "4.5",
        "locked": "0.5",
        "as_of": AS_OF,
    }
    fields.update(changes)
    return Position.build(**fields)  # type: ignore[arg-type]


def a_band(**changes: object) -> Band:
    fields: dict[str, object] = {
        "venue": "kraken",
        "asset": "BTC",
        "floor": "1",
        "target": "5",
        "ceiling": "9",
    }
    fields.update(changes)
    return Band.build(**fields)  # type: ignore[arg-type]


def test_a_position_totals_what_is_free_and_what_is_locked() -> None:
    assert a_position().total == dec("5.0")


def test_a_position_keys_on_the_venue_and_the_asset() -> None:
    assert a_position().key == ("kraken", "BTC")


def test_codes_are_normalised_on_the_way_in() -> None:
    assert a_position(venue=" Kraken ", asset="btc").key == ("kraken", "BTC")


@pytest.mark.parametrize("field", ["free", "locked"])
def test_a_negative_balance_is_refused(field: str) -> None:
    with pytest.raises(BadArgument) as caught:
        a_position(**{field: "-1"})
    assert caught.value.field == field


def test_locked_defaults_to_nothing() -> None:
    assert Position.build("kraken", "BTC", free="1", as_of=AS_OF).locked == dec("0")


def test_taking_reduces_the_free_balance_only() -> None:
    after = a_position().after_taking(dec("1.5"))
    assert after.free == dec("3.0")
    assert after.locked == dec("0.5")


def test_receiving_adds_to_the_free_balance() -> None:
    assert a_position().after_receiving(dec("2")).free == dec("6.5")


def test_taking_more_than_is_free_is_refused_by_the_record_itself() -> None:
    with pytest.raises(BadArgument):
        a_position().after_taking(dec("5"))


def test_taking_a_negative_amount_points_at_the_other_method() -> None:
    with pytest.raises(BadArgument) as caught:
        a_position().after_taking(dec("-1"))
    assert "after_receiving" in caught.value.why


def test_receiving_a_negative_amount_points_at_the_other_method() -> None:
    with pytest.raises(BadArgument) as caught:
        a_position().after_receiving(dec("-1"))
    assert "after_taking" in caught.value.why


def test_a_band_measures_its_own_width() -> None:
    assert a_band().width == dec("8")


def test_headroom_above_shrinks_as_the_holding_grows() -> None:
    band = a_band()
    assert band.headroom_above(dec("5")) == dec("4")
    assert band.headroom_above(dec("11")) == dec("-2")


def test_headroom_below_shrinks_as_the_holding_falls() -> None:
    band = a_band()
    assert band.headroom_below(dec("5")) == dec("4")
    assert band.headroom_below(dec("0.5")) == dec("-0.5")


def test_the_distance_from_target_is_signed() -> None:
    band = a_band()
    assert band.distance_from_target(dec("7")) == dec("2")
    assert band.distance_from_target(dec("3")) == dec("-2")


def test_a_negative_floor_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_band(floor="-1")
    assert caught.value.field == "floor"


def test_a_target_below_the_floor_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_band(floor="5", target="1", ceiling="9")
    assert caught.value.field == "target"


def test_a_target_above_the_ceiling_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_band(floor="1", target="9", ceiling="5")


def test_a_band_with_no_width_is_allowed() -> None:
    flat = a_band(floor="3", target="3", ceiling="3")
    assert flat.width == dec("0")
