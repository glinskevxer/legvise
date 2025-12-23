"""Fill storage and the leg results it collapses into."""

from __future__ import annotations

import pytest

from legvise.errors import Conflict, NotFound
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.fill import Fill, LegOutcome
from legvise.model.plan import Leg, Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.store.db import Database
from legvise.store.fills import FillStore
from legvise.store.plans import PlanStore

SESSION = "S20250917.0001"
REF = f"{SESSION}/P000"
SYMBOL = parse_symbol("BTC-USD")


def a_leg(venue: str, takes: Side, price: str, size: str = "2") -> Leg:
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec(price),
        size=dec(size),
        fee_bps=dec("10"),
        fee_amount=dec("0.2"),
        levels_swept=1,
        slippage_bps=dec("0"),
    )


def a_plan() -> Plan:
    return Plan(
        ref=REF,
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


def a_fill(leg: int, price: str, size: str, at: str = "2025-09-17T09:00:01+00:00") -> Fill:
    venue = "kraken" if leg == 0 else "okx"
    takes = Side.ASK if leg == 0 else Side.BID
    return Fill.build(REF, leg, venue, takes, price=price, size=size, filled_at=at)


@pytest.fixture()
def store(db: Database) -> FillStore:
    plans = PlanStore(db)
    plans.open_session(
        SESSION,
        started_at="2025-09-17T09:00:00+00:00",
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("2"),
    )
    plans.add(a_plan(), session_ref=SESSION)
    return FillStore(db)


def test_a_fill_survives_a_round_trip(store: FillStore) -> None:
    given = a_fill(0, "100", "2")
    store.add(given, venue_trade_id="t1")
    assert store.for_plan(REF) == (given,)


def test_the_same_venue_trade_id_twice_is_a_conflict(store: FillStore) -> None:
    store.add(a_fill(0, "100", "1"), venue_trade_id="t1")
    with pytest.raises(Conflict):
        store.add(a_fill(0, "100", "1"), venue_trade_id="t1")


def test_the_same_trade_id_on_two_venues_is_accepted(store: FillStore) -> None:
    store.add(a_fill(0, "100", "1"), venue_trade_id="t1")
    store.add(a_fill(1, "101", "1"), venue_trade_id="t1")
    assert len(store.for_plan(REF)) == 2


def test_a_fill_against_a_plan_that_does_not_exist_is_refused(store: FillStore) -> None:
    stray = Fill.build(
        "S19990101.0001/P000",
        0,
        "kraken",
        Side.ASK,
        price="100",
        size="1",
        filled_at="2025-09-17T09:00:01+00:00",
    )
    with pytest.raises(Exception):  # noqa: B017 - sqlite reports the key generically
        store.add(stray, venue_trade_id="t9")


def test_fills_come_back_in_leg_then_time_order(store: FillStore) -> None:
    store.add(a_fill(1, "101", "1", "2025-09-17T09:00:02+00:00"), venue_trade_id="b1")
    store.add(a_fill(0, "100", "1", "2025-09-17T09:00:03+00:00"), venue_trade_id="a2")
    store.add(a_fill(0, "100", "1", "2025-09-17T09:00:01+00:00"), venue_trade_id="a1")
    order = [(f.leg_index, f.filled_at) for f in store.for_plan(REF)]
    assert order == [
        (0, "2025-09-17T09:00:01+00:00"),
        (0, "2025-09-17T09:00:03+00:00"),
        (1, "2025-09-17T09:00:02+00:00"),
    ]


def test_one_leg_can_be_read_on_its_own(store: FillStore) -> None:
    store.add(a_fill(0, "100", "1"), venue_trade_id="a1")
    store.add(a_fill(1, "101", "1"), venue_trade_id="b1")
    assert len(store.for_leg(REF, 1)) == 1


def test_a_plan_with_no_fills_has_two_missed_legs(store: FillStore) -> None:
    results = store.results_for(a_plan())
    assert [r.outcome for r in results] == [LegOutcome.MISSED, LegOutcome.MISSED]


def test_a_fully_filled_plan_reads_as_filled_on_both_legs(store: FillStore) -> None:
    store.add(a_fill(0, "100", "2"), venue_trade_id="a1")
    store.add(a_fill(1, "101", "2"), venue_trade_id="b1")
    results = store.results_for(a_plan())
    assert [r.outcome for r in results] == [LegOutcome.FILLED, LegOutcome.FILLED]


def test_one_leg_can_miss_while_the_other_fills(store: FillStore) -> None:
    store.add(a_fill(0, "100", "2"), venue_trade_id="a1")
    results = store.results_for(a_plan())
    assert results[0].outcome is LegOutcome.FILLED
    assert results[1].outcome is LegOutcome.MISSED


def test_several_fills_on_one_leg_average_out(store: FillStore) -> None:
    store.add(a_fill(0, "100", "1"), venue_trade_id="a1")
    store.add(a_fill(0, "102", "1"), venue_trade_id="a2")
    result = store.results_for(a_plan())[0]
    assert result.realised_price == dec("101")
    assert result.outcome is LegOutcome.FILLED


def test_a_partial_leg_reports_its_ratio(store: FillStore) -> None:
    store.add(a_fill(0, "100", "1"), venue_trade_id="a1")
    assert store.results_for(a_plan())[0].fill_ratio == dec("0.5")


def test_the_expected_price_comes_from_the_plan(store: FillStore) -> None:
    assert store.results_for(a_plan())[1].expected_price == dec("101")


def test_plans_with_fills_are_listed_newest_first(store: FillStore) -> None:
    store.add(a_fill(0, "100", "1"), venue_trade_id="a1")
    assert store.plans_with_fills() == (REF,)


def test_requiring_fills_on_a_plan_with_none_is_a_not_found(store: FillStore) -> None:
    with pytest.raises(NotFound):
        store.require_any(REF)


def test_dropping_a_plan_takes_its_fills(db: Database, store: FillStore) -> None:
    store.add(a_fill(0, "100", "1"), venue_trade_id="a1")
    db.execute("DELETE FROM plan WHERE ref = ?", (REF,))
    assert store.count() == 0
