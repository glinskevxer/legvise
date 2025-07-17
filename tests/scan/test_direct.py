"""Pricing a cross-venue pair, and every way it gets turned down."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from legvise.errors import Refused
from legvise.model.book import Book
from legvise.model.instrument import Instrument
from legvise.model.plan import PlanKind, PlanStatus
from legvise.money import dec
from legvise.scan.direct import price_cross_venue
from tests.scan.conftest import AT, a_venue, a_view, terms

REF = "S20250708.0001/P000"


def price(buy_ask: str, sell_bid: str, **changes: object) -> object:
    buy = a_view("kraken", "99.00", buy_ask)
    sell = a_view("okx", sell_bid, str(Decimal(sell_bid) + Decimal("1")))
    return price_cross_venue(buy, sell, terms(**changes), ref=REF, now=AT)  # type: ignore[arg-type]


def test_a_crossing_pair_prices_into_a_plan() -> None:
    plan = price("100.00", "101.00")
    assert plan.kind is PlanKind.CROSS_VENUE  # type: ignore[attr-defined]
    assert plan.status is PlanStatus.PRICED  # type: ignore[attr-defined]
    assert plan.venues == ("kraken", "okx")  # type: ignore[attr-defined]


def test_the_gross_edge_is_measured_touch_to_touch() -> None:
    plan = price("100.00", "101.00")
    assert plan.gross_bps == dec("100")  # type: ignore[attr-defined]


def test_the_arithmetic_of_the_priced_plan_holds() -> None:
    assert price("100.00", "101.00").arithmetic_holds()  # type: ignore[attr-defined]


def test_both_legs_are_priced_and_neither_slips_inside_the_touch() -> None:
    plan = price("100.00", "101.00")
    assert len(plan.legs) == 2  # type: ignore[attr-defined]
    assert all(leg.slippage_bps == 0 for leg in plan.legs)  # type: ignore[attr-defined]


def test_the_round_trip_fee_is_quoted_against_the_buy_leg_notional() -> None:
    # Ten basis points a side, but the sell leg is worth 101 against the buy
    # leg's 100, so the round trip reads 20.1 rather than a tidy 20.
    plan = price("100.00", "101.00")
    assert plan.fee_bps == dec("20.1")  # type: ignore[attr-defined]


def test_a_pair_that_does_not_cross_is_refused_on_the_edge_floor() -> None:
    with pytest.raises(Refused) as caught:
        price("100.00", "99.50")
    assert caught.value.why.startswith("EDGE.01")


def test_a_pair_whose_edge_is_eaten_by_fees_is_refused() -> None:
    buy = a_view("kraken", "99.00", "100.00", taker_bps="60")
    sell = a_view("okx", "101.00", "102.00", taker_bps="60")
    with pytest.raises(Refused) as caught:
        price_cross_venue(buy, sell, terms(), ref=REF, now=AT)
    assert caught.value.why.startswith("EDGE.01")


def test_a_higher_edge_floor_turns_the_same_pair_down() -> None:
    price("100.00", "100.50")
    with pytest.raises(Refused):
        price("100.00", "100.50", min_edge_bps="60")


def test_the_two_legs_have_to_be_the_same_market() -> None:
    buy = a_view("kraken", "99.00", "100.00")
    sell = a_view("okx", "101.00", "102.00")
    other = replace(
        sell,
        instrument=Instrument.build(
            "okx",
            "ETH-USD",
            tick_size="0.01",
            lot_step="0.0001",
            min_notional="10",
            max_notional="10000000",
        ),
    )
    with pytest.raises(Refused) as caught:
        price_cross_venue(buy, other, terms(), ref=REF, now=AT)
    assert caught.value.why.startswith("EDGE.02")


def test_a_venue_against_itself_is_refused() -> None:
    buy = a_view("kraken", "99.00", "100.00")
    sell = a_view("kraken", "101.00", "102.00")
    with pytest.raises(Refused) as caught:
        price_cross_venue(buy, sell, terms(), ref=REF, now=AT)
    assert caught.value.why.startswith("EDGE.02")


def test_a_stale_book_on_either_side_is_refused() -> None:
    tight = a_venue("kraken", staleness_budget_ms=10)
    buy = a_view("kraken", "99.00", "100.00", offset_ms=-500, venue=tight)
    sell = a_view("okx", "101.00", "102.00")
    with pytest.raises(Refused) as caught:
        price_cross_venue(buy, sell, terms(), ref=REF, now=AT)
    assert caught.value.why.startswith("STALE.01")


def test_two_books_too_far_apart_in_time_are_refused() -> None:
    buy = a_view("kraken", "99.00", "100.00", offset_ms=-400)
    sell = a_view("okx", "101.00", "102.00")
    with pytest.raises(Refused) as caught:
        price_cross_venue(buy, sell, terms(pairing_window_ms=100), ref=REF, now=AT)
    assert caught.value.why.startswith("STALE.02")


def test_a_plan_sized_down_by_the_book_reads_as_trimmed() -> None:
    buy = a_view("kraken", "99.00", "100.00", depth="2")
    sell = a_view("okx", "101.00", "102.00")
    plan = price_cross_venue(buy, sell, terms(wanted="10"), ref=REF, now=AT)
    assert plan.status is PlanStatus.TRIMMED
    assert plan.legs[0].size == dec("2")


def test_the_thinner_of_the_two_venues_sets_the_size() -> None:
    buy = a_view("kraken", "99.00", "100.00", depth="9")
    sell = a_view("okx", "101.00", "102.00", depth="3")
    plan = price_cross_venue(buy, sell, terms(wanted="10"), ref=REF, now=AT)
    assert plan.legs[0].size == dec("3")
    assert plan.legs[1].size == dec("3")


def test_sweeping_past_the_touch_shows_up_as_slippage() -> None:
    layered = Book.build(
        "kraken",
        "BTC-USD",
        observed_at=AT,
        bids=(("99.00", "50"),),
        asks=(("100.00", "1"), ("100.50", "50")),
    )
    buy = replace(a_view("kraken", "99.00", "100.00"), book=layered)
    sell = a_view("okx", "102.00", "103.00")
    plan = price_cross_venue(buy, sell, terms(wanted="5"), ref=REF, now=AT)
    assert plan.slippage_bps > 0
    assert plan.arithmetic_holds()
