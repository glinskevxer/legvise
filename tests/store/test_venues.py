"""The venue repository, against a real migrated database."""

from __future__ import annotations

from decimal import Decimal

import pytest

from legvise.errors import Conflict, NotFound
from legvise.store.db import Database
from legvise.store.venues import VenueStore
from tests.conftest import make_venue


@pytest.fixture()
def store(db: Database) -> VenueStore:
    return VenueStore(db)


def test_a_venue_survives_a_round_trip(store: VenueStore) -> None:
    given = make_venue("kraken", pays_maker_rebate=True)
    store.add(given)
    assert store.get("kraken") == given


def test_decimal_columns_come_back_exact(store: VenueStore) -> None:
    store.add(make_venue("okx", depth_limit_bps="12.5", notional_cap="187500.25"))
    read = store.get("okx")
    assert read.depth_limit_bps == Decimal("12.5")
    assert read.notional_cap == Decimal("187500.25")


def test_asking_for_a_venue_that_is_not_there_names_it(store: VenueStore) -> None:
    with pytest.raises(NotFound) as caught:
        store.get("nowhere")
    assert caught.value.kind == "venue"
    assert caught.value.key == "nowhere"


def test_find_answers_nothing_rather_than_raising(store: VenueStore) -> None:
    assert store.find("nowhere") is None


def test_adding_the_same_code_twice_is_a_conflict(store: VenueStore) -> None:
    store.add(make_venue("kraken"))
    with pytest.raises(Conflict):
        store.add(make_venue("kraken"))


def test_listing_comes_back_in_code_order(store: VenueStore) -> None:
    for code in ("okx", "bitstamp", "kraken"):
        store.add(make_venue(code))
    assert [v.code for v in store.list()] == ["bitstamp", "kraken", "okx"]


def test_listing_can_skip_the_venues_that_are_switched_off(store: VenueStore) -> None:
    store.add(make_venue("kraken"))
    store.add(make_venue("okx", active=False))
    assert [v.code for v in store.list(active_only=True)] == ["kraken"]
    assert len(store.list()) == 2


def test_saving_overwrites_every_mutable_field(store: VenueStore) -> None:
    store.add(make_venue("kraken"))
    store.save(store.get("kraken").replacing(staleness_budget_ms=400, active=False))
    read = store.get("kraken")
    assert read.staleness_budget_ms == 400
    assert read.active is False


def test_saving_a_venue_that_was_never_added_is_a_not_found(store: VenueStore) -> None:
    with pytest.raises(NotFound):
        store.save(make_venue("ghost"))


def test_removing_takes_the_row_out(store: VenueStore) -> None:
    store.add(make_venue("kraken"))
    store.remove("kraken")
    assert store.find("kraken") is None


def test_removing_a_venue_that_is_not_there_is_a_not_found(store: VenueStore) -> None:
    with pytest.raises(NotFound):
        store.remove("ghost")


def test_codes_reads_the_keys_without_building_records(store: VenueStore) -> None:
    store.add(make_venue("okx"))
    store.add(make_venue("kraken"))
    assert store.codes() == ("kraken", "okx")


def test_a_rolled_back_block_leaves_no_venue_behind(db: Database) -> None:
    store = VenueStore(db)
    with pytest.raises(RuntimeError), db.tx():
        store.add(make_venue("kraken"))
        raise RuntimeError("changed my mind")
    assert store.codes() == ()
