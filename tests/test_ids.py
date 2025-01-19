"""Canonical spellings for venues, assets, markets and the desk's own handles."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ids import (
    Symbol,
    asset_code,
    parse_symbol,
    plan_ref,
    session_ref,
    symbol_text,
    venue_code,
)


def test_a_venue_code_comes_back_lower_case_and_trimmed() -> None:
    assert venue_code("  Kraken ") == "kraken"


@pytest.mark.parametrize("bad", ["", "k", "kr", "1kraken", "kraken-eu", "Kraken Pro"])
def test_a_venue_code_that_breaks_the_shape_is_refused(bad: str) -> None:
    with pytest.raises(BadArgument):
        venue_code(bad)


def test_an_asset_code_comes_back_upper_case() -> None:
    assert asset_code(" btc ") == "BTC"
    assert asset_code("usdt") == "USDT"


@pytest.mark.parametrize("bad", ["", "B", "BITCOIN-CASH", "bt c"])
def test_an_asset_code_that_breaks_the_shape_is_refused(bad: str) -> None:
    with pytest.raises(BadArgument):
        asset_code(bad)


def test_a_symbol_splits_into_base_and_quote() -> None:
    sym = parse_symbol("btc-usdt")
    assert sym == Symbol("BTC", "USDT")
    assert sym.base == "BTC"
    assert sym.quote == "USDT"


def test_a_symbol_prints_the_canonical_way() -> None:
    assert symbol_text(parse_symbol("eth-usd")) == "ETH-USD"
    assert str(Symbol("SOL", "USDC")) == "SOL-USDC"


def test_inverting_a_symbol_swaps_the_sides() -> None:
    assert parse_symbol("BTC-USD").inverted() == Symbol("USD", "BTC")


@pytest.mark.parametrize("bad", ["BTCUSD", "BTC-USD-PERP", "BTC-", "-USD"])
def test_a_symbol_needs_exactly_one_separator(bad: str) -> None:
    with pytest.raises(BadArgument):
        parse_symbol(bad)


def test_a_market_cannot_quote_an_asset_in_itself() -> None:
    with pytest.raises(BadArgument) as caught:
        parse_symbol("USD-USD")
    assert "in itself" in caught.value.why


def test_a_session_reference_carries_the_day_it_started() -> None:
    assert session_ref("2025-03-04T09:15:00+00:00", 7) == "S20250304.0007"


def test_a_session_reference_needs_a_timestamp() -> None:
    with pytest.raises(BadArgument):
        session_ref("March 4th", 1)


def test_a_negative_session_counter_is_refused() -> None:
    with pytest.raises(BadArgument):
        session_ref("2025-03-04T09:15:00+00:00", -1)


def test_a_plan_reference_hangs_off_its_session() -> None:
    session = session_ref("2025-03-04T09:15:00+00:00", 2)
    assert plan_ref(session, 12) == "S20250304.0002/P012"


def test_a_plan_reference_refuses_a_handle_that_is_not_a_session() -> None:
    with pytest.raises(BadArgument):
        plan_ref("20250304.0002", 1)
