"""Session and plan storage, refusals included."""

from __future__ import annotations

import pytest

from legvise.errors import NotFound
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.store.db import Database
from legvise.store.plans import PlanStore

SESSION = "S20250722.0001"
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


def a_plan(index: int = 0, **changes: object) -> Plan:
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
        started_at="2025-07-22T09:00:00+00:00",
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("1"),
    )
    return handle


def test_a_session_survives_a_round_trip(store: PlanStore) -> None:
    read = store.session(SESSION)
    assert read.min_edge_bps == dec("2")
    assert read.pairing_window_ms == 250


def test_a_session_that_is_not_there_is_a_not_found(store: PlanStore) -> None:
    with pytest.raises(NotFound):
        store.session("S19990101.0001")


def test_a_plan_survives_a_round_trip(store: PlanStore) -> None:
    given = a_plan()
    store.add(given, session_ref=SESSION)
    assert store.get(given.ref) == given


def test_the_legs_come_back_in_order(store: PlanStore) -> None:
    store.add(a_plan(), session_ref=SESSION)
    read = store.get(f"{SESSION}/P000")
    assert [leg.venue for leg in read.legs] == ["kraken", "okx"]
    assert read.legs[0].takes is Side.ASK


def test_a_plan_that_is_not_there_is_a_not_found(store: PlanStore) -> None:
    with pytest.raises(NotFound):
        store.get("nowhere")


def test_a_plan_needs_a_session_that_exists(store: PlanStore) -> None:
    with pytest.raises(Exception):  # noqa: B017 - sqlite reports the key generically
        store.add(a_plan(), session_ref="S19990101.0001")


def test_plans_come_back_best_edge_first(store: PlanStore) -> None:
    store.add(a_plan(0, net_bps=dec("30"), gross_bps=dec("50")), session_ref=SESSION)
    store.add(a_plan(1, net_bps=dec("80")), session_ref=SESSION)
    assert [p.ref for p in store.for_session(SESSION)] == [
        f"{SESSION}/P001",
        f"{SESSION}/P000",
    ]


def test_refused_plans_are_kept_alongside_the_others(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    store.add(
        a_plan(1, status=PlanStatus.REFUSED, clause="EDGE.01", net_bps=dec("80")),
        session_ref=SESSION,
    )
    assert len(store.for_session(SESSION)) == 2


def test_only_the_actionable_ones_come_back_when_asked(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    store.add(
        a_plan(1, status=PlanStatus.REFUSED, clause="EDGE.01"),
        session_ref=SESSION,
    )
    store.add(a_plan(2, status=PlanStatus.TRIMMED), session_ref=SESSION)
    assert {p.ref for p in store.actionable(SESSION)} == {
        f"{SESSION}/P000",
        f"{SESSION}/P002",
    }


def test_refusals_can_be_counted_by_clause(store: PlanStore) -> None:
    for index, clause in enumerate(["EDGE.01", "EDGE.01", "DEPTH.02"]):
        store.add(
            a_plan(index, status=PlanStatus.REFUSED, clause=clause),
            session_ref=SESSION,
        )
    assert store.refusal_counts(SESSION) == {"EDGE.01": 2, "DEPTH.02": 1}


def test_counting_across_every_session_is_the_default(store: PlanStore) -> None:
    store.add(a_plan(0, status=PlanStatus.REFUSED, clause="CAP.01"), session_ref=SESSION)
    assert store.refusal_counts() == {"CAP.01": 1}


def test_a_session_with_no_refusals_counts_nothing(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    assert store.refusal_counts(SESSION) == {}


def test_the_markets_a_session_looked_at_are_listed_once_each(store: PlanStore) -> None:
    store.add(a_plan(0), session_ref=SESSION)
    store.add(a_plan(1), session_ref=SESSION)
    assert store.symbols_seen(SESSION) == (SYMBOL,)


def test_sessions_come_back_newest_first(store: PlanStore) -> None:
    store.open_session(
        "S20250723.0001",
        started_at="2025-07-23T09:00:00+00:00",
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("1"),
    )
    assert [s.ref for s in store.sessions()] == ["S20250723.0001", SESSION]


def test_dropping_a_session_takes_its_plans_and_legs(db: Database, store: PlanStore) -> None:
    store.add(a_plan(), session_ref=SESSION)
    db.execute("DELETE FROM scan_session WHERE ref = ?", (SESSION,))
    assert db.scalar("SELECT count(*) FROM plan") == 0
    assert db.scalar("SELECT count(*) FROM plan_leg") == 0
