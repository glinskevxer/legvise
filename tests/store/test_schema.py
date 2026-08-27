"""The schema itself: what it installs, and what it refuses to let in."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress

import pytest

from legvise.errors import BadArgument, Conflict
from legvise.store.db import Database
from legvise.store.schema import MIGRATIONS, install, table_names

AT = "2025-11-04T08:00:00+00:00"

EXPECTED_TABLES = (
    "applied_migration",
    "book_level",
    "book_snapshot",
    "decision",
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
def fresh() -> Iterator[Database]:
    handle = Database.in_memory()
    install(handle, applied_at=AT)
    yield handle
    handle.close()


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


# What a delete takes with it, and what it refuses to leave behind.


def seeded(db: Database) -> None:
    """One venue with something hanging off every table that references it."""
    db.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '250000', 0, 1)")
    db.execute(
        "INSERT INTO instrument VALUES"
        " ('kraken', 'BTC-USD', 'BTC', 'USD', 'BTCUSD', '0.01', '0.0001', '10', '100000', 1)"
    )
    db.execute(
        "INSERT INTO book_snapshot (venue_code, symbol, observed_at, sequence)"
        " VALUES ('kraken', 'BTC-USD', ?, 0)",
        (AT,),
    )
    db.execute("INSERT INTO book_level VALUES (1, 'bid', 0, '99', '1')")
    db.execute("INSERT INTO fee_tier VALUES ('kraken', 0, '0', '0', '5')")
    db.execute("INSERT INTO venue_volume VALUES ('kraken', '0', ?)", (AT,))
    db.execute("INSERT INTO position VALUES ('kraken', 'BTC', '5', '0', ?)", (AT,))
    db.execute("INSERT INTO inventory_band VALUES ('kraken', 'BTC', '0', '5', '9')")
    db.execute("INSERT INTO transfer_network VALUES ('BTC', 'MAIN', '0.0002', '0.001', 3, '10')")
    db.execute("INSERT INTO venue_network VALUES ('kraken', 'BTC', 'MAIN', 1, 1)")


CHILD_TABLES = (
    "instrument",
    "book_snapshot",
    "book_level",
    "fee_tier",
    "venue_volume",
    "position",
    "inventory_band",
    "venue_network",
)


def test_dropping_a_venue_empties_every_table_that_hangs_off_it(fresh: Database) -> None:
    seeded(fresh)
    fresh.execute("DELETE FROM venue WHERE code = 'kraken'")
    for name in CHILD_TABLES:
        assert fresh.scalar(f"SELECT count(*) FROM {name}") == 0, name


def test_every_child_table_had_a_row_before_the_delete(fresh: Database) -> None:
    seeded(fresh)
    for name in CHILD_TABLES:
        assert fresh.scalar(f"SELECT count(*) FROM {name}") == 1, name


def test_dropping_a_network_takes_the_venue_support_with_it(fresh: Database) -> None:
    seeded(fresh)
    fresh.execute("DELETE FROM transfer_network WHERE asset = 'BTC' AND code = 'MAIN'")
    assert fresh.scalar("SELECT count(*) FROM venue_network") == 0


def test_dropping_a_snapshot_takes_its_levels(fresh: Database) -> None:
    seeded(fresh)
    fresh.execute("DELETE FROM book_snapshot WHERE id = 1")
    assert fresh.scalar("SELECT count(*) FROM book_level") == 0


def test_a_rolled_back_delete_puts_everything_back(fresh: Database) -> None:
    seeded(fresh)
    with pytest.raises(RuntimeError), fresh.tx():
        fresh.execute("DELETE FROM venue WHERE code = 'kraken'")
        raise RuntimeError("changed my mind")
    for name in CHILD_TABLES:
        assert fresh.scalar(f"SELECT count(*) FROM {name}") == 1, name


def test_a_failure_three_blocks_deep_rolls_the_whole_thing_back(fresh: Database) -> None:
    with pytest.raises(RuntimeError), fresh.tx():
        fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '2', 0, 1)")
        with fresh.tx():
            fresh.execute("INSERT INTO venue VALUES ('okx', 'OKX', 750, '35', '2', 0, 1)")
            with fresh.tx():
                fresh.execute(
                    "INSERT INTO venue VALUES ('bitstamp', 'Bitstamp', 750, '35', '2', 0, 1)"
                )
                raise RuntimeError("no")
    assert fresh.scalar("SELECT count(*) FROM venue") == 0


def test_an_inner_block_that_finishes_does_not_commit_on_its_own(fresh: Database) -> None:
    with pytest.raises(RuntimeError), fresh.tx():
        with fresh.tx():
            fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '2', 0, 1)")
        raise RuntimeError("the outer block still fails")
    assert fresh.scalar("SELECT count(*) FROM venue") == 0


def test_two_blocks_one_after_the_other_both_commit(fresh: Database) -> None:
    with fresh.tx():
        fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '2', 0, 1)")
    with fresh.tx():
        fresh.execute("INSERT INTO venue VALUES ('okx', 'OKX', 750, '35', '2', 0, 1)")
    assert fresh.scalar("SELECT count(*) FROM venue") == 2


def test_a_block_that_recovers_from_a_refusal_still_commits(fresh: Database) -> None:
    with fresh.tx():
        fresh.execute("INSERT INTO venue VALUES ('kraken', 'Kraken', 750, '35', '2', 0, 1)")
        with suppress(Conflict):
            fresh.execute("INSERT INTO venue VALUES ('kraken', 'Again', 750, '35', '2', 0, 1)")
    assert fresh.scalar("SELECT count(*) FROM venue") == 1
