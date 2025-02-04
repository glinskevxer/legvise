"""The migration runner: order, the ledger, and the frozen-text refusal."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.store.db import Database
from legvise.store.migrations import (
    Migration,
    applied_versions,
    migrate,
    pending,
    text_digest,
)
from legvise.store.schema import MIGRATIONS, install, table_names

AT = "2025-02-11T08:00:00+00:00"

ONE = Migration(1, "first", ("CREATE TABLE a (k TEXT PRIMARY KEY)",))
TWO = Migration(2, "second", ("CREATE TABLE b (k TEXT PRIMARY KEY)",))


@pytest.fixture()
def db() -> Database:
    return Database.in_memory()


def test_nothing_is_applied_on_a_fresh_database(db: Database) -> None:
    assert applied_versions(db) == {}


def test_every_step_is_pending_on_a_fresh_database(db: Database) -> None:
    assert pending(db, (ONE, TWO)) == (ONE, TWO)


def test_running_the_steps_creates_the_tables(db: Database) -> None:
    assert migrate(db, (ONE, TWO), applied_at=AT) == (1, 2)
    assert "a" in table_names(db)
    assert "b" in table_names(db)


def test_a_second_run_does_nothing(db: Database) -> None:
    migrate(db, (ONE, TWO), applied_at=AT)
    assert migrate(db, (ONE, TWO), applied_at=AT) == ()


def test_a_new_step_added_later_runs_on_its_own(db: Database) -> None:
    migrate(db, (ONE,), applied_at=AT)
    assert migrate(db, (ONE, TWO), applied_at=AT) == (2,)


def test_the_ledger_records_the_digest_each_step_ran_with(db: Database) -> None:
    migrate(db, (ONE, TWO), applied_at=AT)
    assert applied_versions(db) == {1: ONE.digest(), 2: TWO.digest()}


def test_editing_a_shipped_migration_is_refused(db: Database) -> None:
    migrate(db, (ONE,), applied_at=AT)
    edited = Migration(1, "first", ("CREATE TABLE a (k TEXT PRIMARY KEY, v TEXT)",))
    with pytest.raises(Refused) as caught:
        pending(db, (edited,))
    assert "text has changed" in caught.value.why


def test_renaming_a_shipped_migration_is_allowed(db: Database) -> None:
    migrate(db, (ONE,), applied_at=AT)
    renamed = Migration(1, "the first one", ONE.statements)
    assert pending(db, (renamed,)) == ()


def test_a_digest_ignores_surrounding_whitespace() -> None:
    assert text_digest(("  SELECT 1  ",)) == text_digest(("SELECT 1",))


def test_a_failing_step_leaves_the_ledger_untouched(db: Database) -> None:
    broken = Migration(2, "broken", ("CREATE TABLE b (",))
    with pytest.raises(BadArgument):
        migrate(db, (ONE, broken), applied_at=AT)
    assert applied_versions(db) == {}


def test_the_real_schema_installs_and_is_idempotent(db: Database) -> None:
    ran = install(db, applied_at=AT)
    assert ran == tuple(m.version for m in MIGRATIONS)
    assert install(db, applied_at=AT) == ()


def test_the_real_schema_has_the_tables_the_desk_starts_with(db: Database) -> None:
    install(db, applied_at=AT)
    names = table_names(db)
    assert "venue" in names
    assert "instrument" in names
    assert "applied_migration" in names


def test_migration_versions_are_unique_and_ascending() -> None:
    versions = [m.version for m in MIGRATIONS]
    assert versions == sorted(versions)
    assert len(versions) == len(set(versions))


def test_an_instrument_needs_a_venue_that_exists(db: Database) -> None:
    install(db, applied_at=AT)
    with pytest.raises(BadArgument):
        db.execute(
            "INSERT INTO instrument VALUES"
            " ('nowhere', 'BTC-USD', 'BTC', 'USD', 'BTCUSD', '0.01', '0.0001', '10', '100', 1)"
        )
