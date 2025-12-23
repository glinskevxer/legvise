"""The schema itself: what it installs, and what it refuses to let in."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.store.db import Database
from legvise.store.schema import MIGRATIONS, install, table_names

AT = "2025-11-04T08:00:00+00:00"

EXPECTED_TABLES = (
    "applied_migration",
    "book_level",
    "book_snapshot",
    "fee_tier",
    "fill",
    "instrument",
    "inventory_band",
    "plan",
    "plan_leg",
    "position",
    "scan_session",
    "transfer_network",
    "venue",
    "venue_network",
    "venue_volume",
)


@pytest.fixture()
def fresh() -> Database:
    handle = Database.in_memory()
    install(handle, applied_at=AT)
    return handle


def test_every_expected_table_is_installed(fresh: Database) -> None:
    assert table_names(fresh) == EXPECTED_TABLES


def test_the_migration_versions_run_from_one_without_gaps() -> None:
    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, len(MIGRATIONS) + 1))


def test_every_migration_has_a_name_worth_reading() -> None:
    for step in MIGRATIONS:
        assert " " in step.name
        assert step.name == step.name.lower()


def test_every_migration_carries_at_least_one_statement() -> None:
    for step in MIGRATIONS:
        assert step.statements


def test_a_venue_with_a_zero_staleness_budget_is_refused_by_the_table(
    fresh: Database,
) -> None:
    with pytest.raises(BadArgument):
        fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 0, '35', '250000', 0, 1)")


def test_a_flag_column_refuses_anything_but_zero_or_one(fresh: Database) -> None:
    with pytest.raises(BadArgument):
        fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '250000', 2, 1)")


def test_a_book_level_side_has_to_be_a_side(fresh: Database) -> None:
    fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '250000', 0, 1)")
    fresh.execute(
        "INSERT INTO book_snapshot (venue_code, symbol, observed_at, sequence)"
        " VALUES ('kraken', 'BTC-USD', '2025-11-04T08:00:00+00:00', 0)"
    )
    with pytest.raises(BadArgument):
        fresh.execute("INSERT INTO book_level VALUES (1, 'middle', 0, '100', '1')")


def test_a_plan_status_has_to_be_one_the_model_knows(fresh: Database) -> None:
    fresh.execute("INSERT INTO scan_session VALUES ('S20251104.0001', ?, '2', 250, '1')", (AT,))
    with pytest.raises(BadArgument):
        fresh.execute(
            "INSERT INTO plan VALUES ('S20251104.0001/P000', 'S20251104.0001',"
            " 'cross_venue', 'BTC-USD', '200', '100', '20', '0', '0', '80', 'maybe', NULL)"
        )


def test_a_plan_kind_has_to_be_one_the_model_knows(fresh: Database) -> None:
    fresh.execute("INSERT INTO scan_session VALUES ('S20251104.0001', ?, '2', 250, '1')", (AT,))
    with pytest.raises(BadArgument):
        fresh.execute(
            "INSERT INTO plan VALUES ('S20251104.0001/P000', 'S20251104.0001',"
            " 'quadrangular', 'BTC-USD', '200', '100', '20', '0', '0', '80', 'priced', NULL)"
        )


def test_a_negative_sequence_number_is_refused_by_the_table(fresh: Database) -> None:
    fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '250000', 0, 1)")
    with pytest.raises(BadArgument):
        fresh.execute(
            "INSERT INTO book_snapshot (venue_code, symbol, observed_at, sequence)"
            " VALUES ('kraken', 'BTC-USD', '2025-11-04T08:00:00+00:00', -1)"
        )


def test_a_transfer_network_needs_at_least_one_confirmation(fresh: Database) -> None:
    with pytest.raises(BadArgument):
        fresh.execute("INSERT INTO transfer_network VALUES ('USDT', 'TRX', '1', '10', 0, '0.05')")


def test_installing_onto_an_already_migrated_database_does_nothing(fresh: Database) -> None:
    assert install(fresh, applied_at=AT) == ()


def test_every_table_carries_a_primary_key(fresh: Database) -> None:
    for name in table_names(fresh):
        columns = fresh.query(f"PRAGMA table_info({name})")
        assert any(row["pk"] for row in columns), f"{name} has no primary key"
