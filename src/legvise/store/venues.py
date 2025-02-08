"""Reading and writing venue records.

Every repository in the package looks like this one: explicit column lists, no
`SELECT *`, one place that turns a row into a record, and no caching. The column
list matters more than it looks -- a `SELECT *` here means adding a column to
the table silently changes what `_read` is handed.
"""

from __future__ import annotations

import sqlite3

from legvise.errors import NotFound
from legvise.model.venue import Venue
from legvise.rows import as_bool, as_decimal, as_int, as_text, flag
from legvise.store.db import Database

__all__ = ["VenueStore"]

_COLUMNS = (
    "code, display_name, staleness_budget_ms, depth_limit_bps,"
    " notional_cap, pays_maker_rebate, active"
)


def _read(row: sqlite3.Row) -> Venue:
    return Venue(
        code=as_text(row, "code"),
        display_name=as_text(row, "display_name"),
        staleness_budget_ms=as_int(row, "staleness_budget_ms"),
        depth_limit_bps=as_decimal(row, "depth_limit_bps"),
        notional_cap=as_decimal(row, "notional_cap"),
        pays_maker_rebate=as_bool(row, "pays_maker_rebate"),
        active=as_bool(row, "active"),
    )


class VenueStore:
    """The venue table, and nothing else."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, venue: Venue) -> Venue:
        """Insert a venue. A code that is already there is a conflict."""
        self._db.execute(
            f"INSERT INTO venue ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                venue.code,
                venue.display_name,
                venue.staleness_budget_ms,
                venue.depth_limit_bps,
                venue.notional_cap,
                flag(venue.pays_maker_rebate),
                flag(venue.active),
            ),
        )
        return venue

    def get(self, code: str) -> Venue:
        """One venue by code, or a `NotFound` naming it."""
        row = self._db.query_one(f"SELECT {_COLUMNS} FROM venue WHERE code = ?", (code,))
        if row is None:
            raise NotFound("venue", code)
        return _read(row)

    def find(self, code: str) -> Venue | None:
        """One venue by code, or nothing."""
        row = self._db.query_one(f"SELECT {_COLUMNS} FROM venue WHERE code = ?", (code,))
        return None if row is None else _read(row)

    def list(self, *, active_only: bool = False) -> tuple[Venue, ...]:
        """Every venue, in code order."""
        where = " WHERE active = 1" if active_only else ""
        rows = self._db.query(f"SELECT {_COLUMNS} FROM venue{where} ORDER BY code")
        return tuple(_read(r) for r in rows)

    def save(self, venue: Venue) -> Venue:
        """Overwrite an existing venue. A code that is not there is a `NotFound`."""
        cursor = self._db.execute(
            "UPDATE venue SET display_name = ?, staleness_budget_ms = ?,"
            " depth_limit_bps = ?, notional_cap = ?, pays_maker_rebate = ?, active = ?"
            " WHERE code = ?",
            (
                venue.display_name,
                venue.staleness_budget_ms,
                venue.depth_limit_bps,
                venue.notional_cap,
                flag(venue.pays_maker_rebate),
                flag(venue.active),
                venue.code,
            ),
        )
        if cursor.rowcount == 0:
            raise NotFound("venue", venue.code)
        return venue

    def remove(self, code: str) -> None:
        """Delete a venue and everything hanging off it."""
        cursor = self._db.execute("DELETE FROM venue WHERE code = ?", (code,))
        if cursor.rowcount == 0:
            raise NotFound("venue", code)

    def codes(self) -> tuple[str, ...]:
        """Every venue code, in order, without building the records."""
        rows = self._db.query("SELECT code FROM venue ORDER BY code")
        return tuple(as_text(r, "code") for r in rows)
