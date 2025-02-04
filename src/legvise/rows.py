"""Reading typed values back out of a SQLite row.

SQLite stores five things and the desk keeps twelve. Decimals live in TEXT
columns, booleans live in INTEGER columns, symbols live as `BASE-QUOTE` text.
This module is where that translation happens, once, so a repository never
writes `Decimal(row["tick_size"])` and never has to remember that `active` is
an integer.

A missing column is a programming error and reads as one. A NULL in a column
the caller asked for without a default is also a programming error: the schema
says NOT NULL, so a NULL means the query is wrong.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation

from legvise.errors import BadArgument
from legvise.ids import Symbol, parse_symbol

__all__ = [
    "as_bool",
    "as_decimal",
    "as_int",
    "as_optional_text",
    "as_symbol",
    "as_text",
    "flag",
    "has_column",
]


def _cell(row: sqlite3.Row, column: str) -> object:
    if not has_column(row, column):
        raise BadArgument("column", column, "the query did not select it")
    return row[column]


def has_column(row: sqlite3.Row, column: str) -> bool:
    """True when the row carries the column at all, NULL or not.

    `column in row` would test the row's values, not its column names, which is
    the sort of thing that looks right and answers wrong. The tuple is
    deliberate.
    """
    return column in tuple(row.keys())


def as_text(row: sqlite3.Row, column: str) -> str:
    """A TEXT column that the schema says is NOT NULL."""
    value = _cell(row, column)
    if not isinstance(value, str):
        raise BadArgument(column, value, "expected text")
    return value


def as_optional_text(row: sqlite3.Row, column: str) -> str | None:
    """A TEXT column that is allowed to be NULL."""
    value = _cell(row, column)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BadArgument(column, value, "expected text or nothing")
    return value


def as_int(row: sqlite3.Row, column: str) -> int:
    """An INTEGER column that the schema says is NOT NULL."""
    value = _cell(row, column)
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadArgument(column, value, "expected an integer")
    return value


def as_bool(row: sqlite3.Row, column: str) -> bool:
    """An INTEGER column holding 0 or 1 and nothing else."""
    value = as_int(row, column)
    if value not in (0, 1):
        raise BadArgument(column, value, "a flag column holds 0 or 1")
    return value == 1


def as_decimal(row: sqlite3.Row, column: str) -> Decimal:
    """A TEXT column holding an exact decimal literal."""
    text = as_text(row, column)
    try:
        out = Decimal(text)
    except InvalidOperation:
        raise BadArgument(column, text, "not a decimal literal") from None
    if not out.is_finite():
        raise BadArgument(column, text, "must be finite")
    return out


def as_symbol(row: sqlite3.Row, column: str) -> Symbol:
    """A TEXT column holding the desk's canonical spelling of a market."""
    return parse_symbol(as_text(row, column))


def flag(value: bool) -> int:
    """The integer a boolean is stored as."""
    return 1 if value else 0
