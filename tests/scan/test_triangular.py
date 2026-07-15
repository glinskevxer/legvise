"""Walking a venue's currency graph for loops that pay."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import BadArgument
from legvise.model.book import Book
from legvise.money import dec
from legvise.scan.triangular import (
    build_graph,
    find_cycles,
    profitable_cycles,
    starting_assets,
)

AT = dt.datetime(2025, 8, 26, 10, 0, tzinfo=dt.UTC)


def book(symbol: str, bid: str, ask: str) -> Book:
    return Book.build(
        "kraken",
        symbol,
        observed_at=AT,
        bids=((bid, "100"),),
        asks=((ask, "100"),),
    )


def a_venue(eth_usd_bid: str = "5.1", eth_usd_ask: str = "5.2") -> tuple[Book, ...]:
    """Three markets that close a USD, BTC, ETH triangle."""
    return (
        book("BTC-USD", "99.9", "100"),
        book("ETH-BTC", "0.05", "0.0501"),
        book("ETH-USD", eth_usd_bid, eth_usd_ask),
    )


def test_a_market_contributes_an_edge_each_way() -> None:
    graph = build_graph((book("BTC-USD", "99.9", "100"),))
    assert [e.to_asset for e in graph["BTC"]] == ["USD"]
    assert [e.to_asset for e in graph["USD"]] == ["BTC"]


def test_the_sell_edge_carries_the_bid_and_the_buy_edge_the_ask() -> None:
    graph = build_graph((book("BTC-USD", "99.9", "100"),))
    assert graph["BTC"][0].price == dec("99.9")
    assert graph["USD"][0].price == dec("100")


def test_a_one_sided_book_contributes_one_edge() -> None:
    one_sided = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("99.9", "1"),))
    graph = build_graph((one_sided,))
    assert "BTC" in graph
    assert "USD" not in graph


def test_the_graph_lists_every_asset_it_can_leave_from() -> None:
    assert starting_assets(build_graph(a_venue())) == ("BTC", "ETH", "USD")


def test_a_triangle_is_found_from_its_starting_asset() -> None:
    cycles = find_cycles(build_graph(a_venue()), "kraken", start="USD")
    assert len(cycles) == 2
    assert all(c.start == "USD" for c in cycles)


def test_both_directions_of_the_triangle_are_found() -> None:
    cycles = find_cycles(build_graph(a_venue()), "kraken", start="USD")
    assert {c.assets for c in cycles} == {("USD", "BTC", "ETH"), ("USD", "ETH", "BTC")}


def test_a_graph_with_no_loop_finds_nothing() -> None:
    cycles = find_cycles(build_graph((book("BTC-USD", "99.9", "100"),)), "kraken", start="USD")
    assert cycles == ()


def test_a_two_hop_round_trip_is_not_a_cycle() -> None:
    two_markets = (book("BTC-USD", "99.9", "100"), book("ETH-USD", "5", "5.1"))
    assert find_cycles(build_graph(two_markets), "kraken", start="USD") == ()


def test_a_search_shorter_than_three_hops_is_refused() -> None:
    with pytest.raises(BadArgument):
        find_cycles(build_graph(a_venue()), "kraken", start="USD", max_length=2)


def test_a_search_longer_than_the_bound_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        find_cycles(build_graph(a_venue()), "kraken", start="USD", max_length=9)
    assert "bounded at" in caught.value.why


def test_only_the_profitable_direction_survives_the_filter() -> None:
    found = profitable_cycles("kraken", a_venue(), start="USD", min_bps=dec("1"))
    assert len(found) == 1
    assert found[0].gross_bps > dec("1")


def test_a_flat_venue_offers_nothing_above_the_floor() -> None:
    flat = (
        book("BTC-USD", "100", "100.0001"),
        book("ETH-BTC", "0.05", "0.050001"),
        book("ETH-USD", "5", "5.0001"),
    )
    assert profitable_cycles("kraken", flat, start="USD", min_bps=dec("1")) == ()


def test_the_best_loop_comes_first() -> None:
    found = profitable_cycles("kraken", a_venue(), start="USD")
    assert found[0].gross_bps >= found[-1].gross_bps


def test_a_richer_market_makes_the_loop_pay_more() -> None:
    thin = profitable_cycles("kraken", a_venue("5.1", "5.2"), start="USD")[0]
    rich = profitable_cycles("kraken", a_venue("5.4", "5.5"), start="USD")[0]
    assert rich.gross_bps > thin.gross_bps


def test_a_four_hop_loop_is_found_when_asked_for() -> None:
    square = (
        book("BTC-USD", "99.9", "100"),
        book("ETH-BTC", "0.05", "0.0501"),
        book("SOL-ETH", "0.02", "0.0201"),
        book("SOL-USD", "0.1", "0.102"),
    )
    three = find_cycles(build_graph(square), "kraken", start="USD", max_length=3)
    four = find_cycles(build_graph(square), "kraken", start="USD", max_length=4)
    assert three == ()
    assert len(four) == 2


def test_every_found_cycle_visits_each_asset_once() -> None:
    for cycle in find_cycles(build_graph(a_venue()), "kraken", start="USD"):
        assert len(set(cycle.assets)) == cycle.length


def test_starting_somewhere_else_finds_the_same_loop_rotated() -> None:
    from_btc = find_cycles(build_graph(a_venue()), "kraken", start="BTC")
    assert all(c.start == "BTC" for c in from_btc)
    assert len(from_btc) == 2


# Longer loops, and the properties a search over them has to keep.

SQUARE = (
    book("BTC-USD", "99.9", "100"),
    book("ETH-BTC", "0.05", "0.0501"),
    book("SOL-ETH", "0.02", "0.0201"),
    book("SOL-USD", "0.1", "0.102"),
)

STARTS = ("USD", "BTC", "ETH", "SOL")


@pytest.mark.parametrize("start", STARTS)
def test_every_loop_starts_and_ends_where_it_was_asked_to(start: str) -> None:
    for cycle in find_cycles(build_graph(SQUARE), "kraken", start=start, max_length=4):
        assert cycle.start == start
        assert cycle.hops[-1].to_asset == start


@pytest.mark.parametrize("start", STARTS)
def test_every_loop_visits_each_asset_once(start: str) -> None:
    for cycle in find_cycles(build_graph(SQUARE), "kraken", start=start, max_length=4):
        assert len(set(cycle.assets)) == cycle.length


@pytest.mark.parametrize("start", STARTS)
def test_every_hop_joins_the_one_before_it(start: str) -> None:
    for cycle in find_cycles(build_graph(SQUARE), "kraken", start=start, max_length=4):
        for earlier, later in zip(cycle.hops, cycle.hops[1:], strict=False):
            assert earlier.to_asset == later.from_asset


@pytest.mark.parametrize("start", STARTS)
def test_a_longer_search_never_finds_fewer_loops(start: str) -> None:
    graph = build_graph(SQUARE)
    three = find_cycles(graph, "kraken", start=start, max_length=3)
    four = find_cycles(graph, "kraken", start=start, max_length=4)
    assert len(four) >= len(three)


@pytest.mark.parametrize("start", STARTS)
def test_the_loops_from_one_asset_come_in_pairs(start: str) -> None:
    found = find_cycles(build_graph(SQUARE), "kraken", start=start, max_length=4)
    assert len(found) % 2 == 0


@pytest.mark.parametrize("start", STARTS)
def test_reversing_every_loop_flips_the_sign_of_its_edge(start: str) -> None:
    for cycle in find_cycles(build_graph(SQUARE), "kraken", start=start, max_length=4):
        if cycle.gross_bps == dec("0"):
            continue
        assert (cycle.gross_bps > 0) != (cycle.reversed().gross_bps > 0)


@pytest.mark.parametrize("floor", ["0", "1", "10", "100", "10000"])
def test_a_higher_screen_never_keeps_more(floor: str) -> None:
    loose = profitable_cycles("kraken", SQUARE, start="USD", min_bps=dec("0"), max_length=4)
    tight = profitable_cycles("kraken", SQUARE, start="USD", min_bps=dec(floor), max_length=4)
    assert len(tight) <= len(loose)


@pytest.mark.parametrize("floor", ["0", "1", "10"])
def test_everything_kept_clears_the_floor(floor: str) -> None:
    for cycle in profitable_cycles("kraken", SQUARE, start="USD", min_bps=dec(floor), max_length=4):
        assert cycle.gross_bps >= dec(floor)


def test_the_kept_loops_come_back_best_first() -> None:
    found = profitable_cycles("kraken", SQUARE, start="USD", max_length=4)
    edges = [cycle.gross_bps for cycle in found]
    assert edges == sorted(edges, reverse=True)


def test_a_graph_missing_one_market_closes_no_square() -> None:
    broken = tuple(b for b in SQUARE if str(b.symbol) != "SOL-USD")
    assert find_cycles(build_graph(broken), "kraken", start="USD", max_length=4) == ()


def test_a_square_offers_nothing_at_three_hops_from_any_start() -> None:
    graph = build_graph(SQUARE)
    for start in STARTS:
        assert find_cycles(graph, "kraken", start=start, max_length=3) == ()


def test_the_search_is_the_same_twice() -> None:
    graph = build_graph(SQUARE)
    first = find_cycles(graph, "kraken", start="USD", max_length=4)
    second = find_cycles(graph, "kraken", start="USD", max_length=4)
    assert [c.assets for c in first] == [c.assets for c in second]
