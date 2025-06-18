"""Network storage, and the route query that has to check both ends."""

from __future__ import annotations

import pytest

from legvise.errors import NotFound
from legvise.model.network import TransferNetwork, VenueNetwork
from legvise.money import dec
from legvise.store.db import Database
from legvise.store.networks import NetworkStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

TRX = TransferNetwork.build(
    "USDT",
    "TRX",
    withdraw_fee="1",
    min_withdraw="10",
    confirmations=20,
    minutes_per_confirmation="0.05",
)
ERC20 = TransferNetwork.build(
    "USDT",
    "ERC20",
    withdraw_fee="12",
    min_withdraw="50",
    confirmations=12,
    minutes_per_confirmation="0.2",
)


@pytest.fixture()
def store(db: Database) -> NetworkStore:
    venues = VenueStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code))
    handle = NetworkStore(db)
    handle.put_network(TRX)
    handle.put_network(ERC20)
    return handle


def open_both(store: NetworkStore, venue: str, code: str) -> None:
    store.put_support(VenueNetwork.build(venue, "USDT", code))


def test_a_network_survives_a_round_trip(store: NetworkStore) -> None:
    assert store.network("USDT", "TRX") == TRX


def test_writing_a_network_twice_overwrites_it(store: NetworkStore) -> None:
    store.put_network(
        TransferNetwork.build(
            "USDT",
            "TRX",
            withdraw_fee="2",
            min_withdraw="10",
            confirmations=20,
            minutes_per_confirmation="0.05",
        )
    )
    assert store.require_network("USDT", "TRX").withdraw_fee == dec("2")


def test_a_network_that_is_not_there_reads_as_nothing(store: NetworkStore) -> None:
    assert store.network("BTC", "BTC-MAIN") is None


def test_requiring_a_missing_network_names_the_pair(store: NetworkStore) -> None:
    with pytest.raises(NotFound) as caught:
        store.require_network("BTC", "LIGHTNING")
    assert caught.value.key == "BTC:LIGHTNING"


def test_the_networks_for_an_asset_come_back_in_code_order(store: NetworkStore) -> None:
    assert [n.code for n in store.networks_for("USDT")] == ["ERC20", "TRX"]


def test_support_is_recorded_per_venue(store: NetworkStore) -> None:
    open_both(store, "kraken", "TRX")
    assert store.support("kraken", "USDT", "TRX") is not None
    assert store.support("okx", "USDT", "TRX") is None


def test_support_can_be_updated_in_place(store: NetworkStore) -> None:
    open_both(store, "kraken", "TRX")
    store.put_support(VenueNetwork.build("kraken", "USDT", "TRX", withdraw_enabled=False))
    entry = store.support("kraken", "USDT", "TRX")
    assert entry is not None
    assert not entry.withdraw_enabled


def test_support_on_a_venue_lists_every_network(store: NetworkStore) -> None:
    open_both(store, "kraken", "TRX")
    open_both(store, "kraken", "ERC20")
    assert [e.network for e in store.support_on("kraken", "USDT")] == ["ERC20", "TRX"]


def test_a_route_needs_both_ends_to_list_the_network(store: NetworkStore) -> None:
    open_both(store, "kraken", "TRX")
    assert store.routes_between("USDT", "kraken", "okx") == ()
    open_both(store, "okx", "TRX")
    assert [n.code for n in store.routes_between("USDT", "kraken", "okx")] == ["TRX"]


def test_a_suspended_withdrawal_closes_the_route_one_way_only(store: NetworkStore) -> None:
    store.put_support(VenueNetwork.build("kraken", "USDT", "TRX", withdraw_enabled=False))
    open_both(store, "okx", "TRX")
    assert store.routes_between("USDT", "kraken", "okx") == ()
    assert [n.code for n in store.routes_between("USDT", "okx", "kraken")] == ["TRX"]


def test_a_suspended_deposit_closes_the_receiving_end(store: NetworkStore) -> None:
    open_both(store, "kraken", "TRX")
    store.put_support(VenueNetwork.build("okx", "USDT", "TRX", deposit_enabled=False))
    assert store.routes_between("USDT", "kraken", "okx") == ()


def test_every_open_network_shows_up_as_a_route(store: NetworkStore) -> None:
    for code in ("TRX", "ERC20"):
        open_both(store, "kraken", code)
        open_both(store, "okx", code)
    assert [n.code for n in store.routes_between("USDT", "kraken", "okx")] == ["ERC20", "TRX"]


def test_dropping_a_venue_takes_its_support_rows(db: Database, store: NetworkStore) -> None:
    open_both(store, "kraken", "TRX")
    VenueStore(db).remove("kraken")
    assert store.support("kraken", "USDT", "TRX") is None


def test_support_for_a_network_nobody_declared_is_refused(store: NetworkStore) -> None:
    with pytest.raises(Exception):  # noqa: B017 - sqlite reports the foreign key generically
        store.put_support(VenueNetwork.build("kraken", "USDT", "SOLANA"))
