"""The plan command group, run against a scan that actually found something."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.cli.conftest import Run
from tests.cli.test_scan_cli import wire


@pytest.fixture()
def scanned(run: Run) -> tuple[Run, str]:
    desk = wire(run)
    desk("book", "load", "kraken", "BTC-USD", "--bid", "99.00:50", "--ask", "100.00:50")
    desk("book", "load", "okx", "BTC-USD", "--bid", "101.00:50", "--ask", "102.00:50")
    output = desk("scan", "run", "--window-ms", "600000").output
    session = next(line.split()[1] for line in output.splitlines() if line.startswith("session"))
    return (desk, session)


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


def test_best_takes_a_count(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    assert len(desk("plan", "best", session, "--count", "1").output.strip().splitlines()) == 1


def test_best_says_so_when_nothing_was_actionable(run: Run) -> None:
    desk = wire(run)
    output = desk("scan", "run").output
    session = next(line.split()[1] for line in output.splitlines() if line.startswith("session"))
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
