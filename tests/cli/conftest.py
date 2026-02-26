"""Fixtures that drive the real command tree against a temporary book.

The desk builders live here rather than in whichever test module wrote them
first. Five modules used to import `wire` out of `test_scan_cli`, which made
that module a library nobody had decided to make one, and meant renaming a test
in it broke four others.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from legvise.cli.main import cli

Run = Callable[..., Result]

VENUES = (("kraken", "Kraken"), ("okx", "OKX"))


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
    """A runner with two venues already on file and nothing else."""
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


def wire(run: Run) -> Run:
    """Two venues, one market each, fees, balances and bands.

    Everything a scan needs and nothing it does not. Deliberately a function
    rather than a fixture so a test can call it on a runner it built itself.
    """
    for code, name in VENUES:
        run(
            "venue",
            "add",
            code,
            name,
            "--staleness-ms",
            "600000",
            "--depth-bps",
            "500",
            "--cap",
            "10000000",
        )
        run(
            "instrument",
            "add",
            code,
            "BTC-USD",
            "--tick",
            "0.01",
            "--lot",
            "0.0001",
            "--min-notional",
            "10",
            "--max-notional",
            "10000000",
        )
        run("fee", "set-ladder", code, "0:0:5")
        run("fee", "record-volume", code, "0")
        run("inventory", "set-balance", code, "BTC", "50")
        run("inventory", "set-balance", code, "USD", "5000000")
        run(
            "inventory",
            "set-band",
            code,
            "BTC",
            "--floor",
            "0",
            "--target",
            "25",
            "--ceiling",
            "1000",
        )
        run(
            "inventory",
            "set-band",
            code,
            "USD",
            "--floor",
            "0",
            "--target",
            "1000000",
            "--ceiling",
            "50000000",
        )
    return run


def load_crossing(run: Run) -> Run:
    """Books on both venues that cross one way and not the other."""
    run("book", "load", "kraken", "BTC-USD", "--bid", "99.00:50", "--ask", "100.00:50")
    run("book", "load", "okx", "BTC-USD", "--bid", "101.00:50", "--ask", "102.00:50")
    return run


def session_of(output: str) -> str:
    """The session reference a scan or loop run printed."""
    return next(line.split()[1] for line in output.splitlines() if line.startswith("session"))


@pytest.fixture()
def desk(run: Run) -> Run:
    """A wired desk with no books on it yet."""
    return wire(run)


@pytest.fixture()
def scanned(desk: Run) -> tuple[Run, str]:
    """A desk that has scanned one crossing pair, and the session it wrote."""
    load_crossing(desk)
    output = desk("scan", "run", "--window-ms", "600000", "--size", "2").output
    return (desk, session_of(output))


@pytest.fixture()
def planned(scanned: tuple[Run, str]) -> tuple[Run, str, str]:
    """The same desk, plus the reference of the plan the scan produced."""
    desk, session = scanned
    ref = desk("plan", "best", session).output.split()[0]
    return (desk, session, ref)
