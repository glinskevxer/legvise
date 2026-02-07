"""The audit command group."""

from __future__ import annotations

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


def test_the_ledger_lists_every_decision_the_scan_took(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    lines = desk("audit", "session", session).output.strip().splitlines()
    assert len(lines) >= 4


def test_the_ledger_records_the_screened_direction(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    output = desk("audit", "session", session, "--stage", "screened").output
    assert "does not cross" in output


def test_the_ledger_records_the_priced_direction(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    output = desk("audit", "session", session, "--stage", "priced").output
    assert session in output


def test_a_stage_nobody_reached_prints_an_empty_table(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    lines = desk("audit", "session", session, "--stage", "refused").output.strip().splitlines()
    assert len(lines) == 2


def test_an_unknown_stage_is_a_usage_error(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    desk("audit", "session", session, "--stage", "guessed", expect=2)


def test_a_limit_says_how_many_rows_it_held_back(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    result = desk("audit", "session", session, "--limit", "1")
    assert "more not shown" in result.output


def test_the_stage_counts_come_back_busiest_first(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    lines = desk("audit", "stages", session).output.strip().splitlines()[2:]
    counts = [int(line.split()[-1]) for line in lines if line.strip()]
    assert counts == sorted(counts, reverse=True)


def test_a_session_that_decided_nothing_says_so(scanned: tuple[Run, str]) -> None:
    desk, _ = scanned
    assert "took no decisions" in desk("audit", "stages", "S19990101.0001").output


def test_the_shape_reports_the_cheap_share(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    output = desk("audit", "shape", session).output
    assert "cheap share" in output
    assert "decisions" in output


def test_a_healthy_scan_is_mostly_cheap_stages(scanned: tuple[Run, str]) -> None:
    desk, session = scanned
    line = next(
        row
        for row in desk("audit", "shape", session).output.splitlines()
        if row.startswith("cheap share")
    )
    assert int(line.split()[-1].rstrip("%")) >= 50


def test_the_shape_of_a_session_with_no_decisions_fails(scanned: tuple[Run, str]) -> None:
    desk, _ = scanned
    desk("audit", "shape", "S19990101.0001", expect=1)


def test_the_clause_counts_are_empty_when_nothing_was_refused(
    scanned: tuple[Run, str],
) -> None:
    desk, session = scanned
    lines = desk("audit", "clauses", session).output.strip().splitlines()
    assert len(lines) == 2


def test_a_stale_scan_records_its_clause_in_the_ledger(run: Run) -> None:
    desk = wire(run)
    desk(
        "book",
        "load",
        "kraken",
        "BTC-USD",
        "--bid",
        "99.00:50",
        "--ask",
        "100.00:50",
        "--observed-at",
        "2020-01-01T00:00:00+00:00",
    )
    desk(
        "book",
        "load",
        "okx",
        "BTC-USD",
        "--bid",
        "101.00:50",
        "--ask",
        "102.00:50",
        "--observed-at",
        "2020-01-01T00:00:00+00:00",
    )
    output = desk("scan", "run", "--window-ms", "600000").output
    session = next(line.split()[1] for line in output.splitlines() if line.startswith("session"))
    assert "STALE.01" in desk("audit", "clauses", session).output
