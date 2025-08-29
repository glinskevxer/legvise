"""Pricing a loop against depth and three sets of fees."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import BadArgument, Refused
from legvise.fees.quote import FeeContext
from legvise.ids import Symbol, parse_symbol
from legvise.model.book import Book
from legvise.model.cycle import Cycle
from legvise.model.fee import FeeTier
from legvise.model.plan import PlanKind
from legvise.money import dec
from legvise.scan.loop import as_plan, price_cycle
from legvise.scan.triangular import profitable_cycles

AT = dt.datetime(2025, 9, 2, 11, 0, tzinfo=dt.UTC)


def fees(taker_bps: str = "0") -> FeeContext:
    return FeeContext(
        venue="kraken",
        tier=FeeTier.build("0", "0", taker_bps),
        pays_maker_rebate=False,
    )


def book(symbol: str, bid: str, ask: str, depth: str = "10000") -> Book:
    return Book.build(
        "kraken",
        symbol,
        observed_at=AT,
        bids=((bid, depth),),
        asks=((ask, depth),),
    )


def a_venue(eth_usd_bid: str = "5.012") -> dict[Symbol, Book]:
    """A triangle that screens at about four basis points, which is realistic.

    Wide fixtures hide fee arithmetic: a loop screening at three hundred basis
    points still looks profitable after three taker fees, so a test built on one
    proves nothing about whether the fees were applied at all.
    """
    return {
        parse_symbol("BTC-USD"): book("BTC-USD", "99.9", "100"),
        parse_symbol("ETH-BTC"): book("ETH-BTC", "0.05", "0.0501"),
        parse_symbol("ETH-USD"): book("ETH-USD", eth_usd_bid, "5.02"),
    }


def a_cycle(books: dict[Symbol, Book] | None = None) -> Cycle:
    found = profitable_cycles("kraken", tuple((books or a_venue()).values()), start="USD")
    assert found, "the fixture is supposed to screen positive"
    return found[0]


def test_a_loop_with_no_fees_comes_back_close_to_the_touch_edge() -> None:
    cycle = a_cycle()
    quote = price_cycle(cycle, a_venue(), fees(), start_amount=dec("1000"))
    assert quote.net_bps == cycle.gross_bps
    assert quote.fee_bps == dec("0")


def test_every_hop_records_what_it_swept() -> None:
    quote = price_cycle(a_cycle(), a_venue(), fees(), start_amount=dec("1000"))
    assert len(quote.fills) == 3
    assert all(fill.sweep.levels >= 1 for fill in quote.fills)


def test_three_sets_of_fees_eat_the_edge() -> None:
    cycle = a_cycle()
    free = price_cycle(cycle, a_venue(), fees("0"), start_amount=dec("1000"))
    charged = price_cycle(cycle, a_venue(), fees("16"), start_amount=dec("1000"))
    assert charged.net_bps < free.net_bps
    assert charged.fee_bps > dec("40")


def test_the_fee_gap_is_the_difference_between_the_screen_and_the_price() -> None:
    cycle = a_cycle()
    quote = price_cycle(cycle, a_venue(), fees("10"), start_amount=dec("1000"))
    assert quote.fee_bps == cycle.gross_bps - quote.net_bps


def test_a_loop_that_starts_with_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        price_cycle(a_cycle(), a_venue(), fees(), start_amount=dec("0"))


def test_a_missing_book_is_refused_rather_than_skipped() -> None:
    books = a_venue()
    del books[parse_symbol("ETH-BTC")]
    with pytest.raises(Refused) as caught:
        price_cycle(a_cycle(), books, fees(), start_amount=dec("1000"))
    assert caught.value.why.startswith("BOOK.02")


def test_a_loop_bigger_than_the_book_is_refused_on_depth() -> None:
    thin = {
        parse_symbol("BTC-USD"): book("BTC-USD", "99.9", "100", depth="0.5"),
        parse_symbol("ETH-BTC"): book("ETH-BTC", "0.05", "0.0501", depth="0.5"),
        parse_symbol("ETH-USD"): book("ETH-USD", "5.2", "5.3", depth="0.5"),
    }
    with pytest.raises(Refused) as caught:
        price_cycle(a_cycle(), thin, fees(), start_amount=dec("100000"))
    assert caught.value.why.startswith("DEPTH.01")


def test_a_bigger_start_returns_proportionally_more() -> None:
    cycle = a_cycle()
    small = price_cycle(cycle, a_venue(), fees(), start_amount=dec("1000"))
    large = price_cycle(cycle, a_venue(), fees(), start_amount=dec("2000"))
    assert abs(large.net_bps - small.net_bps) < dec("0.0001")


def test_a_priced_loop_becomes_a_three_leg_plan() -> None:
    quote = price_cycle(a_cycle(), a_venue(), fees(), start_amount=dec("1000"))
    plan = as_plan(quote, ref="S20250902.0001/P000", min_edge_bps=dec("1"))
    assert plan.kind is PlanKind.TRIANGULAR
    assert len(plan.legs) == 3
    assert plan.arithmetic_holds()


def test_a_loop_that_does_not_clear_the_floor_is_refused() -> None:
    quote = price_cycle(a_cycle(), a_venue(), fees("16"), start_amount=dec("1000"))
    assert quote.net_bps < dec("0")
    with pytest.raises(Refused) as caught:
        as_plan(quote, ref="S20250902.0001/P000", min_edge_bps=dec("1"))
    assert caught.value.why.startswith("EDGE.01")


def test_every_leg_of_the_plan_names_its_own_market() -> None:
    quote = price_cycle(a_cycle(), a_venue(), fees(), start_amount=dec("1000"))
    plan = as_plan(quote, ref="S20250902.0001/P000", min_edge_bps=dec("1"))
    assert len({str(leg.symbol) for leg in plan.legs}) == 3


def test_the_realised_rate_of_a_hop_is_readable() -> None:
    quote = price_cycle(a_cycle(), a_venue(), fees(), start_amount=dec("1000"))
    first = quote.fills[0]
    assert first.realised_rate > dec("0")
    assert first.spent == dec("1000")
