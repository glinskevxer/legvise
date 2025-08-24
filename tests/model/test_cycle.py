"""Hops, cycles, and the product that decides whether a loop pays."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.cycle import Cycle, Hop
from legvise.money import dec


def hop(from_asset: str, to_asset: str, symbol: str, price: str) -> Hop:
    return Hop(
        from_asset=from_asset,
        to_asset=to_asset,
        symbol=parse_symbol(symbol),
        price=dec(price),
    )


def a_triangle(btc_usd: str = "100", eth_btc: str = "0.05", eth_usd: str = "5.1") -> Cycle:
    """USD to BTC to ETH and back to USD."""
    return Cycle(
        venue="kraken",
        hops=(
            hop("USD", "BTC", "BTC-USD", btc_usd),
            hop("BTC", "ETH", "ETH-BTC", eth_btc),
            hop("ETH", "USD", "ETH-USD", eth_usd),
        ),
    )


def test_selling_the_base_takes_the_bid_at_the_price() -> None:
    selling = hop("BTC", "USD", "BTC-USD", "100")
    assert selling.takes is Side.BID
    assert selling.is_sell
    assert selling.rate == dec("100")


def test_buying_the_base_takes_the_ask_at_the_inverse() -> None:
    buying = hop("USD", "BTC", "BTC-USD", "100")
    assert buying.takes is Side.ASK
    assert not buying.is_sell
    assert buying.rate == dec("1") / dec("100")


def test_a_hop_converts_an_amount() -> None:
    assert hop("BTC", "USD", "BTC-USD", "100").convert(dec("2")) == dec("200")


def test_a_hop_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        hop("BTC", "USD", "BTC-USD", "100").convert(dec("0"))


def test_a_hop_that_changes_nothing_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        hop("BTC", "BTC", "BTC-USD", "100")
    assert "change something" in caught.value.why


def test_a_hop_on_a_market_that_does_not_connect_the_pair_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        hop("BTC", "USD", "ETH-USD", "100")
    assert "does not connect" in caught.value.why


def test_a_hop_with_no_price_is_refused() -> None:
    with pytest.raises(BadArgument):
        hop("BTC", "USD", "BTC-USD", "0")


def test_a_triangle_starts_and_ends_at_the_same_asset() -> None:
    cycle = a_triangle()
    assert cycle.start == "USD"
    assert cycle.assets == ("USD", "BTC", "ETH")
    assert cycle.length == 3


def test_a_flat_triangle_comes_back_to_one() -> None:
    flat = a_triangle(btc_usd="100", eth_btc="0.05", eth_usd="5")
    assert flat.product == dec("1")
    assert flat.gross_bps == dec("0")


def test_a_profitable_triangle_comes_back_above_one() -> None:
    assert a_triangle().gross_bps > dec("0")


def test_a_losing_triangle_comes_back_below_one() -> None:
    assert a_triangle(eth_usd="4.9").gross_bps < dec("0")


def test_the_edge_compounds_rather_than_adding() -> None:
    cycle = a_triangle(btc_usd="100", eth_btc="0.05", eth_usd="5.1")
    assert cycle.product == dec("5.1") / dec("5")


def test_a_cycle_needs_three_hops() -> None:
    with pytest.raises(BadArgument) as caught:
        Cycle(
            venue="kraken",
            hops=(hop("USD", "BTC", "BTC-USD", "100"), hop("BTC", "USD", "BTC-USD", "100")),
        )
    assert caught.value.field == "hops"


def test_hops_that_do_not_join_up_are_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        Cycle(
            venue="kraken",
            hops=(
                hop("USD", "BTC", "BTC-USD", "100"),
                hop("ETH", "USD", "ETH-USD", "5"),
                hop("USD", "ETH", "ETH-USD", "5"),
            ),
        )
    assert "starts where the last one finished" in caught.value.why


def test_a_loop_that_does_not_come_home_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        Cycle(
            venue="kraken",
            hops=(
                hop("USD", "BTC", "BTC-USD", "100"),
                hop("BTC", "ETH", "ETH-BTC", "0.05"),
                hop("ETH", "SOL", "SOL-ETH", "0.02"),
            ),
        )
    assert "comes back to where it began" in caught.value.why


def test_reversing_a_triangle_walks_it_the_other_way() -> None:
    forward = a_triangle()
    backward = forward.reversed()
    assert backward.assets == ("USD", "ETH", "BTC")
    assert backward.start == "USD"


def test_a_profitable_triangle_reversed_loses() -> None:
    forward = a_triangle()
    assert forward.gross_bps > 0
    assert forward.reversed().gross_bps < 0


def test_reversing_twice_returns_the_original_product() -> None:
    forward = a_triangle()
    assert forward.reversed().reversed().product == forward.product
