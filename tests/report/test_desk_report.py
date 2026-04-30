"""Whether the desk is set up well enough to scan."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.model.book import Book
from legvise.model.fee import FeeLadder
from legvise.model.instrument import Instrument
from legvise.model.inventory import Band, Position
from legvise.money import dec
from legvise.report.desk_report import build_desk_status
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.fees import FeeStore
from legvise.store.instruments import InstrumentStore
from legvise.store.inventory import InventoryStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

AT = dt.datetime(2026, 4, 30, 9, 0, tzinfo=dt.UTC)
AS_OF = "2026-04-30T09:00:00+00:00"


@pytest.fixture()
def ready(db: Database) -> Database:
    venues = VenueStore(db)
    instruments = InstrumentStore(db)
    fees = FeeStore(db)
    inventory = InventoryStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code))
        instruments.add(
            Instrument.build(
                code,
                "BTC-USD",
                tick_size="0.01",
                lot_step="0.0001",
                min_notional="10",
                max_notional="10000000",
            )
        )
        fees.put_ladder(FeeLadder.build(code, (("0", "0", "5"),)))
        fees.record_volume(code, dec("0"), as_of=AS_OF)
        for asset in ("BTC", "USD"):
            inventory.put_position(Position.build(code, asset, free="100", as_of=AS_OF))
            inventory.put_band(Band.build(code, asset, floor="0", target="50", ceiling="1000"))
    return db


def test_a_desk_with_nothing_on_it_cannot_scan(db: Database) -> None:
    status = build_desk_status(db)
    assert status.venues == ()
    assert not status.can_scan


def test_a_fully_configured_desk_can_scan(ready: Database) -> None:
    status = build_desk_status(ready)
    assert status.can_scan
    assert status.gaps == ()


def test_every_venue_reports_its_market_count(ready: Database) -> None:
    status = build_desk_status(ready)
    assert all(venue.markets == 1 for venue in status.venues)


def test_a_venue_with_no_book_reports_none(ready: Database) -> None:
    assert all(venue.books == 0 for venue in build_desk_status(ready).venues)


def test_a_venue_with_a_book_reports_it(ready: Database) -> None:
    BookStore(ready).add(
        Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("99", "1"),), asks=(("101", "1"),))
    )
    status = build_desk_status(ready)
    assert next(v for v in status.venues if v.code == "kraken").books == 1


def test_a_venue_with_no_fee_ladder_is_not_ready(ready: Database) -> None:
    ready.execute("DELETE FROM fee_tier WHERE venue_code = 'okx'")
    status = build_desk_status(ready)
    assert "okx: no fee ladder" in status.gaps
    assert not status.can_scan


def test_a_venue_with_no_trailing_volume_is_not_ready(ready: Database) -> None:
    FeeStore(ready).clear_volume("okx")
    assert "okx: no trailing volume" in build_desk_status(ready).gaps


def test_a_venue_missing_a_band_is_not_ready(ready: Database) -> None:
    InventoryStore(ready).remove_band("okx", "USD")
    assert "okx: no band for USD" in build_desk_status(ready).gaps


def test_a_venue_missing_a_balance_is_not_ready(ready: Database) -> None:
    ready.execute("DELETE FROM position WHERE venue_code = 'okx' AND asset = 'BTC'")
    assert "okx: no balance for BTC" in build_desk_status(ready).gaps


def test_a_switched_off_venue_says_so_rather_than_listing_gaps(ready: Database) -> None:
    venues = VenueStore(ready)
    venues.save(venues.get("okx").deactivated())
    status = build_desk_status(ready)
    assert "okx: switched off" in status.gaps
    assert not status.can_scan


def test_one_ready_venue_is_not_enough_to_scan(ready: Database) -> None:
    VenueStore(ready).remove("okx")
    assert not build_desk_status(ready).can_scan


def test_the_shared_markets_are_the_ones_worth_scanning(ready: Database) -> None:
    status = build_desk_status(ready)
    assert len(status.shared_symbols) == 1


def test_a_desk_that_has_never_scanned_has_no_last_session(ready: Database) -> None:
    status = build_desk_status(ready)
    assert status.last_session is None
    assert status.sessions == 0


def test_a_gap_is_reported_once_however_many_markets_hit_it(ready: Database) -> None:
    InventoryStore(ready).remove_band("okx", "USD")
    gaps = [gap for gap in build_desk_status(ready).gaps if "no band for USD" in gap]
    assert len(gaps) == 1
