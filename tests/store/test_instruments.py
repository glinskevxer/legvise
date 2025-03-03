"""The instrument repository, including the lookups the scanner starts from."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Conflict, NotFound
from legvise.ids import Symbol
from legvise.model.instrument import Instrument
from legvise.store.db import Database
from legvise.store.instruments import InstrumentStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue


def an_instrument(venue: str, symbol: str, **changes: object) -> Instrument:
    fields: dict[str, object] = {
        "tick_size": "0.1",
        "lot_step": "0.00001",
        "min_notional": "10",
        "max_notional": "500000",
    }
    fields.update(changes)
    return Instrument.build(venue, symbol, **fields)  # type: ignore[arg-type]


@pytest.fixture()
def store(db: Database) -> InstrumentStore:
    venues = VenueStore(db)
    for code in ("bitstamp", "kraken", "okx"):
        venues.add(make_venue(code))
    return InstrumentStore(db)


def test_an_instrument_survives_a_round_trip(store: InstrumentStore) -> None:
    given = an_instrument("kraken", "BTC-USD", venue_symbol="XBTUSD")
    store.add(given)
    assert store.get("kraken", "BTC-USD") == given


def test_a_symbol_object_works_as_a_key_too(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    assert store.get("kraken", Symbol("BTC", "USD")).venue == "kraken"


def test_an_instrument_on_a_venue_that_does_not_exist_is_refused(
    store: InstrumentStore,
) -> None:
    with pytest.raises(BadArgument):
        store.add(an_instrument("nowhere", "BTC-USD"))


def test_the_same_market_twice_on_one_venue_is_a_conflict(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    with pytest.raises(Conflict):
        store.add(an_instrument("kraken", "BTC-USD"))


def test_the_same_market_on_two_venues_is_the_whole_point(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    store.add(an_instrument("okx", "BTC-USD"))
    assert len(store.for_symbol("BTC-USD")) == 2


def test_asking_for_a_missing_instrument_names_the_pair(store: InstrumentStore) -> None:
    with pytest.raises(NotFound) as caught:
        store.get("kraken", "DOGE-USD")
    assert caught.value.key == "kraken:DOGE-USD"


def test_find_answers_nothing_rather_than_raising(store: InstrumentStore) -> None:
    assert store.find("kraken", "DOGE-USD") is None


def test_everything_on_a_venue_comes_back_in_symbol_order(store: InstrumentStore) -> None:
    for symbol in ("SOL-USD", "BTC-USD", "ETH-USD"):
        store.add(an_instrument("kraken", symbol))
    assert [str(i.symbol) for i in store.for_venue("kraken")] == [
        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
    ]


def test_a_venue_listing_can_skip_the_markets_that_are_switched_off(
    store: InstrumentStore,
) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    store.add(an_instrument("kraken", "ETH-USD", active=False))
    assert len(store.for_venue("kraken", active_only=True)) == 1
    assert len(store.for_venue("kraken")) == 2


def test_a_symbol_lookup_skips_switched_off_listings_by_default(
    store: InstrumentStore,
) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    store.add(an_instrument("okx", "BTC-USD", active=False))
    assert [i.venue for i in store.for_symbol("BTC-USD")] == ["kraken"]
    assert len(store.for_symbol("BTC-USD", active_only=False)) == 2


def test_symbols_on_a_venue_reads_the_keys_only(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "ETH-USD"))
    store.add(an_instrument("kraken", "BTC-USD"))
    assert store.symbols_on("kraken") == (Symbol("BTC", "USD"), Symbol("ETH", "USD"))


def test_shared_symbols_needs_the_market_on_two_venues(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    store.add(an_instrument("okx", "BTC-USD"))
    store.add(an_instrument("kraken", "SOL-USD"))
    assert store.shared_symbols() == (Symbol("BTC", "USD"),)


def test_shared_symbols_counts_venues_not_rows(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    store.add(an_instrument("okx", "BTC-USD", active=False))
    assert store.shared_symbols() == ()


def test_shared_symbols_takes_a_higher_bar_when_asked(store: InstrumentStore) -> None:
    for venue in ("bitstamp", "kraken", "okx"):
        store.add(an_instrument(venue, "BTC-USD"))
    store.add(an_instrument("kraken", "SOL-USD"))
    store.add(an_instrument("okx", "SOL-USD"))
    assert store.shared_symbols(minimum_venues=3) == (Symbol("BTC", "USD"),)


def test_saving_overwrites_the_filters(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    store.save(an_instrument("kraken", "BTC-USD", tick_size="0.5", active=False))
    read = store.get("kraken", "BTC-USD")
    assert str(read.tick_size) == "0.5"
    assert read.active is False


def test_saving_something_that_was_never_added_is_a_not_found(store: InstrumentStore) -> None:
    with pytest.raises(NotFound):
        store.save(an_instrument("kraken", "DOGE-USD"))


def test_removing_takes_the_row_out(store: InstrumentStore) -> None:
    store.add(an_instrument("kraken", "BTC-USD"))
    store.remove("kraken", "BTC-USD")
    assert store.find("kraken", "BTC-USD") is None


def test_removing_something_that_is_not_there_is_a_not_found(store: InstrumentStore) -> None:
    with pytest.raises(NotFound):
        store.remove("kraken", "BTC-USD")


def test_dropping_a_venue_takes_its_instruments_with_it(db: Database) -> None:
    venues = VenueStore(db)
    venues.add(make_venue("kraken"))
    instruments = InstrumentStore(db)
    instruments.add(an_instrument("kraken", "BTC-USD"))
    venues.remove("kraken")
    assert instruments.for_venue("kraken") == ()
