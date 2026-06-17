"""The scan command group, driven through the real command tree."""

from __future__ import annotations

from tests.cli.conftest import Run


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


def test_a_dry_run_says_it_wrote_nothing(desk: Run) -> None:
    assert "dry run     nothing was written" in desk("scan", "run", "--dry-run").output


def test_a_dry_run_leaves_no_session_behind(desk: Run) -> None:
    desk("scan", "run", "--dry-run")
    lines = desk("scan", "sessions").output.strip().splitlines()
    assert len(lines) == 2


def test_a_dry_run_can_be_repeated_with_the_same_counter(desk: Run) -> None:
    desk("scan", "run", "--dry-run")
    desk("scan", "run", "--dry-run")


def test_a_dry_run_prices_the_same_pairs_as_a_real_one(desk: Run) -> None:
    desk("book", "load", "kraken", "BTC-USD", "--bid", "99.00:50", "--ask", "100.00:50")
    desk("book", "load", "okx", "BTC-USD", "--bid", "101.00:50", "--ask", "102.00:50")
    dry = desk("scan", "run", "--dry-run", "--window-ms", "600000").output
    wet = desk("scan", "run", "--window-ms", "600000").output
    assert "priced      1" in dry
    assert "priced      1" in wet
