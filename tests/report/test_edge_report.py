"""Aggregating expected against realised, weighted by notional."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.fill import Fill
from legvise.model.plan import Leg, Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.report.edge_report import build_edge_report
from legvise.store.db import Database
from legvise.store.fills import FillStore
from legvise.store.plans import PlanStore

SESSION = "S20251014.0001"
SYMBOL = parse_symbol("BTC-USD")
AT = "2025-10-14T09:00:01+00:00"


def a_leg(venue: str, takes: Side, price: str, size: str) -> Leg:
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec(price),
        size=dec(size),
        fee_bps=dec("10"),
        fee_amount=dec("0"),
        levels_swept=1,
        slippage_bps=dec("0"),
    )


def a_plan(index: int, size: str = "2", net: str = "80") -> Plan:
    notional = dec("100") * dec(size)
    return Plan(
        ref=f"{SESSION}/P{index:03d}",
        kind=PlanKind.CROSS_VENUE,
        symbol=SYMBOL,
        legs=(a_leg("kraken", Side.ASK, "100", size), a_leg("okx", Side.BID, "101", size)),
        notional=notional,
        gross_bps=dec(net) + dec("20"),
        fee_bps=dec("20"),
        slippage_bps=dec("0"),
        rebalance_bps=dec("0"),
        net_bps=dec(net),
        status=PlanStatus.PRICED,
    )


@pytest.fixture()
def stores(db: Database) -> tuple[PlanStore, FillStore]:
    plans = PlanStore(db)
    plans.open_session(
        SESSION,
        started_at="2025-10-14T09:00:00+00:00",
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("2"),
    )
    return (plans, FillStore(db))


def fill_both(fills: FillStore, plan: Plan, buy_price: str, sell_price: str, tag: str) -> None:
    for index, (venue, takes, price) in enumerate(
        (("kraken", Side.ASK, buy_price), ("okx", Side.BID, sell_price))
    ):
        fills.add(
            Fill.build(
                plan.ref,
                index,
                venue,
                takes,
                price=price,
                size=str(plan.legs[index].size),
                filled_at=AT,
            ),
            venue_trade_id=f"{tag}{index}",
        )


def test_a_report_with_nothing_filled_is_empty(stores: tuple[PlanStore, FillStore]) -> None:
    plans, fills = stores
    plans.add(a_plan(0), session_ref=SESSION)
    report = build_edge_report(plans, fills, session_ref=SESSION)
    assert report.plans == 0
    assert report.expected_bps == dec("0")


def test_a_filled_plan_appears_in_the_report(stores: tuple[PlanStore, FillStore]) -> None:
    plans, fills = stores
    plan = plans.add(a_plan(0), session_ref=SESSION)
    fill_both(fills, plan, "100", "101", "a")
    report = build_edge_report(plans, fills, session_ref=SESSION)
    assert report.plans == 1
    assert report.expected_bps == dec("80")
    assert report.realised_bps == dec("80")
    assert report.gap_bps == dec("0")


def test_price_drift_shows_up_in_the_aggregate(stores: tuple[PlanStore, FillStore]) -> None:
    plans, fills = stores
    plan = plans.add(a_plan(0), session_ref=SESSION)
    fill_both(fills, plan, "101", "101", "a")
    report = build_edge_report(plans, fills, session_ref=SESSION)
    assert report.price_drift_bps == dec("100")
    assert report.gap_bps == dec("100")


def test_the_average_is_weighted_by_notional(stores: tuple[PlanStore, FillStore]) -> None:
    plans, fills = stores
    small = plans.add(a_plan(0, size="1"), session_ref=SESSION)
    large = plans.add(a_plan(1, size="99"), session_ref=SESSION)
    fill_both(fills, small, "110", "101", "a")
    fill_both(fills, large, "100", "101", "b")
    report = build_edge_report(plans, fills, session_ref=SESSION)
    assert report.price_drift_bps < dec("20")


def test_an_unweighted_average_would_have_said_something_else(
    stores: tuple[PlanStore, FillStore],
) -> None:
    plans, fills = stores
    small = plans.add(a_plan(0, size="1"), session_ref=SESSION)
    large = plans.add(a_plan(1, size="99"), session_ref=SESSION)
    fill_both(fills, small, "110", "101", "a")
    fill_both(fills, large, "100", "101", "b")
    report = build_edge_report(plans, fills, session_ref=SESSION)
    plain = sum(line.attribution.price_drift_bps for line in report.lines) / 2
    assert report.price_drift_bps != plain


def test_the_realised_amount_is_in_the_quote_asset(
    stores: tuple[PlanStore, FillStore],
) -> None:
    plans, fills = stores
    plan = plans.add(a_plan(0), session_ref=SESSION)
    fill_both(fills, plan, "100", "101", "a")
    report = build_edge_report(plans, fills, session_ref=SESSION)
    assert report.realised_amount == dec("200") * dec("80") / dec("10000")


def test_a_one_sided_plan_is_flagged(stores: tuple[PlanStore, FillStore]) -> None:
    plans, fills = stores
    plan = plans.add(a_plan(0), session_ref=SESSION)
    fills.add(
        Fill.build(plan.ref, 0, "kraken", Side.ASK, price="100", size="2", filled_at=AT),
        venue_trade_id="a0",
    )
    report = build_edge_report(plans, fills, session_ref=SESSION)
    assert report.leg_risk_plans == (plan.ref,)


def test_the_report_can_be_built_across_every_session(
    stores: tuple[PlanStore, FillStore],
) -> None:
    plans, fills = stores
    plan = plans.add(a_plan(0), session_ref=SESSION)
    fill_both(fills, plan, "100", "101", "a")
    assert build_edge_report(plans, fills).plans == 1


def test_a_limit_of_nothing_is_refused(stores: tuple[PlanStore, FillStore]) -> None:
    plans, fills = stores
    with pytest.raises(BadArgument):
        build_edge_report(plans, fills, limit=0)


def test_the_total_notional_covers_only_the_filled_plans(
    stores: tuple[PlanStore, FillStore],
) -> None:
    plans, fills = stores
    plan = plans.add(a_plan(0), session_ref=SESSION)
    plans.add(a_plan(1), session_ref=SESSION)
    fill_both(fills, plan, "100", "101", "a")
    assert build_edge_report(plans, fills, session_ref=SESSION).total_notional == dec("200")
