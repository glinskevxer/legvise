"""The db command group."""

from __future__ import annotations

from legvise.store.schema import MIGRATIONS
from tests.cli.conftest import Run


def test_the_status_reports_the_current_schema(run: Run) -> None:
    output = run("db", "status").output
    assert f"schema      {len(MIGRATIONS)} of {len(MIGRATIONS)}" in output


def test_the_status_reports_a_size_in_bytes(run: Run) -> None:
    line = next(row for row in run("db", "status").output.splitlines() if row.startswith("size"))
    assert int(line.split()[1]) > 0


def test_a_fresh_book_has_no_snapshot_on_file(run: Run) -> None:
    assert "oldest book none on file" in run("db", "status").output


def test_the_status_reports_a_snapshot_once_one_is_loaded(seeded: Run) -> None:
    seeded(
        "book",
        "load",
        "kraken",
        "BTC-USD",
        "--bid",
        "99:1",
        "--ask",
        "100:1",
        "--observed-at",
        "2026-02-10T09:00:00+00:00",
    )
    assert "2026-02-10T09:00:00+00:00" in seeded("db", "status").output


def test_the_tables_listing_names_every_table(run: Run) -> None:
    output = run("db", "tables").output
    for name in ("venue", "instrument", "plan", "fill", "book_level"):
        assert name in output


def test_the_tables_listing_counts_the_rows(seeded: Run) -> None:
    line = next(
        row for row in seeded("db", "tables").output.splitlines() if row.startswith("venue ")
    )
    assert line.split()[-1] == "2"


def test_migrating_an_up_to_date_book_does_nothing(run: Run) -> None:
    assert "already at the current schema" in run("db", "migrate").output


def test_the_applied_listing_has_a_row_per_migration(run: Run) -> None:
    lines = run("db", "applied").output.strip().splitlines()
    assert len(lines) == len(MIGRATIONS) + 2


def test_the_applied_listing_carries_the_digest(run: Run) -> None:
    # The name column has spaces in it, so the digest is the last field but one.
    row = run("db", "applied").output.strip().splitlines()[2]
    assert len(row.split()[-2]) == 16


def test_the_applied_listing_names_each_migration(run: Run) -> None:
    output = run("db", "applied").output
    for step in MIGRATIONS:
        assert step.name in output


def test_a_vacuum_reports_the_size_either_side(seeded: Run) -> None:
    output = seeded("db", "vacuum").output
    assert "bytes before" in output


def test_a_vacuum_leaves_the_data_alone(seeded: Run) -> None:
    seeded("db", "vacuum")
    assert "kraken" in seeded("venue", "list").output
