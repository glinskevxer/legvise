"""The store-backed pricer, including what it does when no route is open."""

from __future__ import annotations

import pytest

from legvise.model.network import TransferNetwork, VenueNetwork
from legvise.money import dec
from legvise.routing.pricer import StoreRebalancePricer
from legvise.routing.rebalance import CarryTerms
from legvise.store.db import Database
from legvise.store.networks import NetworkStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

TERMS = CarryTerms(carry_bps_per_hour=dec("6"), cycles_served=10)
STRANDED = dec("250")

BTC_MAIN = TransferNetwork.build(
    "BTC",
    "BTC-MAIN",
    withdraw_fee="0.0002",
    min_withdraw="0.001",
    confirmations=3,
    minutes_per_confirmation="10",
)
LIGHTNING = TransferNetwork.build(
    "BTC",
    "LIGHTNING",
    withdraw_fee="0.000001",
    min_withdraw="0.0001",
    confirmations=1,
    minutes_per_confirmation="0.05",
)


@pytest.fixture()
def networks(db: Database) -> NetworkStore:
    venues = VenueStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code))
    store = NetworkStore(db)
    store.put_network(BTC_MAIN)
    store.put_network(LIGHTNING)
    return store


@pytest.fixture()
def pricer(networks: NetworkStore) -> StoreRebalancePricer:
    return StoreRebalancePricer(networks=networks, terms=TERMS, stranded_bps=STRANDED)


def open_route(networks: NetworkStore, code: str) -> None:
    for venue in ("kraken", "okx"):
        networks.put_support(VenueNetwork.build(venue, "BTC", code))


def charge(pricer: StoreRebalancePricer, excess: str) -> object:
    return pricer.charge_bps(
        asset="BTC",
        sender="kraken",
        receiver="okx",
        excess=dec(excess),
        unit_price=dec("100000"),
        notional=dec("500000"),
    )


def test_no_excess_costs_nothing(pricer: StoreRebalancePricer) -> None:
    assert charge(pricer, "0") == dec("0")


def test_a_negative_excess_costs_nothing(pricer: StoreRebalancePricer) -> None:
    assert charge(pricer, "-1") == dec("0")


def test_no_open_route_falls_back_to_the_stranding_charge(
    pricer: StoreRebalancePricer,
) -> None:
    assert charge(pricer, "1") == STRANDED


def test_an_open_route_is_priced_rather_than_stranded(
    pricer: StoreRebalancePricer, networks: NetworkStore
) -> None:
    open_route(networks, "LIGHTNING")
    assert dec("0") < charge(pricer, "1") < STRANDED  # type: ignore[operator]


def test_the_cheaper_of_two_open_routes_is_used(
    pricer: StoreRebalancePricer, networks: NetworkStore
) -> None:
    open_route(networks, "BTC-MAIN")
    only_chain = charge(pricer, "1")
    open_route(networks, "LIGHTNING")
    both = charge(pricer, "1")
    assert both < only_chain  # type: ignore[operator]


def test_an_excess_below_every_minimum_is_stranded(
    pricer: StoreRebalancePricer, networks: NetworkStore
) -> None:
    open_route(networks, "BTC-MAIN")
    assert charge(pricer, "0.0005") == STRANDED


def test_the_chosen_route_can_be_named(
    pricer: StoreRebalancePricer, networks: NetworkStore
) -> None:
    open_route(networks, "BTC-MAIN")
    open_route(networks, "LIGHTNING")
    assert pricer.route_for("BTC", "kraken", "okx", dec("1")) == "LIGHTNING"


def test_no_route_names_nothing(pricer: StoreRebalancePricer) -> None:
    assert pricer.route_for("BTC", "kraken", "okx", dec("1")) is None


def test_no_excess_names_nothing(pricer: StoreRebalancePricer, networks: NetworkStore) -> None:
    open_route(networks, "LIGHTNING")
    assert pricer.route_for("BTC", "kraken", "okx", dec("0")) is None


def test_a_one_way_route_does_not_price_the_other_way(
    pricer: StoreRebalancePricer, networks: NetworkStore
) -> None:
    networks.put_support(VenueNetwork.build("kraken", "BTC", "LIGHTNING", withdraw_enabled=False))
    networks.put_support(VenueNetwork.build("okx", "BTC", "LIGHTNING"))
    assert charge(pricer, "1") == STRANDED


def test_a_bigger_plan_carries_a_smaller_share(
    pricer: StoreRebalancePricer, networks: NetworkStore
) -> None:
    open_route(networks, "LIGHTNING")
    small = pricer.charge_bps(
        asset="BTC",
        sender="kraken",
        receiver="okx",
        excess=dec("1"),
        unit_price=dec("100000"),
        notional=dec("100000"),
    )
    large = pricer.charge_bps(
        asset="BTC",
        sender="kraken",
        receiver="okx",
        excess=dec("1"),
        unit_price=dec("100000"),
        notional=dec("1000000"),
    )
    assert large < small
