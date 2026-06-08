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

from legvise.errors import BadArgument, Conflict, NotFound

__all__ = ["Database", "connect"]

_PRAGMAS: Final = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 4000",
    "PRAGMA synchronous = NORMAL",
)

#: A read only connection cannot set the journal mode, so it gets the subset
#: that does not write to the file.
_READ_PRAGMAS: Final = ("PRAGMA foreign_keys = ON", "PRAGMA busy_timeout = 4000")

Param = str | int | float | bytes | None


def _adapt_decimal(value: Decimal) -> str:
    """Plain notation, never scientific.

    `str(Decimal("0.00000001"))` is `1E-8`, and a column holding a mix of `1E-8`
    and `0.00000002` sorts and greps wrong even though both read back correctly.
    Eight decimal places is normal for a crypto size, so this matters here.
    """
    return format(value, "f")


sqlite3.register_adapter(Decimal, _adapt_decimal)


def connect(path: str | Path, *, read_only: bool = False) -> sqlite3.Connection:
    """Open the book of record with the pragmas the schema assumes.

    `read_only` opens through SQLite's URI form, which refuses every write at
    the driver rather than by convention. A report that opens read only cannot
    migrate the file it is reading, which is the accident worth preventing: a
    dashboard pointed at production should not be able to apply a migration
    because somebody deployed it there first.
    """
    if read_only:
        conn = sqlite3.connect(
            f"file:{Path(path).as_posix()}?mode=ro", uri=True, isolation_level=None
        )
    else:
        conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    for pragma in _PRAGMAS if not read_only else _READ_PRAGMAS:
        conn.execute(pragma)
    return conn


def _first_line(sql: str) -> str:
    """The first non-blank line of a statement, for an error that has to be read."""
    for line in sql.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "<empty statement>"


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
    def open_read_only(cls, path: str | Path) -> Database:
        """Open an existing book that nothing can write to.

        The file has to be there. SQLite will not create one in read only mode,
        and a report that silently opened an empty database would answer every
        question with nothing.
        """
        if not Path(path).exists():
            raise NotFound("book of record", str(path))
        return cls(connect(path, read_only=True))

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
        """Run a statement, translating what sqlite3 raises into package errors.

        Nothing above this line should have to catch `sqlite3.Error`. A caller
        that catches `LegviseError` and still gets an `OperationalError` through
        is the bug this guards against.
        """
        try:
            return self._conn.execute(sql, tuple(params))
        except sqlite3.IntegrityError as exc:
            text = str(exc)
            if "UNIQUE" in text:
                raise Conflict("row", text.split(":")[-1].strip()) from None
            raise BadArgument("statement", _first_line(sql), text) from None
        except sqlite3.OperationalError as exc:
            raise BadArgument("statement", _first_line(sql), str(exc)) from None

    def execute_many(self, sql: str, rows: Sequence[Sequence[Any]]) -> int:
        """Run one statement over many parameter sets, and say how many.

        A book snapshot is forty rows and a busy desk writes one a second per
        market. Forty round trips through `execute` is forty statement
        preparations for one statement, and it shows up as a scan that spends
        more time writing what it saw than reading it.

        Errors translate the same way `execute` translates them, which is why
        this is here rather than reached for through `connection`.
        """
        if not rows:
            return 0
        try:
            cursor = self._conn.executemany(sql, [tuple(row) for row in rows])
        except sqlite3.IntegrityError as exc:
            text = str(exc)
            if "UNIQUE" in text:
                raise Conflict("row", text.split(":")[-1].strip()) from None
            raise BadArgument("statement", _first_line(sql), text) from None
        except sqlite3.OperationalError as exc:
            raise BadArgument("statement", _first_line(sql), str(exc)) from None
        return int(cursor.rowcount)

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
