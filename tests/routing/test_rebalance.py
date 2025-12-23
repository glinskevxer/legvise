"""Pricing a transfer, choosing between two, and charging a plan its share."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.model.network import TransferNetwork
from legvise.money import dec
from legvise.routing.rebalance import (
    CarryTerms,
    amortised_bps,
    cheapest_route,
    quote_route,
)

TRX = TransferNetwork.build(
    "USDT",
    "TRX",
    withdraw_fee="1",
    min_withdraw="10",
    confirmations=20,
    minutes_per_confirmation="0.05",
)
ERC20 = TransferNetwork.build(
    "USDT",
    "ERC20",
    withdraw_fee="12",
    min_withdraw="50",
    confirmations=12,
    minutes_per_confirmation="0.2",
)
SLOW_AND_FREE = TransferNetwork.build(
    "USDT",
    "SLOW",
    withdraw_fee="0",
    min_withdraw="10",
    confirmations=120,
    minutes_per_confirmation="1",
)

TERMS = CarryTerms(carry_bps_per_hour=dec("6"), cycles_served=10)


def test_a_quote_splits_the_fee_from_the_carry() -> None:
    quote = quote_route(TRX, dec("10000"), TERMS)
    assert quote.fee == dec("1")
    assert quote.settle_minutes == dec("1.00")
    assert quote.carry == dec("10000") * dec("6") / dec("10000") * (dec("1.00") / dec("60"))


def test_the_total_is_the_fee_plus_the_carry() -> None:
    quote = quote_route(TRX, dec("10000"), TERMS)
    assert quote.total == quote.fee + quote.carry


def test_what_arrives_is_net_of_the_fee_only() -> None:
    assert quote_route(TRX, dec("10000"), TERMS).arrives == dec("9999")


def test_a_slower_network_carries_more(  # noqa: D103
) -> None:
    fast = quote_route(TRX, dec("10000"), TERMS)
    slow = quote_route(SLOW_AND_FREE, dec("10000"), TERMS)
    assert slow.carry > fast.carry
    assert slow.fee < fast.fee


def test_an_amount_under_the_network_minimum_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        quote_route(ERC20, dec("20"), TERMS)
    assert caught.value.why.startswith("BAND.02")


def test_an_amount_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        quote_route(TRX, dec("0"), TERMS)


def test_a_negative_carry_rate_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        quote_route(TRX, dec("100"), CarryTerms(dec("-1"), 10))
    assert caught.value.field == "carry_bps_per_hour"


def test_a_transfer_has_to_serve_at_least_one_cycle() -> None:
    with pytest.raises(BadArgument) as caught:
        quote_route(TRX, dec("100"), CarryTerms(dec("6"), 0))
    assert caught.value.field == "cycles_served"


def test_the_cheapest_route_wins_on_total_cost() -> None:
    chosen = cheapest_route((ERC20, TRX), dec("10000"), TERMS)
    assert chosen.network == "TRX"


def test_a_free_but_slow_network_can_still_lose_on_a_big_transfer() -> None:
    chosen = cheapest_route((SLOW_AND_FREE, TRX), dec("1000000"), TERMS)
    assert chosen.network == "TRX"


def test_a_free_but_slow_network_wins_on_a_small_one() -> None:
    chosen = cheapest_route((SLOW_AND_FREE, TRX), dec("20"), TERMS)
    assert chosen.network == "SLOW"


def test_a_network_that_cannot_take_the_amount_is_skipped(  # noqa: D103
) -> None:
    chosen = cheapest_route((ERC20, TRX), dec("20"), TERMS)
    assert chosen.network == "TRX"


def test_no_open_network_at_all_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        cheapest_route((ERC20,), dec("20"), TERMS)
    assert caught.value.why.startswith("BAND.02")


def test_an_empty_route_set_is_refused() -> None:
    with pytest.raises(Refused):
        cheapest_route((), dec("100"), TERMS)


def test_the_charge_is_divided_across_the_cycles_it_serves() -> None:
    quote = quote_route(TRX, dec("10000"), TERMS)
    one = amortised_bps(quote, dec("1"), dec("50000"), CarryTerms(dec("6"), 1))
    ten = amortised_bps(quote, dec("1"), dec("50000"), TERMS)
    assert ten * 10 == one


def test_a_bigger_plan_carries_a_smaller_share_in_basis_points() -> None:
    quote = quote_route(TRX, dec("10000"), TERMS)
    small = amortised_bps(quote, dec("1"), dec("10000"), TERMS)
    large = amortised_bps(quote, dec("1"), dec("100000"), TERMS)
    assert large < small


def test_the_unit_price_converts_the_moved_asset_into_the_plan_currency() -> None:
    quote = quote_route(TRX, dec("10000"), TERMS)
    at_one = amortised_bps(quote, dec("1"), dec("50000"), TERMS)
    at_two = amortised_bps(quote, dec("2"), dec("50000"), TERMS)
    assert at_two == at_one * 2


def test_a_conversion_price_of_zero_is_refused() -> None:
    quote = quote_route(TRX, dec("10000"), TERMS)
    with pytest.raises(BadArgument):
        amortised_bps(quote, dec("0"), dec("50000"), TERMS)


def test_a_plan_with_no_notional_is_refused() -> None:
    quote = quote_route(TRX, dec("10000"), TERMS)
    with pytest.raises(BadArgument):
        amortised_bps(quote, dec("1"), dec("0"), TERMS)
