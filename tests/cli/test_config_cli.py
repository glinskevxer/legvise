"""The config command group, and the file the scan reads its numbers from."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from legvise.cli.main import cli
from legvise.settings import DEFAULTS
from tests.cli.conftest import Run, load_crossing, session_of, wire

SETTINGS = '[scan]\nmin_edge_bps = "9"\nwindow_ms = 600000\n'


def a_file(tmp_path: Path, body: str = SETTINGS) -> Path:
    """A settings file beside the book."""
    path = tmp_path / "legvise.toml"
    path.write_text(body, encoding="utf-8")
    return path


def row_for(output: str, name: str) -> list[str]:
    """One row of a settings table, split into its cells."""
    line = next(row for row in output.splitlines() if row.startswith(name + " "))
    return line.split()


def with_config(book: Path, config: Path) -> Run:
    """A runner that passes `--config` on every invocation."""
    runner = CliRunner()

    def invoke(*args: str, expect: int = 0) -> object:
        result = runner.invoke(
            cli,
            ["--db", str(book), "--config", str(config), *args],
            catch_exceptions=False,
        )
        assert result.exit_code == expect, (
            f"expected exit {expect}, got {result.exit_code}\n{result.output}"
        )
        return result

    return invoke  # type: ignore[return-value]


def test_the_settings_read_as_defaults_with_no_file(run: Run) -> None:
    output = run("config", "show").output
    assert row_for(output, "min_edge_bps") == ["min_edge_bps", "2", "default"]


def test_the_source_column_says_no_file_was_loaded(run: Run) -> None:
    assert "file        none loaded" in run("config", "show").output


def test_every_setting_the_desk_has_is_listed(run: Run) -> None:
    lines = run("config", "show").output.strip().splitlines()
    assert len(lines) == len(DEFAULTS.names()) + 3


def test_a_loaded_file_decides_the_numbers_it_names(book: Path, tmp_path: Path) -> None:
    desk = with_config(book, a_file(tmp_path))
    output = desk("config", "show").output
    assert row_for(output, "min_edge_bps") == ["min_edge_bps", "9", "file"]
    assert row_for(output, "window_ms") == ["window_ms", "600000", "file"]


def test_a_setting_the_file_leaves_alone_stays_a_default(book: Path, tmp_path: Path) -> None:
    desk = with_config(book, a_file(tmp_path))
    assert row_for(desk("config", "show").output, "size") == ["size", "1", "default"]


def test_only_the_settings_somebody_set_can_be_listed(book: Path, tmp_path: Path) -> None:
    desk = with_config(book, a_file(tmp_path))
    lines = desk("config", "show", "--changed-only").output.strip().splitlines()
    assert len(lines) == 5


def test_the_file_that_was_loaded_is_named(book: Path, tmp_path: Path) -> None:
    config = a_file(tmp_path)
    assert str(config) in with_config(book, config)("config", "show").output


def test_the_shipped_defaults_can_be_printed_on_their_own(book: Path, tmp_path: Path) -> None:
    desk = with_config(book, a_file(tmp_path))
    output = desk("config", "defaults").output
    assert row_for(output, "min_edge_bps") == ["min_edge_bps", "2"]
    assert "section     [scan]" in output


def test_a_file_can_be_read_without_running_anything(run: Run, tmp_path: Path) -> None:
    output = run("config", "check", str(a_file(tmp_path))).output
    assert row_for(output, "min_edge_bps") == ["min_edge_bps", "9"]
    assert f"sets 2 of {len(DEFAULTS.names())} settings" in output


def test_a_file_with_a_typo_in_a_key_is_refused(run: Run, tmp_path: Path) -> None:
    path = tmp_path / "typo.toml"
    path.write_text('[scan]\nmin_edge_bp = "9"\n', encoding="utf-8")
    run("config", "check", str(path), expect=1)


def test_a_file_that_is_not_there_is_refused(run: Run, tmp_path: Path) -> None:
    run("config", "check", str(tmp_path / "nowhere.toml"), expect=1)


def test_a_bad_file_stops_the_command_before_it_runs(book: Path, tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text('[scan]\nwindow_ms = "400"\n', encoding="utf-8")
    with_config(book, path)("config", "show", expect=1)


def test_the_scan_takes_its_numbers_from_the_file(book: Path, tmp_path: Path) -> None:
    desk = with_config(book, a_file(tmp_path))
    wire(desk)
    load_crossing(desk)
    session = session_of(desk("scan", "run", "--size", "2").output)
    line = next(row for row in desk("scan", "sessions").output.splitlines() if session in row)
    assert line.split()[2] == "9"


def test_a_flag_beats_the_file_for_that_run(book: Path, tmp_path: Path) -> None:
    desk = with_config(book, a_file(tmp_path))
    wire(desk)
    load_crossing(desk)
    first = session_of(desk("scan", "run", "--size", "2", "--min-edge-bps", "1").output)
    second = session_of(desk("scan", "run", "--size", "2", "--counter", "1").output)
    rows = desk("scan", "sessions").output.splitlines()
    flagged = next(row for row in rows if first in row)
    filed = next(row for row in rows if second in row)
    assert flagged.split()[2] == "1"
    assert filed.split()[2] == "9"


def test_the_window_from_the_file_lets_the_pair_price(book: Path, tmp_path: Path) -> None:
    desk = with_config(book, a_file(tmp_path))
    wire(desk)
    load_crossing(desk)
    assert "priced      1" in desk("scan", "run", "--size", "2").output
