"""Collapsing one session into the numbers a desk reads."""

from __future__ import annotations

import pytest

from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.report.session_report import compare, summarise
from legvise.store.db import Database
from legvise.store.plans import PlanStore

SESSION = "S20251008.0001"
SYMBOL = parse_symbol("BTC-USD")


def a_leg(venue: str, takes: Side, price: str) -> Leg:
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


def a_plan(index: int, **changes: object) -> Plan:
    fields: dict[str, object] = {
        "ref": f"{SESSION}/P{index:03d}",
        "kind": PlanKind.CROSS_VENUE,
        "symbol": SYMBOL,
        "legs": (a_leg("kraken", Side.ASK, "100"), a_leg("okx", Side.BID, "101")),
        "notional": dec("200"),
        "gross_bps": dec("100"),
        "fee_bps": dec("20"),
        "slippage_bps": dec("0"),
        "rebalance_bps": dec("0"),
        "net_bps": dec("80"),
        "status": PlanStatus.PRICED,
    }
    fields.update(changes)
    return Plan(**fields)  # type: ignore[arg-type]


@pytest.fixture()
def store(db: Database) -> PlanStore:
    handle = PlanStore(db)
    handle.open_session(
        SESSION,
        started_at="2025-10-08T09:00:00+00:00",
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("2"),
    )
    return handle


def test_an_empty_session_summarises_to_nothing(store: PlanStore) -> None:
    found = summarise(store, SESSION)
    assert found.plans == 0
    assert found.hit_rate == dec("0")
    assert found.best_net_bps is None
    assert found.busiest_clause is None


def test_the_session_settings_come_through(store: PlanStore) -> None:
    found = summarise(store, SESSION)
    assert found.min_edge_bps == dec("2")
    assert found.started_at == "2025-10-08T09:00:00+00:00"


def test_a_priced_plan_counts_as_actionable(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    found = summarise(store, SESSION)
    assert found.actionable == 1
    assert found.hit_rate == dec("1")


def test_a_trimmed_plan_is_counted_separately_and_still_actionable(store: PlanStore) -> None:
    store.add(a_plan(0, status=PlanStatus.TRIMMED), session_ref=SESSION)
    found = summarise(store, SESSION)
    assert found.trimmed == 1
    assert found.actionable == 1


def test_a_refused_plan_is_not_actionable(store: PlanStore) -> None:
    store.add(a_plan(0, status=PlanStatus.REFUSED, clause="EDGE.01"), session_ref=SESSION)
    found = summarise(store, SESSION)
    assert found.refused == 1
    assert found.actionable == 0
    assert found.hit_rate == dec("0")


def test_the_clause_lines_carry_the_rule_book_wording(store: PlanStore) -> None:
    store.add(a_plan(0, status=PlanStatus.REFUSED, clause="CAP.01"), session_ref=SESSION)
    line = summarise(store, SESSION).clauses[0]
    assert line.code == "CAP.01"
    assert "notional cap" in line.text


def test_the_busiest_clause_is_the_one_that_fired_most(store: PlanStore) -> None:
    for index, code in enumerate(["EDGE.01", "EDGE.01", "CAP.01"]):
        store.add(a_plan(index, status=PlanStatus.REFUSED, clause=code), session_ref=SESSION)
    busiest = summarise(store, SESSION).busiest_clause
    assert busiest is not None
    assert busiest.code == "EDGE.01"
    assert busiest.hits == 2


def test_the_best_edge_is_taken_from_the_actionable_plans_only(store: PlanStore) -> None:
    store.add(a_plan(0, net_bps=dec("30"), gross_bps=dec("50")), session_ref=SESSION)
    store.add(
        a_plan(1, status=PlanStatus.REFUSED, clause="CAP.03", net_bps=dec("900")),
        session_ref=SESSION,
    )
    assert summarise(store, SESSION).best_net_bps == dec("30")


def test_the_notional_adds_up_across_the_actionable_plans(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    store.add(a_plan(1), session_ref=SESSION)
    assert summarise(store, SESSION).total_notional == dec("400")


def test_the_venues_are_listed_once_each_in_order(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    store.add(a_plan(1), session_ref=SESSION)
    assert summarise(store, SESSION).venues == ("kraken", "okx")


def test_the_markets_a_session_saw_are_listed(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    assert summarise(store, SESSION).symbols == (SYMBOL,)


def test_comparing_two_sessions_reports_the_movement(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    quiet = summarise(store, SESSION)
    store.add(a_plan(1), session_ref=SESSION)
    busy = summarise(store, SESSION)
    moved = compare(quiet, busy)
    assert moved["plans"] == dec("1")
    assert moved["notional"] == dec("200")
    assert moved["hit_rate"] == dec("0")
