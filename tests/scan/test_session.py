"""A whole scan, end to end, against a real database."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.clock import FixedClock
from legvise.model.audit import Stage
from legvise.model.book import Book
from legvise.model.fee import FeeLadder
from legvise.model.instrument import Instrument
from legvise.model.inventory import Band, Position
from legvise.model.plan import PlanStatus
from legvise.money import dec
from legvise.risk.caps import CapSet
from legvise.scan.direct import ScanTerms
from legvise.scan.session import Scanner
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.decisions import DecisionStore
from legvise.store.fees import FeeStore
from legvise.store.instruments import InstrumentStore
from legvise.store.inventory import InventoryStore
from legvise.store.plans import PlanStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

AT = dt.datetime(2025, 7, 29, 9, 0, tzinfo=dt.UTC)
AS_OF = "2025-07-29T09:00:00+00:00"

WIDE_CAPS = CapSet(
    venue_cap=dec("10000000"),
    venue_used=dec("0"),
    asset_cap=dec("10000000"),
    asset_used=dec("0"),
    gross_cap=dec("100000000"),
    gross_used=dec("0"),
)
TERMS = ScanTerms(min_edge_bps=dec("1"), pairing_window_ms=1000, wanted_size=dec("1"))


def market(venue: str, symbol: str = "BTC-USD") -> Instrument:
    return Instrument.build(
        venue,
        symbol,
        tick_size="0.01",
        lot_step="0.0001",
        min_notional="10",
        max_notional="10000000",
    )


def book(venue: str, bid: str, ask: str, symbol: str = "BTC-USD") -> Book:
    return Book.build(
        venue,
        symbol,
        observed_at=AT,
        bids=((bid, "50"),),
        asks=((ask, "50"),),
    )


@pytest.fixture()
def wired(db: Database) -> Database:
    venues = VenueStore(db)
    instruments = InstrumentStore(db)
    fees = FeeStore(db)
    inventory = InventoryStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code, staleness_budget_ms=60000, depth_limit_bps="500"))
        instruments.add(market(code))
        fees.put_ladder(FeeLadder.build(code, (("0", "0", "5"),)))
        fees.record_volume(code, dec("0"), as_of=AS_OF)
        for asset, free, ceiling in (("BTC", "50", "1000"), ("USD", "5000000", "50000000")):
            inventory.put_position(Position.build(code, asset, free=free, as_of=AS_OF))
            inventory.put_band(Band.build(code, asset, floor="0", target="25", ceiling=ceiling))
    return db


def scanner(db: Database, **changes: object) -> Scanner:
    fields: dict[str, object] = {
        "db": db,
        "clock": FixedClock(AT),
        "terms": TERMS,
        "caps": WIDE_CAPS,
    }
    fields.update(changes)
    return Scanner(**fields)  # type: ignore[arg-type]


def test_a_scan_with_no_books_prices_nothing(wired: Database) -> None:
    report = scanner(wired).run()
    assert report.symbols_considered == 1
    assert report.pairs_priced == 0
    assert report.hit_rate == dec("0")


def test_a_scan_opens_a_session_even_when_it_finds_nothing(wired: Database) -> None:
    report = scanner(wired).run()
    assert PlanStore(wired).session(report.session).ref == report.session


def test_two_books_that_do_not_cross_are_never_priced(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "99.00", "100.00"))
    assert scanner(wired).run().pairs_priced == 0


def test_a_crossing_pair_is_priced_and_written(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    report = scanner(wired).run()
    assert report.pairs_priced == 1
    assert report.actionable == 1
    assert report.hit_rate == dec("1")


def test_the_written_plan_reads_back_with_its_legs(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    report = scanner(wired).run()
    plans = PlanStore(wired).for_session(report.session)
    assert len(plans) == 1
    assert plans[0].venues == ("kraken", "okx")
    assert plans[0].arithmetic_holds()


def test_only_the_direction_that_crosses_is_priced(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    plans = PlanStore(wired).for_session(scanner(wired).run().session)
    assert plans[0].legs[0].venue == "kraken"


def test_a_pair_the_edge_floor_turns_down_is_recorded_as_refused(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "100.01", "101.00"))
    report = scanner(wired, terms=ScanTerms(dec("500"), 1000, dec("1"))).run()
    assert report.actionable == 0
    assert report.refusals == {"EDGE.01": 1}


def test_a_venue_with_no_fee_ladder_is_skipped_and_reported(wired: Database) -> None:
    wired.execute("DELETE FROM fee_tier WHERE venue_code = 'okx'")
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    report = scanner(wired).run()
    assert report.pairs_priced == 0
    assert any("okx" in note for note in report.skipped)


def test_a_venue_with_no_band_is_skipped(wired: Database) -> None:
    InventoryStore(wired).remove_band("okx", "USD")
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    assert scanner(wired).run().pairs_priced == 0


def test_a_switched_off_venue_takes_no_part(wired: Database) -> None:
    venues = VenueStore(wired)
    venues.save(venues.get("okx").deactivated())
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    assert scanner(wired).run().pairs_priced == 0


def test_a_one_sided_book_is_skipped_and_reported(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(Book.build("okx", "BTC-USD", observed_at=AT, bids=(("101.00", "50"),)))
    report = scanner(wired).run()
    assert any("two sided" in note for note in report.skipped)


def test_a_stale_book_reads_as_a_refusal_rather_than_a_skip(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    late = FixedClock(AT + dt.timedelta(seconds=600))
    report = scanner(wired, clock=late).run()
    assert report.refusals == {"STALE.01": 1}


def test_a_refused_plan_still_records_both_venues(wired: Database) -> None:
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    late = FixedClock(AT + dt.timedelta(seconds=600))
    report = scanner(wired, clock=late).run()
    plan = PlanStore(wired).for_session(report.session)[0]
    assert plan.status is PlanStatus.REFUSED
    assert plan.venues == ("kraken", "okx")


def test_two_scans_get_different_session_references(wired: Database) -> None:
    first = scanner(wired).run(counter=0)
    second = scanner(wired).run(counter=1)
    assert first.session != second.session


def test_a_second_market_is_scanned_too(wired: Database) -> None:
    instruments = InstrumentStore(wired)
    inventory = InventoryStore(wired)
    for code in ("kraken", "okx"):
        instruments.add(market(code, "ETH-USD"))
        inventory.put_position(Position.build(code, "ETH", free="500", as_of=AS_OF))
        inventory.put_band(Band.build(code, "ETH", floor="0", target="250", ceiling="10000"))
    books = BookStore(wired)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))
    books.add(book("kraken", "19.00", "20.00", "ETH-USD"))
    books.add(book("okx", "21.00", "22.00", "ETH-USD"))
    report = scanner(wired).run()
    assert report.symbols_considered == 2
    assert report.pairs_priced == 2


def crossing(db: Database) -> None:
    books = BookStore(db)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "101.00", "102.00"))


def flat(db: Database) -> None:
    books = BookStore(db)
    books.add(book("kraken", "99.00", "100.00"))
    books.add(book("okx", "99.00", "100.00"))


@pytest.fixture()
def ledger(wired: Database) -> DecisionStore:
    """The decision ledger for whichever session the test runs."""
    return DecisionStore(wired)


def test_a_scan_with_no_books_still_records_loading_the_symbol(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    report = scanner(wired).run()
    stages = ledger.stage_counts(report.session)
    assert stages["loaded"] == 1
    assert stages["skipped"] == 2


def test_a_pair_that_does_not_cross_is_recorded_as_screened(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    flat(wired)
    report = scanner(wired).run()
    screened = ledger.at_stage(report.session, Stage.SCREENED)
    assert len(screened) == 2
    assert "does not cross" in screened[0].detail


def test_a_priced_pair_is_recorded_as_priced(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    report = scanner(wired).run()
    priced = ledger.at_stage(report.session, Stage.PRICED)
    assert len(priced) == 1
    assert report.session in priced[0].detail


def test_the_other_direction_of_a_crossing_pair_is_screened(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    report = scanner(wired).run()
    assert len(ledger.at_stage(report.session, Stage.SCREENED)) == 1


def test_a_venue_missing_its_volume_is_recorded_as_skipped(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    FeeStore(wired).clear_volume("okx")
    report = scanner(wired).run()
    skipped = ledger.at_stage(report.session, Stage.SKIPPED)
    assert len(skipped) == 1
    assert "okx" in skipped[0].subject


def test_a_venue_missing_a_band_is_recorded_as_skipped(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    InventoryStore(wired).remove_band("okx", "USD")
    report = scanner(wired).run()
    assert len(ledger.at_stage(report.session, Stage.SKIPPED)) == 1


def test_a_stale_pair_is_recorded_as_refused_with_its_clause(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    late = FixedClock(AT + dt.timedelta(seconds=600))
    report = scanner(wired, clock=late).run()
    refused = ledger.at_stage(report.session, Stage.REFUSED)
    assert len(refused) == 1
    assert refused[0].clause == "STALE.01"


def test_the_decisions_are_numbered_from_zero_without_gaps(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    report = scanner(wired).run()
    taken = ledger.for_session(report.session)
    assert [d.sequence for d in taken] == list(range(len(taken)))


def test_every_decision_carries_the_session_start_time(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    report = scanner(wired).run()
    stamps = {d.at for d in ledger.for_session(report.session)}
    assert len(stamps) == 1


def test_the_cheap_stages_outnumber_the_expensive_ones(
    wired: Database,
    ledger: DecisionStore,
) -> None:
    crossing(wired)
    report = scanner(wired).run()
    taken = ledger.for_session(report.session)
    cheap = sum(1 for d in taken if d.stage.costs_nothing)
    assert cheap > len(taken) - cheap
