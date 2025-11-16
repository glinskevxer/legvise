"""Foreign keys are indexed on the child side, and the check can say otherwise."""

from __future__ import annotations

import pytest

from legvise.store.db import Database
from legvise.tools.check_indexes import (
    foreign_keys,
    indexed_columns,
    problems,
    problems_for,
)


@pytest.fixture()
def bare() -> Database:
    """A tiny schema with one indexed key and one that is not."""
    handle = Database.in_memory()
    handle.execute("CREATE TABLE parent (code TEXT PRIMARY KEY)")
    handle.execute(
        "CREATE TABLE good (code TEXT NOT NULL REFERENCES parent (code), n INTEGER,"
        " PRIMARY KEY (code, n))"
    )
    handle.execute("CREATE TABLE bad (code TEXT NOT NULL REFERENCES parent (code), n INTEGER)")
    return handle


def test_the_real_schema_indexes_every_child_side() -> None:
    assert problems() == []


def test_the_check_reports_an_unindexed_key(bare: Database) -> None:
    found = problems_for(bare)
    assert len(found) == 1
    assert "bad" in found[0]


def test_adding_the_index_clears_the_report(bare: Database) -> None:
    bare.execute("CREATE INDEX ix_bad_code ON bad (code)")
    assert problems_for(bare) == []


def test_a_primary_key_prefix_counts_as_an_index(bare: Database) -> None:
    found = problems_for(bare)
    assert not any("good" in line for line in found)


def test_an_index_that_starts_with_the_wrong_column_does_not_count(bare: Database) -> None:
    bare.execute("CREATE INDEX ix_bad_n ON bad (n, code)")
    assert len(problems_for(bare)) == 1


def test_the_keys_are_discovered_from_the_database(bare: Database) -> None:
    keys = {(key.child_table, key.parent_table) for key in foreign_keys(bare)}
    assert keys == {("good", "parent"), ("bad", "parent")}


def test_a_composite_key_is_read_as_one_key(bare: Database) -> None:
    handle = Database.in_memory()
    handle.execute("CREATE TABLE p (a TEXT, b TEXT, PRIMARY KEY (a, b))")
    handle.execute("CREATE TABLE c (a TEXT, b TEXT, FOREIGN KEY (a, b) REFERENCES p (a, b))")
    keys = foreign_keys(handle)
    assert len(keys) == 1
    assert set(keys[0].child_columns) == {"a", "b"}


def test_the_index_prefixes_include_the_primary_key(bare: Database) -> None:
    prefixes = indexed_columns(bare, "good")
    assert ("code", "n") in prefixes


def test_a_table_with_no_index_at_all_reports_nothing_indexed(bare: Database) -> None:
    assert indexed_columns(bare, "bad") == ()


def test_a_foreign_key_prints_readably(bare: Database) -> None:
    text = repr(foreign_keys(bare)[0])
    assert "->" in text
    assert "parent" in text
