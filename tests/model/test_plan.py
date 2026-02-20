"""Plans, and the edge decomposition that has to add up."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec

SYMBOL = parse_symbol("BTC-USD")


def a_leg(venue: str = "kraken", takes: Side = Side.ASK, **changes: object) -> Leg:
    fields: dict[str, object] = {
        "venue": venue,
        "symbol": SYMBOL,
        "takes": takes,
        "price": dec("100"),
        "size": dec("2"),
        "fee_bps": dec("16"),
        "fee_amount": dec("0.32"),
        "levels_swept": 1,
        "slippage_bps": dec("0"),
    }
    fields.update(changes)
    return Leg(**fields)  # type: ignore[arg-type]


def a_plan(**changes: object) -> Plan:
    fields: dict[str, object] = {
        "ref": "S20250701.0001/P000",
        "kind": PlanKind.CROSS_VENUE,
        "symbol": SYMBOL,
        "legs": (a_leg("kraken", Side.ASK), a_leg("okx", Side.BID, price=dec("101"))),
        "notional": dec("200"),
        "gross_bps": dec("100"),
        "fee_bps": dec("32"),
        "slippage_bps": dec("4"),
        "rebalance_bps": dec("6"),
        "net_bps": dec("58"),
        "status": PlanStatus.PRICED,
    }
    fields.update(changes)
    return Plan(**fields)  # type: ignore[arg-type]


def test_a_plan_lists_its_venues_once_each_in_leg_order() -> None:
    assert a_plan().venues == ("kraken", "okx")


def test_a_plan_needs_two_legs() -> None:
    with pytest.raises(BadArgument) as caught:
        a_plan(legs=(a_leg(),))
    assert caught.value.field == "legs"


def test_the_total_cost_is_every_deduction() -> None:
    assert a_plan().total_cost_bps == dec("42")


def test_the_arithmetic_holds_when_the_parts_add_up() -> None:
    assert a_plan().arithmetic_holds()
    assert a_plan().require_arithmetic() is not None


def test_the_arithmetic_fails_when_the_net_does_not_match() -> None:
    plan = a_plan(net_bps=dec("70"))
    assert not plan.arithmetic_holds()
    with pytest.raises(BadArgument) as caught:
        plan.require_arithmetic()
    assert caught.value.field == "net_bps"


def test_a_rounding_sized_difference_is_tolerated() -> None:
    assert a_plan(net_bps=dec("58.00005")).arithmetic_holds()


def test_a_refused_plan_has_to_name_a_clause() -> None:
    with pytest.raises(BadArgument) as caught:
        a_plan(status=PlanStatus.REFUSED)
    assert caught.value.field == "clause"


def test_a_plan_that_was_not_refused_may_not_carry_a_clause() -> None:
    with pytest.raises(BadArgument):
        a_plan(clause="EDGE.01")


def test_a_refused_plan_that_names_a_clause_is_accepted() -> None:
    plan = a_plan(status=PlanStatus.REFUSED, clause="EDGE.01")
    assert plan.clause == "EDGE.01"


def test_a_trimmed_plan_is_still_actionable() -> None:
    assert PlanStatus.TRIMMED.is_actionable
    assert PlanStatus.PRICED.is_actionable
    assert not PlanStatus.REFUSED.is_actionable


def test_the_leg_on_a_venue_can_be_pulled_out() -> None:
    assert a_plan().leg_on("okx").price == dec("101")


def test_a_venue_the_plan_does_not_touch_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_plan().leg_on("bitstamp")
    assert "0 legs" in caught.value.why


def test_a_venue_the_plan_touches_twice_is_refused() -> None:
    plan = a_plan(legs=(a_leg("kraken", Side.ASK), a_leg("kraken", Side.BID)))
    with pytest.raises(BadArgument) as caught:
        plan.leg_on("kraken")
    assert "2 legs" in caught.value.why


def test_a_plan_with_no_notional_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_plan(notional=dec("0"))
