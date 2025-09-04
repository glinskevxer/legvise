"""The loop command group."""

from __future__ import annotations

import pytest

from tests.cli.conftest import Run

TRIANGLE = (
    ("BTC-USD", "99.9", "100"),
    ("ETH-BTC", "0.05", "0.0501"),
    ("ETH-USD", "5.012", "5.02"),
)


@pytest.fixture()
def venue(run: Run) -> Run:
    run(
        "venue",
        "add",
        "kraken",
        "Kraken",
        "--staleness-ms",
        "600000",
        "--depth-bps",
        "500",
        "--cap",
        "10000000",
    )
    run("fee", "set-ladder", "kraken", "0:0:0")
    run("fee", "record-volume", "kraken", "0")
    for symbol, _, _ in TRIANGLE:
        run(
            "instrument",
            "add",
            "kraken",
            symbol,
            "--tick",
            "0.0001",
            "--lot",
            "0.00001",
            "--min-notional",
            "1",
            "--max-notional",
            "10000000",
        )
    return run


def load(run: Run) -> None:
    for symbol, bid, ask in TRIANGLE:
        run(
            "book",
            "load",
            "kraken",
            symbol,
            "--bid",
            f"{bid}:10000",
            "--ask",
            f"{ask}:10000",
        )


def test_a_pass_with_no_books_searches_nothing(venue: Run) -> None:
    assert "venues    0" in venue("loop", "run").output


def test_a_pass_over_a_closed_triangle_writes_a_plan(venue: Run) -> None:
    load(venue)
    output = venue("loop", "run", "--amount", "1000").output
    assert "venues    1" in output
    assert "written   1" in output


def test_a_taker_fee_kills_the_loop(venue: Run) -> None:
    load(venue)
    venue("fee", "set-ladder", "kraken", "0:0:16")
    assert "written   0" in venue("loop", "run", "--amount", "1000").output


def test_a_higher_floor_turns_the_loop_down(venue: Run) -> None:
    load(venue)
    output = venue("loop", "run", "--amount", "1000", "--min-edge-bps", "50").output
    assert "written   0" in output


def test_the_screen_lists_the_loops_at_the_touch(venue: Run) -> None:
    load(venue)
    output = venue("loop", "screen", "kraken").output
    assert "USD -> BTC -> ETH -> USD" in output


def test_the_screen_says_so_when_nothing_qualifies(venue: Run) -> None:
    load(venue)
    output = venue("loop", "screen", "kraken", "--min-bps", "500").output
    assert "no loop from USD" in output


def test_the_screen_takes_a_different_starting_asset(venue: Run) -> None:
    load(venue)
    assert "BTC" in venue("loop", "screen", "kraken", "--start", "BTC").output


def test_the_graph_prints_both_directions_of_each_market(venue: Run) -> None:
    load(venue)
    lines = venue("loop", "graph", "kraken").output.strip().splitlines()
    assert len(lines) == 8


def test_a_venue_with_no_books_has_an_empty_graph(venue: Run) -> None:
    lines = venue("loop", "graph", "kraken").output.strip().splitlines()
    assert len(lines) == 2


def test_the_cross_screen_needs_two_venues(venue: Run) -> None:
    load(venue)
    lines = venue("loop", "cross", "BTC-USD").output.strip().splitlines()
    assert len(lines) == 2


def test_the_cross_screen_reports_both_directions(venue: Run) -> None:
    load(venue)
    venue(
        "venue",
        "add",
        "okx",
        "OKX",
        "--staleness-ms",
        "600000",
        "--depth-bps",
        "500",
        "--cap",
        "10000000",
    )
    venue(
        "instrument",
        "add",
        "okx",
        "BTC-USD",
        "--tick",
        "0.01",
        "--lot",
        "0.0001",
        "--min-notional",
        "10",
        "--max-notional",
        "10000000",
    )
    venue("book", "load", "okx", "BTC-USD", "--bid", "101:10", "--ask", "102:10")
    lines = venue("loop", "cross", "BTC-USD").output.strip().splitlines()
    assert len(lines) == 4


def test_a_loop_longer_than_the_bound_is_refused(venue: Run) -> None:
    load(venue)
    venue("loop", "screen", "kraken", "--max-hops", "9", expect=1)


def test_two_passes_need_different_counters(venue: Run) -> None:
    load(venue)
    venue("loop", "run", "--counter", "0")
    venue("loop", "run", "--counter", "0", expect=1)
