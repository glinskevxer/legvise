"""What a sweep takes, and the two things it is never allowed to take."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.model.book import Book, Side
from legvise.model.fill import Fill
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.fills import FillStore
from legvise.store.plans import PlanStore
from legvise.store.retention import Retention, Sweep
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

AT = dt.datetime(2025, 6, 2, 9, 0, tzinfo=dt.UTC)
LATER = AT + dt.timedelta(days=30)
SYMBOL = parse_symbol("BTC-USD")


@pytest.fixture()
def wired(db: Database) -> Database:
    """A book of record with two venues on it and nothing else."""
    venues = VenueStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code))
    return db


@pytest.fixture()
def policy(wired: Database) -> Retention:
    """The retention policy, pointed at a wired book."""
    return Retention(wired)


def a_book(venue: str = "kraken", symbol: str = "BTC-USD", *, days: int = 0) -> Book:
    """One snapshot, stamped a whole number of days after the start."""
    return Book.build(
        venue,
        symbol,
        observed_at=AT + dt.timedelta(days=days),
        bids=(("99", "1"),),
        asks=(("100", "1"),),
        sequence=days,
    )


def a_session(db: Database, ref: str, *, days: int) -> str:
    """One scan session, stamped a whole number of days after the start."""
    PlanStore(db).open_session(
        ref,
        started_at=(AT + dt.timedelta(days=days)).isoformat(),
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("1"),
    )
    return ref


def a_leg(venue: str, takes: Side, price: str) -> Leg:
    """One side of a plan, priced flat."""
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec(price),
        size=dec("2"),
        fee_bps=dec("10"),
        fee_amount=dec("0.2"),
        levels_swept=1,
        slippage_bps=dec("0"),
    )


def a_plan(ref: str) -> Plan:
    """A priced cross venue plan, whatever session it is written under."""
    return Plan(
        ref=ref,
        kind=PlanKind.CROSS_VENUE,
        symbol=SYMBOL,
        legs=(a_leg("kraken", Side.ASK, "100"), a_leg("okx", Side.BID, "101")),
        notional=dec("200"),
        gross_bps=dec("100"),
        fee_bps=dec("20"),
        slippage_bps=dec("0"),
        rebalance_bps=dec("0"),
        net_bps=dec("80"),
        status=PlanStatus.PRICED,
    )


def trade(db: Database, ref: str, session: str) -> None:
    """Write a plan and a fill against its first leg."""
    PlanStore(db).add(a_plan(ref), session_ref=session)
    fill = Fill.build(
        ref,
        0,
        "kraken",
        Side.ASK,
        price="100",
        size="2",
        filled_at=(AT + dt.timedelta(minutes=1)).isoformat(),
    )
    FillStore(db).add(fill, venue_trade_id=f"{ref}-t1")


def test_a_cutoff_counts_back_from_the_clock(policy: Retention) -> None:
    assert policy.cutoff_from(LATER, 7) == LATER - dt.timedelta(days=7)


def test_a_cutoff_of_no_days_at_all_is_refused(policy: Retention) -> None:
    with pytest.raises(BadArgument):
        policy.cutoff_from(LATER, 0)


def test_a_negative_number_of_days_is_refused(policy: Retention) -> None:
    with pytest.raises(BadArgument) as caught:
        policy.cutoff_from(LATER, -3)
    assert "at least a day" in caught.value.why


def test_an_empty_book_has_nothing_to_sweep(policy: Retention) -> None:
    found = policy.survey(LATER)
    assert found.is_empty
    assert found.rows == 0


def test_an_old_snapshot_goes_when_a_newer_one_exists(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=0))
    store.add(a_book(days=1))
    assert policy.droppable_snapshots(LATER) == 1


def test_the_only_snapshot_of_a_market_is_never_dropped(wired: Database, policy: Retention) -> None:
    BookStore(wired).add(a_book(days=0))
    assert policy.droppable_snapshots(LATER) == 0
    assert policy.held_markets(LATER) == 1


def test_each_market_keeps_its_own_newest_snapshot(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    for venue in ("kraken", "okx"):
        for day in (0, 1, 2):
            store.add(a_book(venue, days=day))
    assert policy.droppable_snapshots(LATER) == 4
    assert policy.held_markets(LATER) == 2


def test_two_symbols_on_one_venue_keep_one_each(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    for symbol in ("BTC-USD", "ETH-USD"):
        store.add(a_book("kraken", symbol, days=0))
        store.add(a_book("kraken", symbol, days=1))
    assert policy.held_markets(LATER) == 2
    assert policy.droppable_snapshots(LATER) == 2


def test_a_cutoff_before_everything_drops_nothing(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=0))
    store.add(a_book(days=1))
    assert policy.droppable_snapshots(AT - dt.timedelta(hours=12)) == 0
    assert store.count() == 2


def test_a_cutoff_between_two_snapshots_drops_the_older(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=0))
    store.add(a_book(days=1))
    store.add(a_book(days=2))
    assert policy.droppable_snapshots(AT + dt.timedelta(hours=36)) == 2


def test_a_sweep_leaves_the_market_readable(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=0))
    store.add(a_book(days=1))
    policy.sweep(LATER)
    assert store.latest("kraken", "BTC-USD") is not None
    assert store.count() == 1


def test_a_sweep_takes_the_levels_with_the_snapshot(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=0))
    store.add(a_book(days=1))
    policy.sweep(LATER)
    assert wired.scalar("SELECT count(*) FROM book_level") == 2


def test_the_kept_snapshot_is_the_one_observed_last(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=5))
    store.add(a_book(days=1))
    policy.sweep(LATER)
    kept = store.latest("kraken", "BTC-USD")
    assert kept is not None
    assert kept.observed_at == AT + dt.timedelta(days=5)


def test_an_old_session_with_no_fill_is_droppable(wired: Database, policy: Retention) -> None:
    a_session(wired, "S20250602.0001", days=0)
    assert policy.droppable_sessions(LATER) == ("S20250602.0001",)


def test_a_session_newer_than_the_cutoff_stays(wired: Database, policy: Retention) -> None:
    a_session(wired, "S20250602.0001", days=0)
    assert policy.droppable_sessions(AT - dt.timedelta(days=1)) == ()


def test_a_sweep_takes_the_plans_of_a_dropped_session(wired: Database, policy: Retention) -> None:
    session = a_session(wired, "S20250602.0001", days=0)
    PlanStore(wired).add(a_plan(f"{session}/P000"), session_ref=session)
    found = policy.sweep(LATER)
    assert found.sessions == 1
    assert found.plans == 1
    assert wired.scalar("SELECT count(*) FROM plan") == 0


def test_a_traded_session_survives_any_cutoff(wired: Database, policy: Retention) -> None:
    session = a_session(wired, "S20250602.0001", days=0)
    trade(wired, f"{session}/P000", session)
    assert policy.droppable_sessions(LATER) == ()
    assert policy.held_sessions(LATER) == 1


def test_a_sweep_never_removes_a_fill(wired: Database, policy: Retention) -> None:
    session = a_session(wired, "S20250602.0001", days=0)
    trade(wired, f"{session}/P000", session)
    policy.sweep(LATER)
    assert wired.scalar("SELECT count(*) FROM fill") == 1
    assert wired.scalar("SELECT count(*) FROM plan") == 1


def test_one_traded_session_does_not_save_another(wired: Database, policy: Retention) -> None:
    traded = a_session(wired, "S20250602.0001", days=0)
    a_session(wired, "S20250602.0002", days=0)
    trade(wired, f"{traded}/P000", traded)
    assert policy.droppable_sessions(LATER) == ("S20250602.0002",)


def test_a_survey_removes_nothing_at_all(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=0))
    store.add(a_book(days=1))
    a_session(wired, "S20250602.0001", days=0)
    found = policy.survey(LATER)
    assert found.snapshots == 1
    assert found.sessions == 1
    assert store.count() == 2
    assert wired.scalar("SELECT count(*) FROM scan_session") == 1


def test_a_survey_and_a_sweep_agree_on_the_count(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    for day in (0, 1, 2):
        store.add(a_book(days=day))
    a_session(wired, "S20250602.0001", days=0)
    assert policy.survey(LATER) == policy.sweep(LATER)


def test_a_second_sweep_finds_nothing_left(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    store.add(a_book(days=0))
    store.add(a_book(days=1))
    policy.sweep(LATER)
    assert policy.sweep(LATER).is_empty


def test_a_sweep_counts_the_rows_it_took(wired: Database, policy: Retention) -> None:
    store = BookStore(wired)
    for day in (0, 1, 2):
        store.add(a_book(days=day))
    session = a_session(wired, "S20250602.0001", days=0)
    PlanStore(wired).add(a_plan(f"{session}/P000"), session_ref=session)
    found = policy.sweep(LATER)
    assert found.rows == found.snapshots + found.sessions + found.plans + found.decisions
    assert found.rows == 4


def test_a_sweep_reports_a_line_for_every_table() -> None:
    found = Sweep(snapshots=3, sessions=1, plans=2, decisions=9, held_markets=1, held_sessions=0)
    lines = found.lines()
    assert lines[0] == "snapshots  3"
    assert lines[-1] == "held       1 markets, 0 traded sessions"


def test_a_sweep_that_took_nothing_says_so() -> None:
    assert Sweep(0, 0, 0, 0, 0, 0).is_empty


def test_a_sweep_holding_things_back_is_still_empty() -> None:
    assert Sweep(0, 0, 0, 0, held_markets=4, held_sessions=2).is_empty
