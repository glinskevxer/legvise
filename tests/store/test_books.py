"""Snapshot storage: the round trip, the newest, and the one true at a time."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import NotFound
from legvise.model.book import Book
from legvise.money import dec
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

AT = dt.datetime(2025, 4, 8, 11, 0, tzinfo=dt.UTC)


def a_book(venue: str = "kraken", *, offset_s: int = 0, shift: str = "0") -> Book:
    """A two sided book, moved bodily up or down so it never crosses itself."""
    move = dec(shift)

    def at(price: str) -> str:
        return str(dec(price) + move)

    return Book.build(
        venue,
        "BTC-USD",
        observed_at=AT + dt.timedelta(seconds=offset_s),
        bids=((at("100.0"), "2"), (at("99.5"), "5")),
        asks=((at("100.5"), "1"), (at("101.0"), "4")),
        sequence=offset_s,
    )


@pytest.fixture()
def store(db: Database) -> BookStore:
    venues = VenueStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code))
    return BookStore(db)


def test_a_snapshot_survives_a_round_trip(store: BookStore) -> None:
    given = a_book()
    read = store.get(store.add(given))
    assert read == given


def test_the_levels_come_back_in_book_order(store: BookStore) -> None:
    read = store.get(store.add(a_book()))
    assert [level.price for level in read.bids] == [dec("100.0"), dec("99.5")]
    assert [level.price for level in read.asks] == [dec("100.5"), dec("101.0")]


def test_a_one_sided_book_survives_a_round_trip(store: BookStore) -> None:
    given = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("100", "1"),))
    read = store.get(store.add(given))
    assert read.asks == ()
    assert len(read.bids) == 1


def test_a_snapshot_id_that_is_not_there_is_a_not_found(store: BookStore) -> None:
    with pytest.raises(NotFound):
        store.get(4321)


def test_the_latest_is_the_newest_observation(store: BookStore) -> None:
    store.add(a_book(offset_s=0, shift="0"))
    store.add(a_book(offset_s=30, shift="1"))
    store.add(a_book(offset_s=15, shift="0.5"))
    latest = store.latest("kraken", "BTC-USD")
    assert latest is not None
    assert latest.bids[0].price == dec("101.0")


def test_the_latest_is_per_venue(store: BookStore) -> None:
    store.add(a_book("kraken", shift="0"))
    store.add(a_book("okx", offset_s=30, shift="2"))
    kraken = store.latest("kraken", "BTC-USD")
    assert kraken is not None
    assert kraken.bids[0].price == dec("100.0")


def test_the_latest_answers_nothing_when_nothing_was_written(store: BookStore) -> None:
    assert store.latest("kraken", "BTC-USD") is None


def test_requiring_the_latest_names_the_pair_that_missed(store: BookStore) -> None:
    with pytest.raises(NotFound) as caught:
        store.require_latest("kraken", "BTC-USD")
    assert caught.value.key == "kraken:BTC-USD"


def test_as_of_ignores_anything_written_after_the_instant(store: BookStore) -> None:
    store.add(a_book(offset_s=0, shift="0"))
    store.add(a_book(offset_s=60, shift="5"))
    earlier = store.as_of("kraken", "BTC-USD", AT + dt.timedelta(seconds=30))
    assert earlier is not None
    assert earlier.bids[0].price == dec("100.0")


def test_as_of_includes_a_snapshot_stamped_exactly_at_the_instant(store: BookStore) -> None:
    store.add(a_book(offset_s=0))
    found = store.as_of("kraken", "BTC-USD", AT)
    assert found is not None


def test_as_of_before_the_first_snapshot_answers_nothing(store: BookStore) -> None:
    store.add(a_book(offset_s=60))
    assert store.as_of("kraken", "BTC-USD", AT) is None


def test_the_latest_across_venues_gets_one_book_each(store: BookStore) -> None:
    store.add(a_book("kraken", offset_s=0))
    store.add(a_book("kraken", offset_s=30))
    store.add(a_book("okx", offset_s=10))
    found = store.latest_across("BTC-USD")
    assert [b.venue for b in found] == ["kraken", "okx"]
    assert found[0].sequence == 30


def test_pruning_drops_the_old_snapshots_and_says_how_many(store: BookStore) -> None:
    store.add(a_book(offset_s=0))
    store.add(a_book(offset_s=60))
    assert store.prune_before(AT + dt.timedelta(seconds=30)) == 1
    assert store.count() == 1


def test_pruning_takes_the_levels_with_it(db: Database, store: BookStore) -> None:
    store.add(a_book(offset_s=0))
    store.prune_before(AT + dt.timedelta(seconds=30))
    assert db.scalar("SELECT count(*) FROM book_level") == 0


def test_dropping_a_venue_takes_its_snapshots(db: Database, store: BookStore) -> None:
    store.add(a_book("kraken"))
    VenueStore(db).remove("kraken")
    assert store.count() == 0
