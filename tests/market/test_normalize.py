"""Rounding onto the venue grids, and the direction each rounding takes."""

from __future__ import annotations

import pytest

from legvise.errors import Refused
from legvise.market.normalize import (
    conform_order,
    conform_price,
    conform_size,
    fits_notional,
    is_conformed,
    require_notional,
)
from legvise.model.book import Side
from legvise.model.instrument import Instrument
from legvise.money import dec

MARKET = Instrument.build(
    "kraken",
    "BTC-USD",
    tick_size="0.5",
    lot_step="0.001",
    min_notional="25",
    max_notional="200000",
)


def test_a_size_rounds_down_onto_the_lot_grid() -> None:
    assert conform_size(MARKET, dec("1.23456")) == dec("1.234")


def test_a_size_already_on_the_grid_does_not_move() -> None:
    assert conform_size(MARKET, dec("1.234")) == dec("1.234")


def test_a_size_that_rounds_away_to_nothing_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        conform_size(MARKET, dec("0.0004"))
    assert caught.value.why.startswith("TICK.02")


def test_a_buy_limit_rounds_up_so_it_stays_marketable() -> None:
    assert conform_price(MARKET, dec("100.2"), Side.ASK) == dec("100.5")


def test_a_sell_limit_rounds_down_so_it_stays_marketable() -> None:
    assert conform_price(MARKET, dec("100.2"), Side.BID) == dec("100.0")


def test_a_price_already_on_the_tick_does_not_move_either_way() -> None:
    assert conform_price(MARKET, dec("100.5"), Side.ASK) == dec("100.5")
    assert conform_price(MARKET, dec("100.5"), Side.BID) == dec("100.5")


def test_a_price_of_zero_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        conform_price(MARKET, dec("0"), Side.ASK)
    assert caught.value.why.startswith("TICK.01")


def test_a_sell_limit_that_rounds_below_the_first_tick_is_refused() -> None:
    with pytest.raises(Refused):
        conform_price(MARKET, dec("0.2"), Side.BID)


def test_a_notional_inside_both_limits_fits() -> None:
    assert fits_notional(MARKET, dec("1000"))
    assert not fits_notional(MARKET, dec("24.99"))
    assert not fits_notional(MARKET, dec("200000.01"))


def test_a_notional_under_the_minimum_names_its_clause() -> None:
    with pytest.raises(Refused) as caught:
        require_notional(MARKET, dec("10"))
    assert caught.value.why.startswith("TICK.03")


def test_a_notional_over_the_maximum_names_the_other_clause() -> None:
    with pytest.raises(Refused) as caught:
        require_notional(MARKET, dec("500000"))
    assert caught.value.why.startswith("TICK.04")


def test_a_notional_exactly_on_a_limit_is_accepted() -> None:
    assert require_notional(MARKET, dec("25")) == dec("25")
    assert require_notional(MARKET, dec("200000")) == dec("200000")


def test_conforming_an_order_rounds_both_sides_and_reports_what_it_lost() -> None:
    order = conform_order(MARKET, Side.ASK, dec("100.2"), dec("1.23456"))
    assert order.price == dec("100.5")
    assert order.size == dec("1.234")
    assert order.size_given_up == dec("0.00056")
    assert order.notional == dec("100.5") * dec("1.234")


def test_conforming_reports_the_size_that_was_asked_for() -> None:
    order = conform_order(MARKET, Side.ASK, dec("100.2"), dec("1.23456"))
    assert order.requested_size == dec("1.23456")


def test_an_order_that_rounds_under_the_venue_minimum_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        conform_order(MARKET, Side.ASK, dec("100.2"), dec("0.001"))
    assert caught.value.why.startswith("TICK.03")


def test_an_order_over_the_venue_maximum_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        conform_order(MARKET, Side.ASK, dec("100.2"), dec("3000"))
    assert caught.value.why.startswith("TICK.04")


def test_a_conformed_order_reports_itself_as_on_the_grids() -> None:
    order = conform_order(MARKET, Side.BID, dec("100.2"), dec("1.23456"))
    assert is_conformed(MARKET, order.price, order.size)


def test_an_unrounded_pair_reports_itself_as_off_the_grids() -> None:
    assert not is_conformed(MARKET, dec("100.2"), dec("1.23456"))
