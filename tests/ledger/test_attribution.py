"""Splitting the gap between a plan and its fills into named reasons."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.ledger.attribution import attribute
from legvise.model.book import Side
from legvise.model.fill import Fill, LegResult
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec

REF = "S20250924.0001/P000"
SYMBOL = parse_symbol("BTC-USD")
AT = "2025-09-24T09:00:01+00:00"


def a_leg(venue: str, takes: Side, price: str) -> Leg:
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec(price),
        size=dec("2"),
        fee_bps=dec("10"),
        fee_amount=dec("0.2"),
        levels_swept=1,
        slippage_bps=dec("0"),
    )


def a_plan() -> Plan:
    return Plan(
        ref=REF,
        kind=PlanKind.CROSS_VENUE,
        symbol=SYMBOL,
        legs=(a_leg("kraken", Side.ASK, "100"), a_leg("okx", Side.BID, "101")),
        notional=dec("200"),
        gross_bps=dec("100"),
        fee_bps=dec("20"),
        slippage_bps=dec("0"),
        rebalance_bps=dec("0"),
        net_bps=dec("80"),
        status=PlanStatus.PRICED,
    )


def fills(leg: int, *prices_and_sizes: tuple[str, str], fee: str = "0.2") -> tuple[Fill, ...]:
    venue = "kraken" if leg == 0 else "okx"
    takes = Side.ASK if leg == 0 else Side.BID
    return tuple(
        Fill.build(REF, leg, venue, takes, price=price, size=size, fee_amount=fee, filled_at=AT)
        for price, size in prices_and_sizes
    )


def results(buy: tuple[Fill, ...] = (), sell: tuple[Fill, ...] = ()) -> tuple[LegResult, ...]:
    plan = a_plan()
    return tuple(
        LegResult(
            plan_ref=REF,
            leg_index=index,
            expected_price=leg.price,
            expected_size=leg.size,
            fills=buy if index == 0 else sell,
        )
        for index, leg in enumerate(plan.legs)
    )


def test_a_plan_that_filled_exactly_as_priced_has_no_drift() -> None:
    found = attribute(a_plan(), results(fills(0, ("100", "2")), fills(1, ("101", "2"))))
    assert found.price_drift_bps == dec("0")
    assert found.fee_drift_bps == dec("0")
    assert found.realised_bps == dec("80")
    assert found.gap_bps == dec("0")


def test_a_plan_that_never_filled_realises_nothing() -> None:
    found = attribute(a_plan(), results())
    assert found.realised_bps == dec("0")
    assert found.gap_bps == dec("80")
    assert not found.has_leg_risk


def test_a_buy_that_filled_higher_lost_the_difference() -> None:
    found = attribute(a_plan(), results(fills(0, ("101", "2")), fills(1, ("101", "2"))))
    assert found.price_drift_bps == dec("100")
    assert found.realised_bps == dec("-20")


def test_a_buy_that_filled_lower_gained() -> None:
    found = attribute(a_plan(), results(fills(0, ("99", "2")), fills(1, ("101", "2"))))
    assert found.price_drift_bps == dec("-100")
    assert found.realised_bps == dec("180")


def test_a_sell_that_filled_lower_lost_the_difference() -> None:
    found = attribute(a_plan(), results(fills(0, ("100", "2")), fills(1, ("100", "2"))))
    assert found.price_drift_bps == dec("100")


def test_a_fee_bigger_than_the_plan_booked_reads_as_fee_drift() -> None:
    found = attribute(
        a_plan(),
        results(fills(0, ("100", "2"), fee="0.4"), fills(1, ("101", "2"))),
    )
    assert found.fee_drift_bps == dec("10")


def test_a_fee_smaller_than_booked_reads_as_a_credit() -> None:
    found = attribute(
        a_plan(),
        results(fills(0, ("100", "2"), fee="0.1"), fills(1, ("101", "2"))),
    )
    assert found.fee_drift_bps == dec("-5")


def test_a_partial_fill_reports_the_worst_ratio() -> None:
    found = attribute(a_plan(), results(fills(0, ("100", "1")), fills(1, ("101", "2"))))
    assert found.shortfall_ratio == dec("0.5")


def test_one_leg_filling_alone_is_recorded_as_leg_risk() -> None:
    found = attribute(a_plan(), results(fills(0, ("100", "2"))))
    assert found.has_leg_risk
    assert found.naked_legs == (1,)


def test_neither_leg_filling_is_not_leg_risk() -> None:
    assert attribute(a_plan(), results()).naked_legs == ()


def test_both_legs_filling_is_not_leg_risk() -> None:
    found = attribute(a_plan(), results(fills(0, ("100", "2")), fills(1, ("101", "2"))))
    assert not found.has_leg_risk


def test_several_fills_on_one_leg_average_before_the_drift_is_measured() -> None:
    found = attribute(
        a_plan(),
        results(fills(0, ("99", "1"), ("101", "1"), fee="0.1"), fills(1, ("101", "2"))),
    )
    assert found.price_drift_bps == dec("0")


def test_the_decomposition_reconstructs_the_gap() -> None:
    found = attribute(
        a_plan(),
        results(fills(0, ("101", "2"), fee="0.4"), fills(1, ("100", "2"))),
    )
    assert found.adds_up()


def test_a_result_count_that_does_not_match_the_plan_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        attribute(a_plan(), results()[:1])
    assert "2 legs" in caught.value.why


def test_the_explained_and_unexplained_parts_sum_to_the_gap() -> None:
    found = attribute(a_plan(), results(fills(0, ("100", "1")), fills(1, ("101", "1"))))
    assert found.explained_bps + found.unexplained_bps == found.gap_bps


# Relationships attribution has to satisfy whatever the fills came back as.

PRICES = ("98", "99", "100", "101", "102")
SIZES = ("0.5", "1", "1.5", "2")


@pytest.mark.parametrize("buy_price", PRICES)
@pytest.mark.parametrize("sell_price", PRICES)
def test_the_named_parts_always_reconstruct_the_gap(buy_price: str, sell_price: str) -> None:
    found = attribute(
        a_plan(),
        results(fills(0, (buy_price, "2")), fills(1, (sell_price, "2"))),
    )
    assert found.adds_up()


@pytest.mark.parametrize("buy_price", PRICES)
def test_a_worse_buy_never_realises_more(buy_price: str) -> None:
    at_plan = attribute(a_plan(), results(fills(0, ("100", "2")), fills(1, ("101", "2"))))
    moved = attribute(a_plan(), results(fills(0, (buy_price, "2")), fills(1, ("101", "2"))))
    if dec(buy_price) > dec("100"):
        assert moved.realised_bps <= at_plan.realised_bps


@pytest.mark.parametrize("size", SIZES)
def test_the_fill_ratio_never_exceeds_one_on_a_partial(size: str) -> None:
    found = attribute(a_plan(), results(fills(0, ("100", size)), fills(1, ("101", "2"))))
    assert found.shortfall_ratio <= dec("1")


@pytest.mark.parametrize("size", SIZES)
def test_one_leg_short_is_always_a_shortfall(size: str) -> None:
    found = attribute(a_plan(), results(fills(0, ("100", size)), fills(1, ("101", "2"))))
    assert found.shortfall_ratio == dec(size) / dec("2")


@pytest.mark.parametrize("size", SIZES)
def test_a_leg_that_traded_alone_is_always_leg_risk(size: str) -> None:
    found = attribute(a_plan(), results(fills(0, ("100", size))))
    assert found.has_leg_risk
    assert found.naked_legs == (1,)


@pytest.mark.parametrize("fee", ["0", "0.1", "0.2", "0.5", "1"])
def test_a_bigger_fee_never_realises_more(fee: str) -> None:
    found = attribute(
        a_plan(),
        results(fills(0, ("100", "2"), fee=fee), fills(1, ("101", "2"), fee="0.2")),
    )
    at_plan = attribute(
        a_plan(),
        results(fills(0, ("100", "2"), fee="0.2"), fills(1, ("101", "2"), fee="0.2")),
    )
    if dec(fee) > dec("0.2"):
        assert found.realised_bps <= at_plan.realised_bps


@pytest.mark.parametrize("buy_price", PRICES)
@pytest.mark.parametrize("sell_price", PRICES)
def test_the_expected_edge_is_always_the_plan_edge(buy_price: str, sell_price: str) -> None:
    found = attribute(
        a_plan(),
        results(fills(0, (buy_price, "2")), fills(1, (sell_price, "2"))),
    )
    assert found.expected_bps == a_plan().net_bps


@pytest.mark.parametrize("buy_price", PRICES)
def test_filling_both_legs_is_never_leg_risk(buy_price: str) -> None:
    found = attribute(
        a_plan(),
        results(fills(0, (buy_price, "2")), fills(1, ("101", "2"))),
    )
    assert not found.has_leg_risk
