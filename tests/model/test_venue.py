"""What a venue record refuses to be built as."""

from __future__ import annotations

from decimal import Decimal

import pytest

from legvise.errors import BadArgument
from legvise.model.venue import Venue


def a_venue(**changes: object) -> Venue:
    fields: dict[str, object] = {
        "code": "kraken",
        "display_name": "Kraken",
        "staleness_budget_ms": 750,
        "depth_limit_bps": "35",
        "notional_cap": "250000",
    }
    fields.update(changes)
    return Venue.build(**fields)  # type: ignore[arg-type]


def test_a_venue_normalises_its_code_and_trims_its_name() -> None:
    venue = Venue.build(
        " Kraken ",
        "  Kraken Pro  ",
        staleness_budget_ms=750,
        depth_limit_bps="35",
        notional_cap="250000",
    )
    assert venue.code == "kraken"
    assert venue.display_name == "Kraken Pro"


def test_decimal_fields_arrive_as_decimals() -> None:
    venue = a_venue()
    assert venue.depth_limit_bps == Decimal("35")
    assert venue.notional_cap == Decimal("250000")


def test_a_venue_is_active_and_pays_no_rebate_unless_told_otherwise() -> None:
    venue = a_venue()
    assert venue.active is True
    assert venue.pays_maker_rebate is False


def test_a_venue_cannot_be_changed_after_it_is_built() -> None:
    venue = a_venue()
    with pytest.raises(AttributeError):
        venue.code = "other"  # type: ignore[misc]


def test_a_venue_needs_a_name() -> None:
    with pytest.raises(BadArgument) as caught:
        a_venue(display_name="   ")
    assert caught.value.field == "display_name"


@pytest.mark.parametrize("budget", [0, -1])
def test_a_staleness_budget_has_to_leave_room_to_trade(budget: int) -> None:
    with pytest.raises(BadArgument) as caught:
        a_venue(staleness_budget_ms=budget)
    assert caught.value.field == "staleness_budget_ms"


def test_a_depth_limit_of_zero_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_venue(depth_limit_bps="0")
    assert caught.value.field == "depth_limit_bps"


def test_a_notional_cap_of_zero_is_refused_as_a_way_to_switch_a_venue_off() -> None:
    with pytest.raises(BadArgument) as caught:
        a_venue(notional_cap="0")
    assert "the venue is off" in caught.value.why


def test_a_code_that_is_not_normalised_cannot_be_constructed_directly() -> None:
    with pytest.raises(BadArgument):
        Venue(
            code="Kraken",
            display_name="Kraken",
            staleness_budget_ms=750,
            depth_limit_bps=Decimal("35"),
            notional_cap=Decimal("250000"),
            pays_maker_rebate=False,
            active=True,
        )


def test_deactivating_leaves_everything_else_alone() -> None:
    venue = a_venue()
    off = venue.deactivated()
    assert off.active is False
    assert off.code == venue.code
    assert off.notional_cap == venue.notional_cap
    assert venue.active is True


def test_replacing_a_field_revalidates_the_result() -> None:
    venue = a_venue()
    with pytest.raises(BadArgument):
        venue.replacing(staleness_budget_ms=0)


def test_replacing_a_field_that_does_not_exist_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_venue().replacing(fee_bps=Decimal("2"))
    assert caught.value.why == "a venue has no such field"


def test_replacing_returns_a_new_record() -> None:
    venue = a_venue()
    louder = venue.replacing(display_name="Kraken Institutional")
    assert louder.display_name == "Kraken Institutional"
    assert venue.display_name == "Kraken"
