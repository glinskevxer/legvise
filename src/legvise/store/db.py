"""The SQLite handle, its pragmas, and the only transaction helper.

The desk's book of record is a single file. That is a deliberate choice: a scan
is a read-mostly job against a few thousand rows, and an operator being able to
copy the file to a laptop and open it is worth more here than a server.

Two things are worth knowing before touching this module. Foreign keys are off
by default in SQLite and have to be turned on for every connection, so the
constraint the schema declares is only enforced because `connect` says so. And
`sqlite3` opens its own implicit transactions unless isolation is disabled, so
this module runs with `isolation_level=None` and issues BEGIN itself.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from legvise.errors import BadArgument, Conflict

__all__ = ["Database", "connect"]

_PRAGMAS: Final = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 4000",
    "PRAGMA synchronous = NORMAL",
)

Param = str | int | float | bytes | None


def _adapt_decimal(value: Decimal) -> str:
    """Plain notation, never scientific.

    `str(Decimal("0.00000001"))` is `1E-8`, and a column holding a mix of `1E-8`
    and `0.00000002` sorts and greps wrong even though both read back correctly.
    Eight decimal places is normal for a crypto size, so this matters here.
    """
    return format(value, "f")


sqlite3.register_adapter(Decimal, _adapt_decimal)


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the book of record with the pragmas the schema assumes."""
    target = str(path)
    conn = sqlite3.connect(target, isolation_level=None)
    conn.row_factory = sqlite3.Row
    for pragma in _PRAGMAS:
        conn.execute(pragma)
    return conn


class Database:
    """A thin wrapper that owns the connection and hands out rows.

    It is not an ORM and is not going to become one. The repositories under
    `legvise.store` write their own SQL; this only removes the boilerplate that
    would otherwise be copied into every one of them.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._depth = 0

    @classmethod
    def open(cls, path: str | Path) -> Database:
        """Open a database at a path, creating the file if it is not there."""
        return cls(connect(path))

    @classmethod
    def in_memory(cls) -> Database:
        """A throwaway database, for tests and for `--dry-run` work."""
        return cls(connect(":memory:"))

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for the migration runner only."""
        return self._conn

    def close(self) -> None:
        """Close the connection. Further use raises from sqlite3 itself."""
        self._conn.close()

    @contextmanager
    def tx(self) -> Iterator[Database]:
        """Run a block in one transaction, nesting by counting rather than saving.

        A nested `tx` joins the outer one. That is what the repositories want:
        a service can wrap three repository calls without any of them knowing.
        """
        if self._depth == 0:
            self._conn.execute("BEGIN")
        self._depth += 1
        try:
            yield self
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("COMMIT")

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run a statement, turning a unique violation into a `Conflict`."""
        try:
            return self._conn.execute(sql, tuple(params))
        except sqlite3.IntegrityError as exc:
            text = str(exc)
            if "UNIQUE" in text:
                raise Conflict("row", text.split(":")[-1].strip()) from None
            raise BadArgument("statement", sql.strip().split("\n")[0], text) from None

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """Every row a statement returns."""
        return list(self.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        """The first row a statement returns, or nothing."""
        rows = self.execute(sql, params).fetchmany(1)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        """The first column of the first row, or nothing."""
        row = self.query_one(sql, params)
        return None if row is None else row[0]
