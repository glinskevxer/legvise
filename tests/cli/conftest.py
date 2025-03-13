"""A runner that drives the real command tree against a temporary book."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from legvise.cli.main import cli

Run = Callable[..., Result]


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    """A path for a book of record that the first command will create."""
    return tmp_path / "book.sqlite3"


@pytest.fixture()
def run(book: Path) -> Run:
    """Invoke the command tree the way the console script does."""
    runner = CliRunner()

    def invoke(*args: str, expect: int = 0) -> Result:
        result = runner.invoke(cli, ["--db", str(book), *args], catch_exceptions=False)
        assert result.exit_code == expect, (
            f"expected exit {expect}, got {result.exit_code}\n{result.output}"
        )
        return result

    return invoke


@pytest.fixture()
def seeded(run: Run) -> Run:
    """A runner with two venues already on file."""
    run(
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
    run(
        "venue",
        "add",
        "okx",
        "OKX",
        "--staleness-ms",
        "400",
        "--depth-bps",
        "20",
        "--cap",
        "500000",
        "--maker-rebate",
    )
    return run
