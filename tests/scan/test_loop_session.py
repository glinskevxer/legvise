"""The triangular pass, end to end against a real database."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.clock import FixedClock
from legvise.model.book import Book
from legvise.model.fee import FeeLadder
from legvise.model.instrument import Instrument
from legvise.model.plan import PlanKind
from legvise.money import dec
from legvise.scan.loop_session import LoopScanner
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.fees import FeeStore
from legvise.store.instruments import InstrumentStore
from legvise.store.plans import PlanStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

AT = dt.datetime(2025, 9, 3, 8, 0, tzinfo=dt.UTC)
AS_OF = "2025-09-03T08:00:00+00:00"

TRIANGLE = (
    ("BTC-USD", "99.9", "100"),
    ("ETH-BTC", "0.05", "0.0501"),
    ("ETH-USD", "5.012", "5.02"),
)


def market(venue: str, symbol: str) -> Instrument:
    return Instrument.build(
        venue,
        symbol,
        tick_size="0.0001",
        lot_step="0.00001",
        min_notional="1",
        max_notional="10000000",
    )


def book(venue: str, symbol: str, bid: str, ask: str) -> Book:
    return Book.build(
        venue,
        symbol,
        observed_at=AT,
        bids=((bid, "10000"),),
        asks=((ask, "10000"),),
    )


@pytest.fixture()
def venue(db: Database) -> Database:
    venues = VenueStore(db)
    instruments = InstrumentStore(db)
    fees = FeeStore(db)
    venues.add(make_venue("kraken"))
    for symbol, _, _ in TRIANGLE:
        instruments.add(market("kraken", symbol))
    fees.put_ladder(FeeLadder.build("kraken", (("0", "0", "0"),)))
    fees.record_volume("kraken", dec("0"), as_of=AS_OF)
    return db


def load(db: Database) -> None:
    books = BookStore(db)
    for symbol, bid, ask in TRIANGLE:
        books.add(book("kraken", symbol, bid, ask))


def scanner(db: Database, **changes: object) -> LoopScanner:
    fields: dict[str, object] = {
        "db": db,
        "clock": FixedClock(AT),
        "start_asset": "USD",
        "start_amount": dec("1000"),
        "min_edge_bps": dec("1"),
    }
    fields.update(changes)
    return LoopScanner(**fields)  # type: ignore[arg-type]


def test_a_venue_with_no_books_is_not_searched(venue: Database) -> None:
    report = scanner(venue).run()
    assert report.venues_searched == 0
    assert report.plans_written == 0


def test_a_venue_with_a_closed_triangle_is_searched(venue: Database) -> None:
    load(venue)
    report = scanner(venue).run()
    assert report.venues_searched == 1
    assert report.cycles_screened >= 1


def test_a_profitable_loop_is_written_as_a_plan(venue: Database) -> None:
    load(venue)
    report = scanner(venue).run()
    assert report.plans_written == 1
    plans = PlanStore(venue).for_session(report.session)
    assert plans[0].kind is PlanKind.TRIANGULAR
    assert len(plans[0].legs) == 3


def test_three_taker_fees_kill_the_loop(venue: Database) -> None:
    load(venue)
    FeeStore(venue).put_ladder(FeeLadder.build("kraken", (("0", "0", "16"),)))
    report = scanner(venue).run()
    assert report.cycles_screened >= 1
    assert report.plans_written == 0


def test_a_higher_edge_floor_turns_the_loop_down(venue: Database) -> None:
    load(venue)
    assert scanner(venue, min_edge_bps=dec("50")).run().plans_written == 0


def test_the_screen_can_reject_before_the_price(venue: Database) -> None:
    load(venue)
    report = scanner(venue, screen_bps=dec("100")).run()
    assert report.cycles_screened == 0
    assert report.plans_written == 0


def test_a_venue_with_no_fee_ladder_is_skipped_and_reported(venue: Database) -> None:
    load(venue)
    venue.execute("DELETE FROM fee_tier WHERE venue_code = 'kraken'")
    report = scanner(venue).run()
    assert report.plans_written == 0
    assert any("kraken" in note for note in report.skipped)


def test_a_venue_with_only_two_markets_cannot_close_a_loop(venue: Database) -> None:
    books = BookStore(venue)
    books.add(book("kraken", "BTC-USD", "99.9", "100"))
    books.add(book("kraken", "ETH-USD", "5.012", "5.02"))
    assert scanner(venue).run().venues_searched == 0


def test_a_one_sided_book_takes_its_market_out_of_the_search(venue: Database) -> None:
    books = BookStore(venue)
    books.add(book("kraken", "BTC-USD", "99.9", "100"))
    books.add(book("kraken", "ETH-BTC", "0.05", "0.0501"))
    books.add(Book.build("kraken", "ETH-USD", observed_at=AT, bids=(("5.012", "1"),)))
    assert scanner(venue).run().venues_searched == 0


def test_a_session_is_opened_even_when_nothing_is_found(venue: Database) -> None:
    report = scanner(venue).run()
    assert PlanStore(venue).session(report.session).ref == report.session


def test_starting_from_an_asset_with_no_loop_finds_nothing(venue: Database) -> None:
    load(venue)
    assert scanner(venue, start_asset="SOL").run().plans_written == 0


def test_two_passes_need_different_counters(venue: Database) -> None:
    load(venue)
    first = scanner(venue).run(counter=0)
    second = scanner(venue).run(counter=1)
    assert first.session != second.session
