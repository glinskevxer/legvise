"""The network command group."""

from __future__ import annotations

import pytest

from tests.cli.conftest import Run


@pytest.fixture()
def wired(seeded: Run) -> Run:
    seeded(
        "network",
        "add",
        "USDT",
        "TRX",
        "--fee",
        "1",
        "--min-withdraw",
        "10",
        "--confirmations",
        "20",
        "--block-minutes",
        "0.05",
    )
    seeded(
        "network",
        "add",
        "USDT",
        "ERC20",
        "--fee",
        "12",
        "--min-withdraw",
        "50",
        "--confirmations",
        "12",
        "--block-minutes",
        "0.2",
    )
    return seeded


def both_ends(run: Run, code: str) -> None:
    for venue in ("kraken", "okx"):
        run("network", "support", venue, "USDT", code)


def test_adding_a_network_reports_its_settlement_time(seeded: Run) -> None:
    result = seeded(
        "network",
        "add",
        "USDT",
        "TRX",
        "--fee",
        "1",
        "--min-withdraw",
        "10",
        "--confirmations",
        "20",
        "--block-minutes",
        "0.05",
    )
    assert "settles in 1.00 min" in result.output


def test_a_network_with_no_confirmations_is_refused(seeded: Run) -> None:
    seeded(
        "network",
        "add",
        "USDT",
        "TRX",
        "--fee",
        "1",
        "--min-withdraw",
        "10",
        "--confirmations",
        "0",
        "--block-minutes",
        "0.05",
        expect=1,
    )


def test_listing_networks_shows_both(wired: Run) -> None:
    output = wired("network", "list", "USDT").output
    assert "TRX" in output
    assert "ERC20" in output


def test_support_reports_both_directions(wired: Run) -> None:
    result = wired("network", "support", "kraken", "USDT", "TRX")
    assert "deposit on" in result.output
    assert "withdraw on" in result.output


def test_support_can_be_switched_off_one_way(wired: Run) -> None:
    result = wired("network", "support", "kraken", "USDT", "TRX", "--no-withdraw")
    assert "withdraw off" in result.output


def test_support_for_a_network_nobody_declared_is_refused(wired: Run) -> None:
    wired("network", "support", "kraken", "USDT", "SOLANA", expect=1)


def test_no_route_says_so(wired: Run) -> None:
    result = wired("network", "routes", "USDT", "kraken", "okx")
    assert "no open route" in result.output


def test_a_route_appears_once_both_ends_agree(wired: Run) -> None:
    both_ends(wired, "TRX")
    assert wired("network", "routes", "USDT", "kraken", "okx").output.strip() == "TRX"


def test_a_one_way_suspension_closes_the_route(wired: Run) -> None:
    wired("network", "support", "kraken", "USDT", "TRX", "--no-withdraw")
    wired("network", "support", "okx", "USDT", "TRX")
    assert "no open route" in wired("network", "routes", "USDT", "kraken", "okx").output


def test_pricing_a_route_picks_the_cheaper_one(wired: Run) -> None:
    both_ends(wired, "TRX")
    both_ends(wired, "ERC20")
    chosen = wired("network", "routes", "USDT", "kraken", "okx", "--amount", "1000").output
    assert chosen.strip() == "TRX"


def test_pricing_an_amount_no_route_can_take_fails(wired: Run) -> None:
    both_ends(wired, "ERC20")
    result = wired("network", "routes", "USDT", "kraken", "okx", "--amount", "5", expect=1)
    assert "no open route" in result.output


def test_the_cost_command_prints_basis_points(wired: Run) -> None:
    both_ends(wired, "TRX")
    output = wired(
        "network",
        "cost",
        "USDT",
        "kraken",
        "okx",
        "1000",
        "--price",
        "1",
        "--notional",
        "50000",
    ).output
    assert float(output.strip()) > 0


def test_the_cost_command_charges_the_stranding_rate_with_no_route(wired: Run) -> None:
    output = wired(
        "network",
        "cost",
        "USDT",
        "kraken",
        "okx",
        "1000",
        "--price",
        "1",
        "--notional",
        "50000",
        "--stranded-bps",
        "300",
    ).output
    assert output.strip().startswith("300")


def test_no_excess_costs_nothing(wired: Run) -> None:
    output = wired(
        "network",
        "cost",
        "USDT",
        "kraken",
        "okx",
        "0",
        "--price",
        "1",
        "--notional",
        "50000",
    ).output
    assert float(output.strip()) == 0
