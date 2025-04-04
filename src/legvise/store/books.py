"""Storing book snapshots, and reading back the one that was true at a time.

The desk keeps snapshots for two reasons that pull in different directions.
Live scanning wants the newest book per venue and symbol, which is a tiny query.
Attribution wants the book that was on file *when a plan was written*, months
later, which is a different query over a much bigger table.

Both are here. What is not here is any attempt to reconstruct a book from deltas
-- the feed handler owns that, and this package only ever sees whole snapshots.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

from legvise.clock import parse_instant, to_text
from legvise.errors import NotFound
from legvise.ids import Symbol, parse_symbol, symbol_text
from legvise.model.book import Book, Level, Side
from legvise.rows import as_decimal, as_int, as_symbol, as_text
from legvise.store.db import Database

__all__ = ["BookStore"]

_SNAPSHOT_COLUMNS = "id, venue_code, symbol, observed_at, sequence"
_LEVEL_COLUMNS = "snapshot_id, side, rank, price, size"


def _levels_by_side(rows: list[sqlite3.Row]) -> dict[Side, list[Level]]:
    grouped: dict[Side, list[Level]] = defaultdict(list)
    for row in rows:
        side = Side(as_text(row, "side"))
        grouped[side].append(Level(price=as_decimal(row, "price"), size=as_decimal(row, "size")))
    return grouped


class BookStore:
    """The snapshot and level tables."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, book: Book) -> int:
        """Write a snapshot and its levels, returning the row id."""
        with self._db.tx():
            cursor = self._db.execute(
                "INSERT INTO book_snapshot (venue_code, symbol, observed_at, sequence)"
                " VALUES (?, ?, ?, ?)",
                (
                    book.venue,
                    symbol_text(book.symbol),
                    to_text(book.observed_at),
                    book.sequence,
                ),
            )
            snapshot_id = int(cursor.lastrowid or 0)
            for side in (Side.BID, Side.ASK):
                for rank, level in enumerate(book.side(side)):
                    self._db.execute(
                        f"INSERT INTO book_level ({_LEVEL_COLUMNS}) VALUES (?, ?, ?, ?, ?)",
                        (snapshot_id, side.value, rank, level.price, level.size),
                    )
        return snapshot_id

    def get(self, snapshot_id: int) -> Book:
        """One snapshot by row id."""
        row = self._db.query_one(
            f"SELECT {_SNAPSHOT_COLUMNS} FROM book_snapshot WHERE id = ?", (snapshot_id,)
        )
        if row is None:
            raise NotFound("book snapshot", str(snapshot_id))
        return self._build(row)

    def latest(self, venue: str, symbol: str | Symbol) -> Book | None:
        """The newest snapshot for a venue and symbol, or nothing."""
        key = symbol if isinstance(symbol, Symbol) else parse_symbol(symbol)
        row = self._db.query_one(
            f"SELECT {_SNAPSHOT_COLUMNS} FROM book_snapshot"
            " WHERE venue_code = ? AND symbol = ?"
            " ORDER BY observed_at DESC, id DESC LIMIT 1",
            (venue, symbol_text(key)),
        )
        return None if row is None else self._build(row)

    def require_latest(self, venue: str, symbol: str | Symbol) -> Book:
        """The newest snapshot, refusing to carry on without one."""
        found = self.latest(venue, symbol)
        if found is None:
            raise NotFound("book snapshot", f"{venue}:{symbol}")
        return found

    def as_of(self, venue: str, symbol: str | Symbol, at: dt.datetime) -> Book | None:
        """The newest snapshot that was already on file at `at`."""
        key = symbol if isinstance(symbol, Symbol) else parse_symbol(symbol)
        row = self._db.query_one(
            f"SELECT {_SNAPSHOT_COLUMNS} FROM book_snapshot"
            " WHERE venue_code = ? AND symbol = ? AND observed_at <= ?"
            " ORDER BY observed_at DESC, id DESC LIMIT 1",
            (venue, symbol_text(key), to_text(at)),
        )
        return None if row is None else self._build(row)

    def latest_across(self, symbol: str | Symbol) -> tuple[Book, ...]:
        """The newest snapshot on every venue that has one for this symbol."""
        key = symbol if isinstance(symbol, Symbol) else parse_symbol(symbol)
        rows = self._db.query(
            "SELECT DISTINCT venue_code FROM book_snapshot WHERE symbol = ? ORDER BY venue_code",
            (symbol_text(key),),
        )
        found = (self.latest(as_text(r, "venue_code"), key) for r in rows)
        return tuple(book for book in found if book is not None)

    def prune_before(self, at: dt.datetime) -> int:
        """Drop snapshots older than `at`, returning how many went."""
        with self._db.tx():
            cursor = self._db.execute(
                "DELETE FROM book_snapshot WHERE observed_at < ?", (to_text(at),)
            )
            return int(cursor.rowcount)

    def count(self) -> int:
        """How many snapshots are on file."""
        return int(self._db.scalar("SELECT count(*) FROM book_snapshot") or 0)

    def _build(self, row: sqlite3.Row) -> Book:
        snapshot_id = as_int(row, "id")
        levels = self._db.query(
            f"SELECT {_LEVEL_COLUMNS} FROM book_level WHERE snapshot_id = ? ORDER BY side, rank",
            (snapshot_id,),
        )
        grouped = _levels_by_side(levels)
        return Book(
            venue=as_text(row, "venue_code"),
            symbol=as_symbol(row, "symbol"),
            observed_at=parse_instant(as_text(row, "observed_at")),
            sequence=as_int(row, "sequence"),
            bids=tuple(grouped.get(Side.BID, ())),
            asks=tuple(grouped.get(Side.ASK, ())),
        )
