"""Connection pragmas, the transaction helper, and how errors come back."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from legvise.errors import BadArgument, Conflict, NotFound
from legvise.store.db import Database, connect


@pytest.fixture()
def db() -> Database:
    handle = Database.in_memory()
    handle.execute("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    return handle


def test_foreign_keys_are_on_for_every_connection() -> None:
    conn = connect(":memory:")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_rows_come_back_addressable_by_column_name() -> None:
    conn = connect(":memory:")
    row = conn.execute("SELECT 4 AS four").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["four"] == 4


def test_a_decimal_is_stored_as_its_exact_text(db: Database) -> None:
    db.execute("INSERT INTO t VALUES (?, ?)", ("a", Decimal("0.00000001")))
    assert db.scalar("SELECT v FROM t WHERE k = 'a'") == "0.00000001"


def test_a_committed_block_survives_the_transaction(db: Database) -> None:
    with db.tx():
        db.execute("INSERT INTO t VALUES ('a', '1')")
    assert db.scalar("SELECT v FROM t WHERE k = 'a'") == "1"


def test_a_raising_block_leaves_nothing_behind(db: Database) -> None:
    with pytest.raises(RuntimeError), db.tx():
        db.execute("INSERT INTO t VALUES ('a', '1')")
        raise RuntimeError("no")
    assert db.scalar("SELECT count(*) FROM t") == 0


def test_a_nested_block_joins_the_outer_one(db: Database) -> None:
    with db.tx():
        db.execute("INSERT INTO t VALUES ('a', '1')")
        with db.tx():
            db.execute("INSERT INTO t VALUES ('b', '2')")
    assert db.scalar("SELECT count(*) FROM t") == 2


def test_a_failure_inside_a_nested_block_rolls_the_whole_thing_back(db: Database) -> None:
    with pytest.raises(RuntimeError), db.tx():
        db.execute("INSERT INTO t VALUES ('a', '1')")
        with db.tx():
            db.execute("INSERT INTO t VALUES ('b', '2')")
            raise RuntimeError("no")
    assert db.scalar("SELECT count(*) FROM t") == 0


def test_a_duplicate_key_reads_as_a_conflict(db: Database) -> None:
    db.execute("INSERT INTO t VALUES ('a', '1')")
    with pytest.raises(Conflict):
        db.execute("INSERT INTO t VALUES ('a', '2')")


def test_a_broken_constraint_that_is_not_a_duplicate_reads_as_a_bad_argument(
    db: Database,
) -> None:
    with pytest.raises(BadArgument):
        db.execute("INSERT INTO t VALUES ('a', NULL)")


def test_query_one_answers_nothing_when_there_is_no_row(db: Database) -> None:
    assert db.query_one("SELECT * FROM t WHERE k = 'missing'") is None


def test_query_returns_every_row_in_statement_order(db: Database) -> None:
    db.execute("INSERT INTO t VALUES ('a', '1')")
    db.execute("INSERT INTO t VALUES ('b', '2')")
    rows = db.query("SELECT k FROM t ORDER BY k")
    assert [r["k"] for r in rows] == ["a", "b"]


def test_a_database_can_be_opened_on_a_file(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    handle = Database.open(target)
    handle.execute("CREATE TABLE t (k TEXT)")
    handle.close()
    again = Database.open(target)
    assert again.scalar("SELECT count(*) FROM t") == 0
    again.close()


def test_a_batch_writes_every_row(db: Database) -> None:
    written = db.execute_many("INSERT INTO t VALUES (?, ?)", [("a", "1"), ("b", "2"), ("c", "3")])
    assert written == 3
    assert db.scalar("SELECT count(*) FROM t") == 3


def test_an_empty_batch_writes_nothing_and_says_so(db: Database) -> None:
    assert db.execute_many("INSERT INTO t VALUES (?, ?)", []) == 0


def test_a_batch_with_a_duplicate_key_reads_as_a_conflict(db: Database) -> None:
    with pytest.raises(Conflict):
        db.execute_many("INSERT INTO t VALUES (?, ?)", [("a", "1"), ("a", "2")])


def test_a_batch_with_a_broken_constraint_reads_as_a_bad_argument(db: Database) -> None:
    with pytest.raises(BadArgument):
        db.execute_many("INSERT INTO t VALUES (?, ?)", [("a", None)])


def test_a_batch_with_a_broken_statement_reads_as_a_bad_argument(db: Database) -> None:
    with pytest.raises(BadArgument):
        db.execute_many("INSERT INTO nowhere VALUES (?, ?)", [("a", "1")])


def test_a_batch_inside_a_rolled_back_block_leaves_nothing(db: Database) -> None:
    with pytest.raises(RuntimeError), db.tx():
        db.execute_many("INSERT INTO t VALUES (?, ?)", [("a", "1"), ("b", "2")])
        raise RuntimeError("no")
    assert db.scalar("SELECT count(*) FROM t") == 0


def test_a_batch_of_decimals_stores_them_in_plain_notation(db: Database) -> None:
    db.execute_many("INSERT INTO t VALUES (?, ?)", [("a", Decimal("0.00000001"))])
    assert db.scalar("SELECT v FROM t WHERE k = 'a'") == "0.00000001"


def test_a_read_only_book_answers_a_query(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    writer = Database.open(target)
    writer.execute("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    writer.execute("INSERT INTO t VALUES ('a', '1')")
    writer.close()
    reader = Database.open_read_only(target)
    assert reader.scalar("SELECT v FROM t WHERE k = 'a'") == "1"
    reader.close()


def test_a_read_only_book_refuses_a_write(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    writer = Database.open(target)
    writer.execute("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    writer.close()
    reader = Database.open_read_only(target)
    with pytest.raises(BadArgument):
        reader.execute("INSERT INTO t VALUES ('a', '1')")
    reader.close()


def test_a_read_only_book_refuses_a_schema_change(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    writer = Database.open(target)
    writer.execute("CREATE TABLE t (k TEXT PRIMARY KEY)")
    writer.close()
    reader = Database.open_read_only(target)
    with pytest.raises(BadArgument):
        reader.execute("CREATE TABLE u (k TEXT PRIMARY KEY)")
    reader.close()


def test_a_read_only_book_still_enforces_foreign_keys(tmp_path: Path) -> None:
    target = tmp_path / "book.sqlite3"
    writer = Database.open(target)
    writer.execute("CREATE TABLE t (k TEXT PRIMARY KEY)")
    writer.close()
    reader = Database.open_read_only(target)
    assert reader.scalar("PRAGMA foreign_keys") == 1
    reader.close()


def test_opening_a_book_that_is_not_there_read_only_is_a_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFound):
        Database.open_read_only(tmp_path / "nowhere.sqlite3")
