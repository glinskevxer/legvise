"""The scan command group, driven through the real command tree."""

from __future__ import annotations

import pytest

from tests.cli.conftest import Run


def wire(run: Run) -> Run:
    """Two venues, one market each, fees, balances and bands."""
    for code, name in (("kraken", "Kraken"), ("okx", "OKX")):
        run(
            "venue",
            "add",
            code,
            name,
            "--staleness-ms",
            "600000",
            "--depth-bps",
            "500",
            "--cap",
            "10000000",
        )
        run(
            "instrument",
            "add",
            code,
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
        run("fee", "set-ladder", code, "0:0:5")
        run("fee", "record-volume", code, "0")
        run("inventory", "set-balance", code, "BTC", "50")
        run("inventory", "set-balance", code, "USD", "5000000")
        run(
            "inventory",
            "set-band",
            code,
            "BTC",
            "--floor",
            "0",
            "--target",
            "25",
            "--ceiling",
            "1000",
        )
        run(
            "inventory",
            "set-band",
            code,
            "USD",
            "--floor",
            "0",
            "--target",
            "1000000",
            "--ceiling",
            "50000000",
        )
    return run


@pytest.fixture()
def desk(run: Run) -> Run:
    return wire(run)


def test_a_scan_with_no_books_reports_nothing_priced(desk: Run) -> None:
    output = desk("scan", "run").output
    assert "priced      0" in output
    assert "session     S" in output


def test_a_scan_lists_its_session_afterwards(desk: Run) -> None:
    desk("scan", "run")
    assert "S2" in desk("scan", "sessions").output


def test_two_scans_need_different_counters(desk: Run) -> None:
    desk("scan", "run", "--counter", "0")
    desk("scan", "run", "--counter", "1")
    lines = desk("scan", "sessions").output.strip().splitlines()
    assert len(lines) == 4


def test_reusing_a_counter_in_one_day_is_refused(desk: Run) -> None:
    desk("scan", "run", "--counter", "0")
    desk("scan", "run", "--counter", "0", expect=1)


def test_the_refusals_command_reports_nothing_on_an_empty_scan(desk: Run) -> None:
    desk("scan", "run")
    lines = desk("scan", "refusals").output.strip().splitlines()
    assert len(lines) == 2


def test_a_bad_edge_floor_is_refused_before_the_scan_starts(desk: Run) -> None:
    desk("scan", "run", "--min-edge-bps", "loads", expect=1)


def test_a_cap_of_zero_is_refused(desk: Run) -> None:
    desk("scan", "run", "--gross-cap", "0", expect=1)


def test_a_scan_reports_the_venues_it_had_to_skip(desk: Run) -> None:
    desk("fee", "clear-volume", "okx")
    result = desk("scan", "run")
    assert "skipped" in result.output


def test_the_sessions_listing_takes_a_limit(desk: Run) -> None:
    for counter in range(3):
        desk("scan", "run", "--counter", str(counter))
    lines = desk("scan", "sessions", "--limit", "2").output.strip().splitlines()
    assert len(lines) == 4


def test_the_scan_accepts_every_knob_at_once(desk: Run) -> None:
    desk(
        "scan",
        "run",
        "--min-edge-bps",
        "5",
        "--window-ms",
        "500",
        "--size",
        "2",
        "--venue-cap",
        "500000",
        "--asset-cap",
        "800000",
        "--gross-cap",
        "2000000",
        "--carry-bps-hour",
        "4",
        "--cycles",
        "20",
        "--stranded-bps",
        "400",
    )
