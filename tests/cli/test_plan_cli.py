"""The plan command group, run against a scan that actually found something."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.cli.conftest import Run, session_of, wire


def test_the_scan_found_one_plan(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    lines = desk("plan", "list", session).output.strip().splitlines()
    assert len(lines) == 3


def test_the_listing_names_both_venues(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    assert "kraken/okx" in desk("plan", "list", session).output


def test_the_listing_can_skip_the_refused_ones(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    assert "priced" in desk("plan", "list", session, "--actionable").output


def test_showing_a_plan_prints_the_whole_decomposition(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    ref = desk("plan", "best", session).output.split()[0]
    output = desk("plan", "show", ref).output
    for label in ("gross", "fees", "slippage", "rebalance", "net", "status"):
        assert label in output


def test_showing_a_plan_prints_both_legs(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    ref = desk("plan", "best", session).output.split()[0]
    output = desk("plan", "show", ref).output
    assert "buy" in output
    assert "sell" in output


def test_a_plan_that_is_not_there_fails(scanned: tuple[Run, str]) -> None:
    desk, _ = scanned
    result = desk("plan", "show", "S19990101.0001/P000", expect=1)
    assert "plan" in result.output


def test_best_prints_the_reference_and_the_edge(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    line = desk("plan", "best", session).output.strip().splitlines()[0]
    assert line.startswith(session)
    assert len(line.split()) == 2


def test_the_best_command_takes_a_count(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    assert len(desk("plan", "best", session, "--count", "1").output.strip().splitlines()) == 1


def test_best_says_so_when_nothing_was_actionable(run: Run) -> None:
    desk = wire(run)
    output = desk("scan", "run").output
    session = session_of(output)
    assert "nothing was actionable" in desk("plan", "best", session).output


def test_the_check_command_passes_on_a_healthy_session(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    assert "every plan adds up" in desk("plan", "check", session).output


def test_the_check_command_catches_a_plan_that_was_tampered_with(
    scanned: tuple[Run, str], book: Path
) -> None:
    desk, session = scanned
    ref = desk("plan", "best", session).output.split()[0]
    conn = sqlite3.connect(book)
    conn.execute("UPDATE plan SET net_bps = '999' WHERE ref = ?", (ref,))
    conn.commit()
    conn.close()
    result = desk("plan", "check", session, expect=1)
    assert "do not add up" in result.output


def test_the_rank_command_lists_what_each_plan_makes(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    output = desk("plan", "rank", session).output
    assert "makes" in output
    assert "adjusted" in output


def test_the_rank_command_reports_the_depth_penalty(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    output = desk("plan", "rank", session, "--depth-penalty-bps", "2").output
    assert "penalty" in output


def test_a_venue_weight_is_accepted(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    desk("plan", "rank", session, "--venue-weight", "okx:0.5")


def test_a_venue_weight_that_is_not_a_pair_is_a_usage_error(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    result = desk("plan", "rank", session, "--venue-weight", "okx", expect=2)
    assert "VENUE:WEIGHT" in result.output


def test_a_venue_weight_of_zero_is_refused(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    desk("plan", "rank", session, "--venue-weight", "okx:0", expect=1)


def test_ranking_a_session_with_nothing_sendable_says_so(desk: Run) -> None:
    output = desk("scan", "run").output
    session = session_of(output)
    assert "nothing was actionable" in desk("plan", "rank", session).output
