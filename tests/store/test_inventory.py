"""The inventory repository: balances overwritten, bands edited rarely."""

from __future__ import annotations

import pytest

from legvise.errors import NotFound
from legvise.model.inventory import Band, Position
from legvise.money import dec
from legvise.store.db import Database
from legvise.store.inventory import InventoryStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

AS_OF = "2025-06-02T07:00:00+00:00"
LATER = "2025-06-02T19:00:00+00:00"


@pytest.fixture()
def store(db: Database) -> InventoryStore:
    venues = VenueStore(db)
    for code in ("bitstamp", "kraken", "okx"):
        venues.add(make_venue(code))
    return InventoryStore(db)


def test_a_position_survives_a_round_trip(store: InventoryStore) -> None:
    given = Position.build("kraken", "BTC", free="4.5", locked="0.5", as_of=AS_OF)
    store.put_position(given)
    assert store.position("kraken", "BTC") == given


def test_writing_a_position_twice_overwrites_it(store: InventoryStore) -> None:
    store.put_position(Position.build("kraken", "BTC", free="4.5", as_of=AS_OF))
    store.put_position(Position.build("kraken", "BTC", free="2.0", as_of=LATER))
    read = store.require_position("kraken", "BTC")
    assert read.free == dec("2.0")
    assert read.as_of == LATER


def test_a_position_the_desk_does_not_hold_reads_as_nothing(store: InventoryStore) -> None:
    assert store.position("kraken", "DOGE") is None


def test_requiring_a_missing_position_names_the_pair(store: InventoryStore) -> None:
    with pytest.raises(NotFound) as caught:
        store.require_position("kraken", "DOGE")
    assert caught.value.key == "kraken:DOGE"


def test_an_asset_code_is_normalised_on_lookup(store: InventoryStore) -> None:
    store.put_position(Position.build("kraken", "BTC", free="1", as_of=AS_OF))
    assert store.position("kraken", "btc") is not None


def test_positions_on_a_venue_come_back_in_asset_order(store: InventoryStore) -> None:
    for asset in ("USD", "BTC", "ETH"):
        store.put_position(Position.build("kraken", asset, free="1", as_of=AS_OF))
    assert [p.asset for p in store.positions_on("kraken")] == ["BTC", "ETH", "USD"]


def test_one_asset_across_venues_comes_back_in_venue_order(store: InventoryStore) -> None:
    for venue in ("okx", "bitstamp", "kraken"):
        store.put_position(Position.build(venue, "BTC", free="1", as_of=AS_OF))
    assert [p.venue for p in store.positions_of("BTC")] == ["bitstamp", "kraken", "okx"]


def test_the_assets_held_are_listed_once_each(store: InventoryStore) -> None:
    store.put_position(Position.build("kraken", "BTC", free="1", as_of=AS_OF))
    store.put_position(Position.build("okx", "BTC", free="1", as_of=AS_OF))
    store.put_position(Position.build("okx", "USD", free="1", as_of=AS_OF))
    assert store.assets_held() == ("BTC", "USD")


def test_a_band_survives_a_round_trip(store: InventoryStore) -> None:
    given = Band.build("kraken", "BTC", floor="1", target="5", ceiling="9")
    store.put_band(given)
    assert store.band("kraken", "BTC") == given


def test_writing_a_band_twice_overwrites_it(store: InventoryStore) -> None:
    store.put_band(Band.build("kraken", "BTC", floor="1", target="5", ceiling="9"))
    store.put_band(Band.build("kraken", "BTC", floor="2", target="6", ceiling="10"))
    assert store.require_band("kraken", "BTC").floor == dec("2")


def test_a_band_that_was_never_set_reads_as_nothing(store: InventoryStore) -> None:
    assert store.band("kraken", "BTC") is None


def test_requiring_a_missing_band_names_the_pair(store: InventoryStore) -> None:
    with pytest.raises(NotFound) as caught:
        store.require_band("kraken", "BTC")
    assert caught.value.kind == "inventory band"


def test_bands_on_a_venue_come_back_in_asset_order(store: InventoryStore) -> None:
    for asset in ("USD", "BTC"):
        store.put_band(Band.build("kraken", asset, floor="1", target="5", ceiling="9"))
    assert [b.asset for b in store.bands_on("kraken")] == ["BTC", "USD"]


def test_removing_a_band_takes_it_out(store: InventoryStore) -> None:
    store.put_band(Band.build("kraken", "BTC", floor="1", target="5", ceiling="9"))
    store.remove_band("kraken", "BTC")
    assert store.band("kraken", "BTC") is None


def test_removing_a_band_that_is_not_there_is_a_not_found(store: InventoryStore) -> None:
    with pytest.raises(NotFound):
        store.remove_band("kraken", "BTC")


def test_dropping_a_venue_takes_its_balances_and_bands(db: Database, store: InventoryStore) -> None:
    store.put_position(Position.build("kraken", "BTC", free="1", as_of=AS_OF))
    store.put_band(Band.build("kraken", "BTC", floor="1", target="5", ceiling="9"))
    VenueStore(db).remove("kraken")
    assert store.position("kraken", "BTC") is None
    assert store.band("kraken", "BTC") is None
