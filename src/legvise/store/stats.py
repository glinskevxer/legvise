"""What is in the book of record, and how big it has got.

The one table that grows without bound is `book_level`, at a few dozen rows per
snapshot per venue per symbol. A desk scanning four markets on three venues once
a second writes about a million rows an hour, and nobody notices until a copy of
the file stops fitting on a laptop.

So the counts are here, in one place, and the CLI prints them. Nothing here
deletes anything; pruning is a decision an operator makes.
"""

from __future__ import annotations

from dataclasses import dataclass

from legvise.rows import as_int, as_optional_text, as_text
from legvise.store.db import Database
from legvise.store.schema import table_names

__all__ = [
    "AppliedStep",
    "TableCount",
    "applied_steps",
    "compact",
    "counts",
    "oldest_snapshot",
    "schema_version",
    "total_rows",
]


@dataclass(frozen=True, slots=True)
class AppliedStep:
    """One migration this database has applied, and when."""

    version: int
    name: str
    digest: str
    applied_at: str


@dataclass(frozen=True, slots=True)
class TableCount:
    """One table and how many rows it holds."""

    table: str
    rows: int


def counts(db: Database) -> tuple[TableCount, ...]:
    """Every table and its row count, biggest first then by name."""
    found = [
        TableCount(table=name, rows=int(db.scalar(f"SELECT count(*) FROM {name}") or 0))
        for name in table_names(db)
    ]
    return tuple(sorted(found, key=lambda row: (-row.rows, row.table)))


def total_rows(db: Database) -> int:
    """Every row in the book of record."""
    return sum(item.rows for item in counts(db))


def schema_version(db: Database) -> int:
    """The highest migration the database has applied."""
    return int(db.scalar("SELECT max(version) FROM applied_migration") or 0)


def oldest_snapshot(db: Database) -> str | None:
    """When the oldest book snapshot on file was observed."""
    row = db.query_one("SELECT min(observed_at) AS at FROM book_snapshot")
    return None if row is None else as_optional_text(row, "at")


def page_count(db: Database) -> int:
    """How many pages the database file uses, free ones included."""
    row = db.query_one("PRAGMA page_count")
    return 0 if row is None else as_int(row, "page_count")


def page_size(db: Database) -> int:
    """The size of one page in bytes."""
    row = db.query_one("PRAGMA page_size")
    return 0 if row is None else as_int(row, "page_size")


def approximate_bytes(db: Database) -> int:
    """Roughly how big the file is, from SQLite's own page arithmetic."""
    return page_count(db) * page_size(db)


def applied_steps(db: Database) -> tuple[AppliedStep, ...]:
    """Every migration this database has applied, in order."""
    rows = db.query(
        "SELECT version, name, digest, applied_at FROM applied_migration ORDER BY version"
    )
    return tuple(
        AppliedStep(
            version=as_int(row, "version"),
            name=as_text(row, "name"),
            digest=as_text(row, "digest"),
            applied_at=as_text(row, "applied_at"),
        )
        for row in rows
    )


def compact(db: Database) -> tuple[int, int]:
    """Rebuild the file and report its size before and after.

    Kept here rather than in the CLI so every statement the package runs lives
    in the store layer, checkable in one place.
    """
    before = approximate_bytes(db)
    db.execute("VACUUM")
    return (before, approximate_bytes(db))
