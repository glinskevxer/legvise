"""The venue command group, driven through the real command tree."""

from __future__ import annotations

from pathlib import Path

from tests.cli.conftest import Run


def test_the_root_prints_its_version() -> None:
    from click.testing import CliRunner

    from legvise import __version__
    from legvise.cli.main import cli

    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_the_first_command_creates_the_book(run: Run, book: Path) -> None:
    run("venue", "list")
    assert book.exists()


def test_adding_a_venue_reports_it(run: Run) -> None:
    result = run(
        "venue",
        "add",
        "kraken",
        "Kraken",
        "--staleness-ms",
        "750",
        "--depth-bps",
        "35",
        "--cap",
        "250000",
    )
    assert "added venue kraken" in result.output


def test_a_listing_carries_a_header_and_a_row_for_each_venue(seeded: Run) -> None:
    output = seeded("venue", "list").output
    assert "code" in output
    assert "kraken" in output
    assert "okx" in output


def test_a_listing_lines_the_columns_up(seeded: Run) -> None:
    lines = seeded("venue", "list").output.strip().splitlines()
    assert set(lines[1]) <= {"-", " "}
    assert len(lines) == 4


def test_showing_a_venue_prints_every_field(seeded: Run) -> None:
    output = seeded("venue", "show", "okx").output
    assert "maker_rebate   yes" in output
    assert "staleness_ms   400" in output
    assert "state          on" in output


def test_disabling_a_venue_takes_it_out_of_the_active_listing(seeded: Run) -> None:
    seeded("venue", "disable", "okx")
    output = seeded("venue", "list", "--active-only").output
    assert "kraken" in output
    assert "okx" not in output


def test_enabling_a_venue_puts_it_back(seeded: Run) -> None:
    seeded("venue", "disable", "okx")
    seeded("venue", "enable", "okx")
    assert "okx" in seeded("venue", "list", "--active-only").output


def test_a_venue_that_is_not_there_fails_rather_than_printing_nothing(seeded: Run) -> None:
    result = seeded("venue", "show", "nowhere", expect=1)
    assert "nowhere" in result.output


def test_a_bad_depth_limit_is_refused_before_anything_is_written(run: Run) -> None:
    run(
        "venue",
        "add",
        "kraken",
        "Kraken",
        "--staleness-ms",
        "750",
        "--depth-bps",
        "0",
        "--cap",
        "250000",
        expect=1,
    )
    assert "kraken" not in run("venue", "list").output


def test_quiet_prints_nothing_on_a_write(run: Run, book: Path) -> None:
    from click.testing import CliRunner

    from legvise.cli.main import cli

    result = CliRunner().invoke(
        cli,
        [
            "--db",
            str(book),
            "--quiet",
            "venue",
            "add",
            "kraken",
            "Kraken",
            "--staleness-ms",
            "750",
            "--depth-bps",
            "35",
            "--cap",
            "250000",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output == ""


def test_a_read_only_run_can_still_list(seeded: Run, book: Path) -> None:
    from click.testing import CliRunner

    from legvise.cli.main import cli

    result = CliRunner().invoke(
        cli, ["--db", str(book), "--read-only", "venue", "list"], catch_exceptions=False
    )
    assert result.exit_code == 0
    assert "kraken" in result.output


def test_a_read_only_run_cannot_add_a_venue(seeded: Run, book: Path) -> None:
    from click.testing import CliRunner

    from legvise.cli.main import cli

    result = CliRunner().invoke(
        cli,
        [
            "--db",
            str(book),
            "--read-only",
            "venue",
            "add",
            "bitstamp",
            "Bitstamp",
            "--staleness-ms",
            "750",
            "--depth-bps",
            "35",
            "--cap",
            "250000",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 1
