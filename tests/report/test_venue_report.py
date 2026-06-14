"""Which venues are earning their place."""

from __future__ import annotations

import pytest

from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.report.venue_report import build_venue_report
from legvise.store.db import Database
from legvise.store.plans import PlanStore

SESSION = "S20260618.0001"
SYMBOL = parse_symbol("BTC-USD")


def a_leg(venue: str, takes: Side) -> Leg:
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec("100"),
        size=dec("2"),
        fee_bps=dec("10"),
        fee_amount=dec("0.2"),
        levels_swept=1,
        slippage_bps=dec("0"),
    )


def a_plan(
    index: int,
    *,
    venues: tuple[str, str] = ("kraken", "okx"),
    status: PlanStatus = PlanStatus.PRICED,
    clause: str | None = None,
    notional: str = "200",
) -> Plan:
    return Plan(
        ref=f"{SESSION}/P{index:03d}",
        kind=PlanKind.CROSS_VENUE,
        symbol=SYMBOL,
        legs=(a_leg(venues[0], Side.ASK), a_leg(venues[1], Side.BID)),
        notional=dec(notional),
        gross_bps=dec("100"),
        fee_bps=dec("20"),
        slippage_bps=dec("0"),
        rebalance_bps=dec("0"),
        net_bps=dec("80"),
        status=status,
        clause=clause,
    )


@pytest.fixture()
def store(db: Database) -> PlanStore:
    handle = PlanStore(db)
    handle.open_session(
        SESSION,
        started_at="2026-06-18T09:00:00+00:00",
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("2"),
    )
    return handle


def test_a_desk_with_no_plans_has_no_venue_lines(store: PlanStore) -> None:
    report = build_venue_report(store)
    assert report.lines == ()
    assert report.busiest is None


def test_every_venue_on_a_plan_gets_a_line(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    report = build_venue_report(store)
    assert {line.venue for line in report.lines} == {"kraken", "okx"}


def test_a_sendable_plan_counts_toward_both_venues(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    report = build_venue_report(store)
    assert all(line.actionable == 1 for line in report.lines)


def test_a_refused_plan_counts_as_refused_not_sendable(store: PlanStore) -> None:
    store.add(a_plan(0, status=PlanStatus.REFUSED, clause="EDGE.01"), session_ref=SESSION)
    line = build_venue_report(store).line_for("kraken")
    assert line is not None
    assert line.refused == 1
    assert line.actionable == 0


def test_only_the_sendable_notional_is_counted(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    store.add(
        a_plan(1, status=PlanStatus.REFUSED, clause="EDGE.01", notional="9999"),
        session_ref=SESSION,
    )
    line = build_venue_report(store).line_for("kraken")
    assert line is not None
    assert line.notional == dec("200")


def test_the_hit_rate_is_sendable_over_seen(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    store.add(a_plan(1, status=PlanStatus.REFUSED, clause="EDGE.01"), session_ref=SESSION)
    line = build_venue_report(store).line_for("kraken")
    assert line is not None
    assert line.hit_rate == dec("0.5")


def test_the_worst_clause_is_the_one_that_fired_most(store: PlanStore) -> None:
    for index, clause in enumerate(["EDGE.01", "EDGE.01", "DEPTH.02"]):
        store.add(a_plan(index, status=PlanStatus.REFUSED, clause=clause), session_ref=SESSION)
    line = build_venue_report(store).line_for("kraken")
    assert line is not None
    assert line.worst_clause == "EDGE.01"


def test_a_venue_nothing_refused_has_no_worst_clause(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    line = build_venue_report(store).line_for("kraken")
    assert line is not None
    assert line.worst_clause is None


def test_a_venue_that_never_reached_a_sendable_plan_is_idle(store: PlanStore) -> None:
    store.add(
        a_plan(0, venues=("kraken", "bitstamp"), status=PlanStatus.REFUSED, clause="EDGE.01"),
        session_ref=SESSION,
    )
    assert set(build_venue_report(store).idle) == {"kraken", "bitstamp"}


def test_the_busiest_venue_is_the_one_carrying_the_most(store: PlanStore) -> None:
    store.add(a_plan(0, venues=("kraken", "okx")), session_ref=SESSION)
    store.add(a_plan(1, venues=("kraken", "bitstamp"), notional="5000"), session_ref=SESSION)
    busiest = build_venue_report(store).busiest
    assert busiest is not None
    assert busiest.venue == "kraken"


def test_a_venue_that_never_appeared_has_no_line(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    assert build_venue_report(store).line_for("bitstamp") is None
