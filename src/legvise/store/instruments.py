"""Reading and writing instrument records.

The lookups this repository offers are the ones the scanner actually makes:
one instrument on one venue, every instrument on a venue, and -- the one that
matters -- every venue that lists a given symbol, which is how a cross-venue
scan finds its candidates.
"""

from __future__ import annotations

import sqlite3

from legvise.errors import NotFound
from legvise.ids import Symbol, parse_symbol, symbol_text
from legvise.model.instrument import Instrument
from legvise.rows import as_bool, as_decimal, as_symbol, as_text, flag
from legvise.store.db import Database

__all__ = ["InstrumentStore"]

_COLUMNS = (
    "venue_code, symbol, base_asset, quote_asset, venue_symbol,"
    " tick_size, lot_step, min_notional, max_notional, active"
)


def _read(row: sqlite3.Row) -> Instrument:
    return Instrument(
        venue=as_text(row, "venue_code"),
        symbol=as_symbol(row, "symbol"),
        venue_symbol=as_text(row, "venue_symbol"),
        tick_size=as_decimal(row, "tick_size"),
        lot_step=as_decimal(row, "lot_step"),
        min_notional=as_decimal(row, "min_notional"),
        max_notional=as_decimal(row, "max_notional"),
        active=as_bool(row, "active"),
    )


class InstrumentStore:
    """The instrument table, and nothing else."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, instrument: Instrument) -> Instrument:
        """Insert an instrument. The venue has to exist already."""
        self._db.execute(
            f"INSERT INTO instrument ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                instrument.venue,
                symbol_text(instrument.symbol),
                instrument.base,
                instrument.quote,
                instrument.venue_symbol,
                instrument.tick_size,
                instrument.lot_step,
                instrument.min_notional,
                instrument.max_notional,
                flag(instrument.active),
            ),
        )
        return instrument

    def get(self, venue: str, symbol: str | Symbol) -> Instrument:
        """One instrument, or a `NotFound` naming the pair that missed."""
        found = self.find(venue, symbol)
        if found is None:
            raise NotFound("instrument", f"{venue}:{symbol}")
        return found

    def find(self, venue: str, symbol: str | Symbol) -> Instrument | None:
        """One instrument, or nothing."""
        key = symbol if isinstance(symbol, Symbol) else parse_symbol(symbol)
        row = self._db.query_one(
            f"SELECT {_COLUMNS} FROM instrument WHERE venue_code = ? AND symbol = ?",
            (venue, symbol_text(key)),
        )
        return None if row is None else _read(row)

    def for_venue(self, venue: str, *, active_only: bool = False) -> tuple[Instrument, ...]:
        """Every instrument listed on one venue, in symbol order."""
        where = " AND active = 1" if active_only else ""
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM instrument WHERE venue_code = ?{where} ORDER BY symbol",
            (venue,),
        )
        return tuple(_read(r) for r in rows)

    def for_symbol(
        self, symbol: str | Symbol, *, active_only: bool = True
    ) -> tuple[Instrument, ...]:
        """Every venue that lists a symbol, in venue order.

        This is the cross-venue scan's entry point, so it defaults to skipping
        anything switched off. A scan should never have to remember to ask.
        """
        key = symbol if isinstance(symbol, Symbol) else parse_symbol(symbol)
        where = " AND active = 1" if active_only else ""
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM instrument WHERE symbol = ?{where} ORDER BY venue_code",
            (symbol_text(key),),
        )
        return tuple(_read(r) for r in rows)

    def symbols_on(self, venue: str) -> tuple[Symbol, ...]:
        """Every symbol a venue lists, without building the records."""
        rows = self._db.query(
            "SELECT symbol FROM instrument WHERE venue_code = ? ORDER BY symbol", (venue,)
        )
        return tuple(as_symbol(r, "symbol") for r in rows)

    def shared_symbols(self, *, minimum_venues: int = 2) -> tuple[Symbol, ...]:
        """Symbols listed on at least `minimum_venues` active venues.

        The scanner starts here: a symbol on one venue cannot be arbitraged
        across venues, so there is no point loading its book.
        """
        rows = self._db.query(
            "SELECT symbol FROM instrument WHERE active = 1"
            " GROUP BY symbol HAVING count(DISTINCT venue_code) >= ?"
            " ORDER BY symbol",
            (minimum_venues,),
        )
        return tuple(as_symbol(r, "symbol") for r in rows)

    def save(self, instrument: Instrument) -> Instrument:
        """Overwrite an existing instrument."""
        cursor = self._db.execute(
            "UPDATE instrument SET venue_symbol = ?, tick_size = ?, lot_step = ?,"
            " min_notional = ?, max_notional = ?, active = ?"
            " WHERE venue_code = ? AND symbol = ?",
            (
                instrument.venue_symbol,
                instrument.tick_size,
                instrument.lot_step,
                instrument.min_notional,
                instrument.max_notional,
                flag(instrument.active),
                instrument.venue,
                symbol_text(instrument.symbol),
            ),
        )
        if cursor.rowcount == 0:
            raise NotFound("instrument", f"{instrument.venue}:{instrument.symbol}")
        return instrument

    def remove(self, venue: str, symbol: str | Symbol) -> None:
        """Delete one instrument."""
        key = symbol if isinstance(symbol, Symbol) else parse_symbol(symbol)
        cursor = self._db.execute(
            "DELETE FROM instrument WHERE venue_code = ? AND symbol = ?",
            (venue, symbol_text(key)),
        )
        if cursor.rowcount == 0:
            raise NotFound("instrument", f"{venue}:{key}")
