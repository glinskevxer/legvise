"""Every foreign key has an index on the child side.

SQLite indexes the parent side of a foreign key for free, because the parent
side is a primary key or a unique constraint. It indexes nothing on the child
side. So `DELETE FROM venue WHERE code = 'kraken'` with `ON DELETE CASCADE`
walks every row of every child table looking for matches, and on a book table
with a few million snapshots that is the difference between a command that
returns and one that appears to hang.

The check builds the real schema in memory and asks SQLite what it made, rather
than reading the DDL. That way a `CREATE INDEX` that was written and never run
-- because it sits in a migration that was edited after shipping, say -- shows
up as missing rather than as present.
"""

from __future__ import annotations

import sys

from legvise.store.db import Database
from legvise.store.schema import install, table_names
from legvise.tools.walk import report

__all__ = [
    "ForeignKey",
    "foreign_keys",
    "indexed_columns",
    "main",
    "problems",
    "problems_for",
]

INSTALLED_AT = "2000-01-01T00:00:00+00:00"


class ForeignKey:
    """One foreign key, from the child table's point of view."""

    __slots__ = ("child_columns", "child_table", "parent_table")

    def __init__(self, child_table: str, parent_table: str, child_columns: tuple[str, ...]) -> None:
        self.child_table = child_table
        self.parent_table = parent_table
        self.child_columns = child_columns

    def __repr__(self) -> str:
        columns = ", ".join(self.child_columns)
        return f"{self.child_table}({columns}) -> {self.parent_table}"


def _fresh() -> Database:
    handle = Database.in_memory()
    install(handle, applied_at=INSTALLED_AT)
    return handle


def foreign_keys(db: Database) -> tuple[ForeignKey, ...]:
    """Every foreign key in the schema, grouped by the key it belongs to."""
    found: list[ForeignKey] = []
    for table in table_names(db):
        rows = db.query(f"PRAGMA foreign_key_list({table})")
        grouped: dict[int, list[str]] = {}
        parents: dict[int, str] = {}
        for row in rows:
            key = int(row["id"])
            grouped.setdefault(key, []).append(str(row["from"]))
            parents[key] = str(row["table"])
        for key, columns in sorted(grouped.items()):
            found.append(ForeignKey(table, parents[key], tuple(columns)))
    return tuple(found)


def indexed_columns(db: Database, table: str) -> tuple[tuple[str, ...], ...]:
    """Every column prefix an index or primary key on a table can serve."""
    prefixes: list[tuple[str, ...]] = []
    info = db.query(f"PRAGMA table_info({table})")
    primary = [str(row["name"]) for row in sorted(info, key=lambda r: int(r["pk"])) if row["pk"]]
    if primary:
        prefixes.append(tuple(primary))
    for row in db.query(f"PRAGMA index_list({table})"):
        columns = [
            str(entry["name"])
            for entry in db.query(f"PRAGMA index_info({row['name']})")
            if entry["name"] is not None
        ]
        if columns:
            prefixes.append(tuple(columns))
    return tuple(prefixes)


def _is_served(columns: tuple[str, ...], prefixes: tuple[tuple[str, ...], ...]) -> bool:
    return any(prefix[: len(columns)] == columns for prefix in prefixes)


def problems_for(db: Database) -> list[str]:
    """Every foreign key in one database whose child columns nothing indexes.

    Split out from `problems` so a test can point it at a database with a
    deliberately unindexed key. A check nobody has watched fail is a check that
    might only ever return an empty list.
    """
    found: list[str] = []
    for key in foreign_keys(db):
        prefixes = indexed_columns(db, key.child_table)
        if not _is_served(key.child_columns, prefixes):
            found.append(f"{key!r} has no index on the child side")
    return found


def problems() -> list[str]:
    """Every foreign key in the real schema whose child side is unindexed."""
    db = _fresh()
    try:
        return problems_for(db)
    finally:
        db.close()


def main() -> int:
    """Run the check and report."""
    return report("check_indexes", problems())


if __name__ == "__main__":
    sys.exit(main())
