"""The db command group."""

from __future__ import annotations

from pathlib import Path

from legvise.store.db import Database
from legvise.store.schema import MIGRATIONS
from tests.cli.conftest import Run

CUTOFF = "2025-09-01T00:00:00+00:00"


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


# Pruning. The command took its cutoff and dropped everything older than it,
# newest snapshot of a market included, which quietly retired the market.


def a_desk(run: Run) -> Run:
    """Two venues, one market each, and two snapshots a day apart."""
    for code, name in (("kraken", "Kraken"), ("okx", "OKX")):
        run("venue", "add", code, name, "--staleness-ms", "750", "--depth-bps", "35", "--cap", "1")
        for day in ("01", "02"):
            run(
                "book",
                "load",
                code,
                "BTC-USD",
                "--bid",
                "99:1",
                "--ask",
                "100:1",
                "--observed-at",
                f"2025-08-{day}T09:00:00+00:00",
            )
    return run


def test_pruning_keeps_the_newest_snapshot_of_every_market(run: Run) -> None:
    desk = a_desk(run)
    output = desk("db", "prune", "--before", CUTOFF).output
    assert "snapshots  2" in output
    assert "held       2 markets" in output


def test_a_pruned_market_can_still_be_read(run: Run) -> None:
    desk = a_desk(run)
    desk("db", "prune", "--before", CUTOFF)
    output = desk("book", "show", "kraken", "BTC-USD").output
    assert "observed 2025-08-02T09:00:00+00:00" in output


def test_a_dry_run_removes_nothing(run: Run) -> None:
    desk = a_desk(run)
    output = desk("db", "prune", "--before", CUTOFF, "--dry-run").output
    assert "dry run    nothing was removed" in output
    assert "snapshots  2" in desk("db", "prune", "--before", CUTOFF, "--dry-run").output


def test_a_dry_run_and_the_sweep_report_the_same_count(run: Run) -> None:
    desk = a_desk(run)
    dry = desk("db", "prune", "--before", CUTOFF, "--dry-run").output
    wet = desk("db", "prune", "--before", CUTOFF).output
    assert "snapshots  2" in dry
    assert "snapshots  2" in wet


def test_pruning_says_how_many_rows_it_took(run: Run) -> None:
    desk = a_desk(run)
    assert "removed    2 rows" in desk("db", "prune", "--before", CUTOFF).output


def test_pruning_by_days_counts_back_from_the_clock(run: Run) -> None:
    desk = a_desk(run)
    output = desk("db", "prune", "--keep-days", "1").output
    assert "snapshots  2" in output


def test_pruning_that_keeps_no_days_is_refused(run: Run) -> None:
    a_desk(run)("db", "prune", "--keep-days", "0", expect=1)


def test_pruning_needs_a_cutoff_of_some_kind(run: Run) -> None:
    run("db", "prune", expect=2)


def test_pruning_takes_one_cutoff_and_not_two(run: Run) -> None:
    run("db", "prune", "--before", CUTOFF, "--keep-days", "7", expect=2)


def test_pruning_needs_an_instant_with_an_offset(run: Run) -> None:
    run("db", "prune", "--before", "2025-09-01", expect=1)


def test_pruning_an_empty_book_takes_nothing(run: Run) -> None:
    output = run("db", "prune", "--before", CUTOFF).output
    assert "snapshots  0" in output
    assert "removed    0 rows" in output


def test_pruning_prints_the_cutoff_it_used(run: Run) -> None:
    output = run("db", "prune", "--before", CUTOFF).output
    assert "cutoff     2025-09-01T00:00:00+00:00" in output


# Verifying. A nightly job runs this against the restored file, so the exit
# code carries the answer and the findings go to standard error.


def tamper(book: Path, ref: str) -> None:
    """Break one plan's arithmetic the way a hand edit at two in the morning would."""
    handle = Database.open(book)
    with handle.tx():
        handle.execute("UPDATE plan SET net_bps = ? WHERE ref = ?", ("999", ref))
    handle.close()


def test_a_fresh_book_adds_up(run: Run) -> None:
    assert "the book adds up" in run("db", "verify").output


def test_a_scanned_book_adds_up(scanned: tuple[Run, str]) -> None:
    desk, _ = scanned
    assert "the book adds up" in desk("db", "verify").output


def test_a_tampered_plan_makes_the_command_fail(planned: tuple[Run, str, str], book: Path) -> None:
    desk, _, ref = planned
    tamper(book, ref)
    desk("db", "verify", expect=1)


def test_a_tampered_plan_is_counted_by_kind(planned: tuple[Run, str, str], book: Path) -> None:
    desk, _, ref = planned
    tamper(book, ref)
    assert "arithmetic   1" in desk("db", "verify", expect=1).output


def test_a_tampered_plan_names_the_row_it_found(planned: tuple[Run, str, str], book: Path) -> None:
    desk, _, ref = planned
    tamper(book, ref)
    assert ref in desk("db", "verify", expect=1).output


def test_the_verdict_says_how_many_problems_there_are(
    planned: tuple[Run, str, str], book: Path
) -> None:
    desk, _, ref = planned
    tamper(book, ref)
    assert "the book has 1 problem(s)" in desk("db", "verify", expect=1).output


def test_the_findings_can_be_capped(planned: tuple[Run, str, str], book: Path) -> None:
    desk, _, ref = planned
    tamper(book, ref)
    output = desk("db", "verify", "--limit", "0", expect=1).output
    assert "1 more not shown" in output
