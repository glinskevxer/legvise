"""One order inside a plan, and the two balances it moves."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.leg import Leg
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


def test_a_leg_knows_its_notional() -> None:
    assert a_leg().notional == dec("200")


def test_a_leg_that_takes_the_asks_is_a_buy() -> None:
    assert a_leg(takes=Side.ASK).is_buy
    assert not a_leg(takes=Side.BID).is_buy


def test_a_buy_brings_the_base_in_and_sends_the_quote_out() -> None:
    leg = a_leg(takes=Side.ASK)
    assert leg.base_delta == dec("2")
    assert leg.quote_delta == dec("-200")


def test_a_sell_sends_the_base_out_and_brings_the_quote_in() -> None:
    leg = a_leg(takes=Side.BID)
    assert leg.base_delta == dec("-2")
    assert leg.quote_delta == dec("200")


@pytest.mark.parametrize("field", ["price", "size"])
def test_a_leg_of_nothing_is_refused(field: str) -> None:
    changes: dict[str, object] = {field: dec("0")}
    with pytest.raises(BadArgument) as caught:
        a_leg("kraken", Side.ASK, **changes)
    assert caught.value.field == field


def test_a_leg_touches_at_least_one_level() -> None:
    with pytest.raises(BadArgument):
        a_leg(levels_swept=0)


def test_a_negative_slippage_figure_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_leg(slippage_bps=dec("-1"))


def test_a_venue_code_that_is_not_normalised_is_refused() -> None:
    # A leg is built by the scanner from a venue record whose code is already
    # normalised, so this refuses rather than normalising a second time.
    with pytest.raises(BadArgument) as caught:
        a_leg(" Kraken ")
    assert caught.value.field == "venue"


def test_a_leg_is_immutable_once_it_is_built() -> None:
    leg = a_leg()
    with pytest.raises(AttributeError):
        leg.size = dec("1")  # type: ignore[misc]


def test_the_base_and_quote_deltas_cancel_across_a_matched_pair() -> None:
    bought = a_leg("kraken", Side.ASK)
    sold = a_leg("okx", Side.BID)
    assert bought.base_delta + sold.base_delta == dec("0")
