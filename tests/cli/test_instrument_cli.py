"""The instrument command group."""

from __future__ import annotations

import pytest

from tests.cli.conftest import Run


def add_market(run: Run, venue: str, symbol: str, **extra: str) -> None:
    args = [
        "instrument",
        "add",
        venue,
        symbol,
        "--tick",
        extra.get("tick", "0.1"),
        "--lot",
        extra.get("lot", "0.00001"),
        "--min-notional",
        extra.get("min_notional", "10"),
        "--max-notional",
        extra.get("max_notional", "500000"),
    ]
    if "venue_symbol" in extra:
        args += ["--venue-symbol", extra["venue_symbol"]]
    run(*args)


@pytest.fixture()
def markets(seeded: Run) -> Run:
    add_market(seeded, "kraken", "BTC-USD", venue_symbol="XBTUSD")
    add_market(seeded, "okx", "BTC-USD")
    add_market(seeded, "kraken", "SOL-USD")
    return seeded


def test_adding_a_market_reports_the_pair_and_the_venue(seeded: Run) -> None:
    add_market(seeded, "kraken", "BTC-USD")
    assert "BTC-USD" in seeded("instrument", "list").output


def test_a_market_on_a_venue_that_is_not_on_file_is_refused(run: Run) -> None:
    run(
        "instrument",
        "add",
        "nowhere",
        "BTC-USD",
        "--tick",
        "0.1",
        "--lot",
        "0.001",
        "--min-notional",
        "10",
        "--max-notional",
        "5000",
        expect=1,
    )


def test_the_venue_spelling_shows_up_in_the_listing(markets: Run) -> None:
    assert "XBTUSD" in markets("instrument", "list", "--venue", "kraken").output


def test_listing_by_venue_leaves_the_other_venue_out(markets: Run) -> None:
    output = markets("instrument", "list", "--venue", "okx").output
    assert "SOL-USD" not in output
    assert "BTC-USD" in output


def test_listing_by_symbol_crosses_the_venues(markets: Run) -> None:
    output = markets("instrument", "list", "--symbol", "BTC-USD").output
    assert "kraken" in output
    assert "okx" in output


def test_listing_by_venue_and_symbol_at_once_is_a_usage_error(markets: Run) -> None:
    result = markets("instrument", "list", "--venue", "okx", "--symbol", "BTC-USD", expect=2)
    assert "not both" in result.output


def test_listing_everything_covers_both_venues(markets: Run) -> None:
    lines = markets("instrument", "list").output.strip().splitlines()
    assert len(lines) == 5


def test_shared_names_only_the_markets_on_two_venues(markets: Run) -> None:
    output = markets("instrument", "shared").output
    assert output.strip() == "BTC-USD"


def test_shared_says_so_when_nothing_qualifies(markets: Run) -> None:
    result = markets("instrument", "shared", "--min-venues", "3")
    assert "no market is live on 3 venues" in result.output


def test_disabling_a_market_takes_it_out_of_shared(markets: Run) -> None:
    markets("instrument", "disable", "okx", "BTC-USD")
    assert "BTC-USD" not in markets("instrument", "shared").output


def test_disabling_a_market_that_is_not_there_fails(markets: Run) -> None:
    result = markets("instrument", "disable", "okx", "DOGE-USD", expect=1)
    assert "okx:DOGE-USD" in result.output


def test_a_market_that_breaks_a_filter_rule_never_reaches_the_store(seeded: Run) -> None:
    add_market_args = [
        "instrument",
        "add",
        "kraken",
        "BTC-USD",
        "--tick",
        "0.1",
        "--lot",
        "0.001",
        "--min-notional",
        "1000",
        "--max-notional",
        "100",
    ]
    seeded(*add_market_args, expect=1)
    assert "BTC-USD" not in seeded("instrument", "list").output
