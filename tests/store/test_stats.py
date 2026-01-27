"""What is in the book of record, and how big it has got."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.model.book import Book
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.schema import MIGRATIONS
from legvise.store.stats import (
    applied_steps,
    approximate_bytes,
    compact,
    counts,
    oldest_snapshot,
    page_count,
    page_size,
    schema_version,
    total_rows,
)
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

AT = dt.datetime(2026, 2, 10, 9, 0, tzinfo=dt.UTC)


@pytest.fixture()
def stocked(db: Database) -> Database:
    venues = VenueStore(db)
    venues.add(make_venue("kraken"))
    books = BookStore(db)
    for minute in range(3):
        books.add(
            Book.build(
                "kraken",
                "BTC-USD",
                observed_at=AT + dt.timedelta(minutes=minute),
                bids=(("99", "1"), ("98", "2")),
                asks=(("101", "1"), ("102", "2")),
            )
        )
    return db


def test_a_fresh_book_is_at_the_current_schema(db: Database) -> None:
    assert schema_version(db) == len(MIGRATIONS)


def test_a_fresh_book_holds_only_the_migration_ledger(db: Database) -> None:
    assert total_rows(db) == len(MIGRATIONS)


def test_every_table_in_the_schema_is_counted(db: Database) -> None:
    names = {item.table for item in counts(db)}
    assert "venue" in names
    assert "book_level" in names


def test_the_biggest_table_comes_first(stocked: Database) -> None:
    listed = counts(stocked)
    assert listed[0].table == "book_level"
    assert listed[0].rows == 12


def test_tables_with_the_same_count_sort_by_name(db: Database) -> None:
    empty = [item.table for item in counts(db) if item.rows == 0]
    assert empty == sorted(empty)


def test_the_rows_add_up_across_the_tables(stocked: Database) -> None:
    assert total_rows(stocked) == sum(item.rows for item in counts(stocked))


def test_an_empty_book_has_no_oldest_snapshot(db: Database) -> None:
    assert oldest_snapshot(db) is None


def test_the_oldest_snapshot_is_the_earliest_observation(stocked: Database) -> None:
    assert oldest_snapshot(stocked) == AT.isoformat()


def test_the_page_arithmetic_gives_a_size(stocked: Database) -> None:
    assert page_size(stocked) > 0
    assert page_count(stocked) > 0
    assert approximate_bytes(stocked) == page_count(stocked) * page_size(stocked)


def test_writing_more_snapshots_grows_the_level_count(stocked: Database) -> None:
    before = next(item.rows for item in counts(stocked) if item.table == "book_level")
    BookStore(stocked).add(
        Book.build(
            "kraken",
            "BTC-USD",
            observed_at=AT + dt.timedelta(hours=1),
            bids=(("99", "1"),),
            asks=(("101", "1"),),
        )
    )
    after = next(item.rows for item in counts(stocked) if item.table == "book_level")
    assert after == before + 2


def test_the_applied_steps_are_read_back_in_order(db: Database) -> None:
    steps = applied_steps(db)
    assert [step.version for step in steps] == [item.version for item in MIGRATIONS]


def test_every_applied_step_carries_its_digest(db: Database) -> None:
    for step in applied_steps(db):
        assert len(step.digest) == 16
        assert step.applied_at


def test_compacting_reports_the_size_either_side(stocked: Database) -> None:
    before, after = compact(stocked)
    assert before > 0
    assert after > 0


def test_compacting_leaves_the_rows_alone(stocked: Database) -> None:
    before = total_rows(stocked)
    compact(stocked)
    assert total_rows(stocked) == before
