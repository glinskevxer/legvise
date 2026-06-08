"""The context the command tree carries, and the table printer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from legvise.cli.options import DeskGroup, bps_text, echo_rows, open_context
from legvise.clock import FixedClock
from legvise.errors import BadArgument, NotFound
from tests.conftest import SESSION_START


def test_opening_a_context_creates_the_book_and_migrates_it(tmp_path: Path) -> None:
    context = open_context(tmp_path / "book.sqlite3", clock=FixedClock(SESSION_START))
    assert context.db.scalar("SELECT count(*) FROM venue") == 0
    context.db.close()


def test_the_context_reports_the_clock_it_was_given(tmp_path: Path) -> None:
    context = open_context(tmp_path / "book.sqlite3", clock=FixedClock(SESSION_START))
    assert context.now_text() == SESSION_START.isoformat()
    context.db.close()


def test_opening_the_same_book_twice_does_not_migrate_twice(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    first = open_context(target, clock=FixedClock(SESSION_START))
    first.db.close()
    second = open_context(target, clock=FixedClock(SESSION_START))
    assert second.db.scalar("SELECT count(*) FROM applied_migration") > 0
    second.db.close()


def test_quiet_is_carried_on_the_context(tmp_path: Path) -> None:
    context = open_context(tmp_path / "book.sqlite3", quiet=True)
    assert context.quiet
    context.db.close()


def test_a_table_pads_every_column_to_its_widest_cell(capsys: pytest.CaptureFixture[str]) -> None:
    echo_rows([("a", "long value"), ("bbbb", "x")], ("one", "two"))
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("one ")
    assert len(lines) == 4


def test_a_table_with_no_rows_still_prints_a_header(capsys: pytest.CaptureFixture[str]) -> None:
    echo_rows([], ("one", "two"))
    assert capsys.readouterr().out.strip().splitlines()[0] == "one  two"


def test_a_basis_point_figure_is_rounded_for_reading() -> None:
    assert bps_text(Decimal("100.5025125628140703517587940")) == "100.50"


def test_a_basis_point_figure_can_be_asked_for_more_places() -> None:
    assert bps_text(Decimal("0.123456789"), "0.0001") == "0.1235"


def test_a_whole_number_still_prints_its_places() -> None:
    assert bps_text(Decimal("2")) == "2.00"


def test_the_group_turns_a_domain_refusal_into_a_command_failure() -> None:
    @click.group(cls=DeskGroup)
    def cli() -> None:
        """A tree for the test."""

    @cli.command("boom")
    def boom() -> None:
        """Raise a domain error."""
        raise NotFound("venue", "nowhere")

    result = CliRunner().invoke(cli, ["boom"])
    assert result.exit_code == 1
    assert "nowhere" in result.output


def test_the_group_leaves_other_errors_alone() -> None:
    @click.group(cls=DeskGroup)
    def cli() -> None:
        """A tree for the test."""

    @cli.command("boom")
    def boom() -> None:
        """Raise something the package does not own."""
        raise RuntimeError("not ours")

    with pytest.raises(RuntimeError):
        CliRunner().invoke(cli, ["boom"], catch_exceptions=False)


def test_a_read_only_context_opens_an_existing_book(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    open_context(target, clock=FixedClock(SESSION_START)).db.close()
    context = open_context(target, clock=FixedClock(SESSION_START), read_only=True)
    assert context.db.scalar("SELECT count(*) FROM venue") == 0
    context.db.close()


def test_a_read_only_context_refuses_a_write(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    open_context(target, clock=FixedClock(SESSION_START)).db.close()
    context = open_context(target, clock=FixedClock(SESSION_START), read_only=True)
    with pytest.raises(BadArgument):
        context.db.execute(
            "INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '250000', 0, 1)"
        )
    context.db.close()


def test_a_read_only_context_on_a_missing_book_is_a_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFound):
        open_context(tmp_path / "nowhere.sqlite3", read_only=True)
