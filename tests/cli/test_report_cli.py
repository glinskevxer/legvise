"""The report command group."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.cli.conftest import Run
from tests.cli.test_scan_cli import wire


@pytest.fixture()
def traded(run: Run) -> tuple[Run, str, str]:
    desk = wire(run)
    desk("book", "load", "kraken", "BTC-USD", "--bid", "99.00:50", "--ask", "100.00:50")
    desk("book", "load", "okx", "BTC-USD", "--bid", "101.00:50", "--ask", "102.00:50")
    output = desk("scan", "run", "--window-ms", "600000", "--size", "2").output
    session = next(line.split()[1] for line in output.splitlines() if line.startswith("session"))
    ref = desk("plan", "best", session).output.split()[0]
    return (desk, session, ref)


def test_a_session_report_prints_the_counts(traded: tuple[Run, str, str]) -> None:
    desk, session, _ = traded
    output = desk("report", "session", session).output
    assert "plans       1" in output
    assert "actionable  1" in output


def test_a_session_report_prints_the_best_edge(traded: tuple[Run, str, str]) -> None:
    desk, session, _ = traded
    assert "best " in desk("report", "session", session).output


def test_a_session_report_lists_the_clauses_that_fired(run: Run) -> None:
    desk = wire(run)
    desk("book", "load", "kraken", "BTC-USD", "--bid", "99.00:50", "--ask", "100.00:50")
    desk("book", "load", "okx", "BTC-USD", "--bid", "100.01:50", "--ask", "101.00:50")
    output = desk("scan", "run", "--window-ms", "600000", "--min-edge-bps", "500").output
    session = next(line.split()[1] for line in output.splitlines() if line.startswith("session"))
    assert "EDGE.01" in desk("report", "session", session).output


def test_a_session_that_is_not_there_fails(traded: tuple[Run, str, str]) -> None:
    desk, _, _ = traded
    desk("report", "session", "S19990101.0001", expect=1)


def test_the_edge_report_is_empty_before_any_fill(traded: tuple[Run, str, str]) -> None:
    desk, session, _ = traded
    output = desk("report", "edge", "--session", session).output
    assert "plans        0" in output


def test_the_edge_report_picks_up_a_fill(traded: tuple[Run, str, str]) -> None:
    desk, session, ref = traded
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    output = desk("report", "edge", "--session", session).output
    assert "plans        1" in output
    assert "realised" in output


def test_the_edge_report_shouts_about_leg_risk(traded: tuple[Run, str, str]) -> None:
    desk, session, ref = traded
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    assert "LEG RISK" in desk("report", "edge", "--session", session).output


def test_exporting_to_standard_output_writes_csv(traded: tuple[Run, str, str]) -> None:
    desk, session, _ = traded
    output = desk("report", "export", session).output
    assert output.splitlines()[0].startswith("ref,kind,symbol")
    assert len(output.strip().splitlines()) == 2


def test_exporting_to_a_file_reports_the_count(
    traded: tuple[Run, str, str], tmp_path: Path
) -> None:
    desk, session, _ = traded
    target = tmp_path / "plans.csv"
    result = desk("report", "export", session, "--out", str(target))
    assert "wrote 1 plans" in result.output
    assert target.read_text(encoding="utf-8").count("\n") == 2


def test_exporting_json_is_readable_back(traded: tuple[Run, str, str], tmp_path: Path) -> None:
    desk, session, _ = traded
    target = tmp_path / "session.json"
    desk("report", "export", session, "--format", "json", "--out", str(target))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["session"] == session
    assert payload["actionable"] == 1


def test_an_unknown_format_is_a_usage_error(traded: tuple[Run, str, str]) -> None:
    desk, session, _ = traded
    desk("report", "export", session, "--format", "xml", expect=2)


def test_exporting_the_edge_report_writes_json(
    traded: tuple[Run, str, str], tmp_path: Path
) -> None:
    desk, session, ref = traded
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    target = tmp_path / "edge.json"
    desk("report", "export-edge", "--session", session, "--out", str(target))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["plans"] == 1
    assert payload["lines"][0]["ref"] == ref


def test_the_edge_export_goes_to_standard_output_by_default(
    traded: tuple[Run, str, str],
) -> None:
    desk, session, _ = traded
    payload = json.loads(desk("report", "export-edge", "--session", session).output)
    assert payload["plans"] == 0


def test_an_exported_file_has_no_carriage_returns(
    traded: tuple[Run, str, str], tmp_path: Path
) -> None:
    desk, session, _ = traded
    target = tmp_path / "plans.csv"
    desk("report", "export", session, "--out", str(target))
    assert b"\r" not in target.read_bytes()
