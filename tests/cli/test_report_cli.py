"""The report command group."""

from __future__ import annotations

import json
from pathlib import Path

from tests.cli.conftest import Run, session_of, wire


def test_a_session_report_prints_the_counts(planned: tuple[Run, str, str]) -> None:
    desk, session, _ = planned
    output = desk("report", "session", session).output
    assert "plans       1" in output
    assert "actionable  1" in output


def test_a_session_report_prints_the_best_edge(planned: tuple[Run, str, str]) -> None:
    desk, session, _ = planned
    assert "best " in desk("report", "session", session).output


def test_a_session_report_lists_the_clauses_that_fired(run: Run) -> None:
    desk = wire(run)
    desk("book", "load", "kraken", "BTC-USD", "--bid", "99.00:50", "--ask", "100.00:50")
    desk("book", "load", "okx", "BTC-USD", "--bid", "100.01:50", "--ask", "101.00:50")
    output = desk("scan", "run", "--window-ms", "600000", "--min-edge-bps", "500").output
    session = session_of(output)
    assert "EDGE.01" in desk("report", "session", session).output


def test_a_session_that_is_not_there_fails(planned: tuple[Run, str, str]) -> None:
    desk, _, _ = planned
    desk("report", "session", "S19990101.0001", expect=1)


def test_the_edge_report_is_empty_before_any_fill(planned: tuple[Run, str, str]) -> None:
    desk, session, _ = planned
    output = desk("report", "edge", "--session", session).output
    assert "plans        0" in output


def test_the_edge_report_picks_up_a_fill(planned: tuple[Run, str, str]) -> None:
    desk, session, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    output = desk("report", "edge", "--session", session).output
    assert "plans        1" in output
    assert "realised" in output


def test_the_edge_report_shouts_about_leg_risk(planned: tuple[Run, str, str]) -> None:
    desk, session, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    assert "LEG RISK" in desk("report", "edge", "--session", session).output


def test_exporting_to_standard_output_writes_csv(planned: tuple[Run, str, str]) -> None:
    desk, session, _ = planned
    output = desk("report", "export", session).output
    assert output.splitlines()[0].startswith("ref,kind,symbol")
    assert len(output.strip().splitlines()) == 2


def test_exporting_to_a_file_reports_the_count(
    planned: tuple[Run, str, str], tmp_path: Path
) -> None:
    desk, session, _ = planned
    target = tmp_path / "plans.csv"
    result = desk("report", "export", session, "--out", str(target))
    assert "wrote 1 plans" in result.output
    assert target.read_text(encoding="utf-8").count("\n") == 2


def test_exporting_json_is_readable_back(planned: tuple[Run, str, str], tmp_path: Path) -> None:
    desk, session, _ = planned
    target = tmp_path / "session.json"
    desk("report", "export", session, "--format", "json", "--out", str(target))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["session"] == session
    assert payload["actionable"] == 1


def test_an_unknown_format_is_a_usage_error(planned: tuple[Run, str, str]) -> None:
    desk, session, _ = planned
    desk("report", "export", session, "--format", "xml", expect=2)


def test_exporting_the_edge_report_writes_json(
    planned: tuple[Run, str, str], tmp_path: Path
) -> None:
    desk, session, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    target = tmp_path / "edge.json"
    desk("report", "export-edge", "--session", session, "--out", str(target))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["plans"] == 1
    assert payload["lines"][0]["ref"] == ref


def test_the_edge_export_goes_to_standard_output_by_default(
    planned: tuple[Run, str, str],
) -> None:
    desk, session, _ = planned
    payload = json.loads(desk("report", "export-edge", "--session", session).output)
    assert payload["plans"] == 0


def test_an_exported_file_has_no_carriage_returns(
    planned: tuple[Run, str, str], tmp_path: Path
) -> None:
    desk, session, _ = planned
    target = tmp_path / "plans.csv"
    desk("report", "export", session, "--out", str(target))
    assert b"\r" not in target.read_bytes()


def test_the_inventory_report_lists_every_holding(planned: tuple[Run, str, str]) -> None:
    desk, _, _ = planned
    lines = desk("report", "inventory").output.strip().splitlines()
    assert len(lines) >= 6


def test_the_inventory_report_says_what_would_square_an_asset(
    planned: tuple[Run, str, str],
) -> None:
    desk, _, _ = planned
    desk("inventory", "set-balance", "kraken", "BTC", "80")
    output = desk("report", "inventory").output
    assert "BTC: transfer" in output


def test_a_desk_on_target_needs_nothing_moved(planned: tuple[Run, str, str]) -> None:
    desk, _, _ = planned
    desk("inventory", "set-balance", "kraken", "BTC", "25")
    desk("inventory", "set-balance", "okx", "BTC", "25")
    output = desk("report", "inventory", "--asset", "BTC").output
    assert "BTC: transfer" not in output


def test_the_inventory_report_can_be_narrowed_to_one_asset(
    planned: tuple[Run, str, str],
) -> None:
    desk, _, _ = planned
    output = desk("report", "inventory", "--asset", "BTC").output
    assert "USD" not in output


def test_the_inventory_report_names_the_state_of_each_holding(
    planned: tuple[Run, str, str],
) -> None:
    desk, _, _ = planned
    assert "in band" in desk("report", "inventory").output


def test_a_wired_desk_reports_that_it_can_scan(desk: Run) -> None:
    assert "the desk is ready to scan" in desk("report", "desk").output


def test_the_desk_report_counts_the_shared_markets(desk: Run) -> None:
    assert "shared markets  1" in desk("report", "desk").output


def test_the_desk_report_counts_the_books_on_file(scanned: tuple[Run, str]) -> None:
    run, _ = scanned
    line = next(
        row for row in run("report", "desk").output.splitlines() if row.startswith("kraken")
    )
    assert line.split()[3] == "1"


def test_the_desk_report_names_the_last_session(scanned: tuple[Run, str]) -> None:
    run, session = scanned
    assert session in run("report", "desk").output


def test_a_desk_missing_a_volume_is_not_ready(desk: Run) -> None:
    desk("fee", "clear-volume", "okx")
    result = desk("report", "desk", expect=1)
    assert "no trailing volume" in result.output
    assert "not ready" in result.output


def test_a_desk_with_no_venues_is_not_ready(run: Run) -> None:
    result = run("report", "desk", expect=1)
    assert "not ready to scan" in result.output


def test_the_leg_export_writes_one_row_per_order(planned: tuple[Run, str, str]) -> None:
    desk, session, _ = planned
    lines = desk("report", "export-legs", session).output.strip().splitlines()
    assert lines[0].startswith("plan_ref,leg_index")
    assert len(lines) == 3


def test_the_leg_export_to_a_file_counts_the_legs(
    planned: tuple[Run, str, str], tmp_path: Path
) -> None:
    desk, session, _ = planned
    target = tmp_path / "legs.csv"
    assert "wrote 2 legs" in desk("report", "export-legs", session, "--out", str(target)).output


def test_the_leg_export_can_skip_the_refused_plans(planned: tuple[Run, str, str]) -> None:
    desk, session, _ = planned
    lines = desk("report", "export-legs", session, "--actionable").output.strip().splitlines()
    assert len(lines) == 3
