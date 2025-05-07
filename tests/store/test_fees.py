"""Storing ladders and trailing volume, which move on different clocks."""

from __future__ import annotations

import pytest

from legvise.errors import NotFound
from legvise.fees.ladder import resolve
from legvise.model.fee import FeeLadder
from legvise.money import dec
from legvise.store.db import Database
from legvise.store.fees import FeeStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

RUNGS = (
    ("0", "10", "16"),
    ("1000000", "6", "10"),
    ("25000000", "0", "6"),
)
AS_OF = "2025-04-20T00:00:00+00:00"


@pytest.fixture()
def store(db: Database) -> FeeStore:
    venues = VenueStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code))
    return FeeStore(db)


def test_a_ladder_survives_a_round_trip(store: FeeStore) -> None:
    given = FeeLadder.build("kraken", RUNGS)
    store.put_ladder(given)
    assert store.ladder("kraken") == given


def test_the_rungs_come_back_in_ladder_order(store: FeeStore) -> None:
    store.put_ladder(FeeLadder.build("kraken", RUNGS))
    read = store.ladder("kraken")
    assert [t.min_volume_30d for t in read.tiers] == [dec("0"), dec("1000000"), dec("25000000")]


def test_a_venue_with_no_ladder_is_a_not_found(store: FeeStore) -> None:
    with pytest.raises(NotFound) as caught:
        store.ladder("kraken")
    assert caught.value.kind == "fee ladder"


def test_finding_a_missing_ladder_answers_nothing(store: FeeStore) -> None:
    assert store.find_ladder("kraken") is None


def test_replacing_a_ladder_removes_the_rungs_that_went_away(store: FeeStore) -> None:
    store.put_ladder(FeeLadder.build("kraken", RUNGS))
    store.put_ladder(FeeLadder.build("kraken", (("0", "8", "12"),)))
    read = store.ladder("kraken")
    assert read.depth() == 1
    assert read.base.taker_bps == 12


def test_replacing_one_venues_ladder_leaves_the_other_alone(store: FeeStore) -> None:
    store.put_ladder(FeeLadder.build("kraken", RUNGS))
    store.put_ladder(FeeLadder.build("okx", (("0", "2", "5"),)))
    assert store.ladder("kraken").depth() == 3
    assert store.ladder("okx").depth() == 1


def test_the_venues_with_ladders_are_listed_in_order(store: FeeStore) -> None:
    store.put_ladder(FeeLadder.build("okx", (("0", "2", "5"),)))
    store.put_ladder(FeeLadder.build("kraken", RUNGS))
    assert store.venues_with_ladders() == ("kraken", "okx")


def test_an_unrecorded_volume_reads_as_nothing(store: FeeStore) -> None:
    assert store.volume("kraken") is None
    assert store.volume_as_of("kraken") is None


def test_a_recorded_volume_comes_back_exact(store: FeeStore) -> None:
    store.record_volume("kraken", dec("1234567.89"), as_of=AS_OF)
    assert store.volume("kraken") == dec("1234567.89")
    assert store.volume_as_of("kraken") == AS_OF


def test_recording_twice_overwrites_rather_than_duplicating(store: FeeStore) -> None:
    store.record_volume("kraken", dec("1000"), as_of=AS_OF)
    store.record_volume("kraken", dec("2000"), as_of="2025-04-21T00:00:00+00:00")
    assert store.volume("kraken") == dec("2000")


def test_clearing_a_volume_puts_pricing_back_to_refusing(store: FeeStore) -> None:
    store.record_volume("kraken", dec("1000"), as_of=AS_OF)
    store.clear_volume("kraken")
    assert store.volume("kraken") is None


def test_the_ladder_and_the_volume_resolve_together(store: FeeStore) -> None:
    store.put_ladder(FeeLadder.build("kraken", RUNGS))
    store.record_volume("kraken", dec("30000000"), as_of=AS_OF)
    tier = resolve(store.ladder("kraken"), store.volume("kraken"))
    assert tier.taker_bps == 6


def test_dropping_a_venue_takes_its_ladder_and_its_volume(db: Database, store: FeeStore) -> None:
    store.put_ladder(FeeLadder.build("kraken", RUNGS))
    store.record_volume("kraken", dec("1000"), as_of=AS_OF)
    VenueStore(db).remove("kraken")
    assert store.find_ladder("kraken") is None
    assert store.volume("kraken") is None
