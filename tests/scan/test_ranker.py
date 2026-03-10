"""Ordering plans by what they make, not by the rate they quote."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.scan.ranker import RankTerms, adjusted_edge, best, rank

SESSION = "S20260310.0001"
SYMBOL = parse_symbol("BTC-USD")


def a_leg(venue: str, takes: Side, levels: int = 1) -> Leg:
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec("100"),
        size=dec("2"),
        fee_bps=dec("10"),
        fee_amount=dec("0.2"),
        levels_swept=levels,
        slippage_bps=dec("0"),
    )


def a_plan(
    index: int,
    *,
    net: str = "10",
    notional: str = "200",
    levels: int = 1,
    status: PlanStatus = PlanStatus.PRICED,
    venues: tuple[str, str] = ("kraken", "okx"),
) -> Plan:
    return Plan(
        ref=f"{SESSION}/P{index:03d}",
        kind=PlanKind.CROSS_VENUE,
        symbol=SYMBOL,
        legs=(a_leg(venues[0], Side.ASK, levels), a_leg(venues[1], Side.BID, levels)),
        notional=dec(notional),
        gross_bps=dec(net) + dec("20"),
        fee_bps=dec("20"),
        slippage_bps=dec("0"),
        rebalance_bps=dec("0"),
        net_bps=dec(net),
        status=status,
        clause="EDGE.01" if status is PlanStatus.REFUSED else None,
    )


def test_a_bigger_plan_at_a_smaller_rate_ranks_first() -> None:
    tight = a_plan(0, net="9", notional="2000")
    wide = a_plan(1, net="4", notional="80000")
    ordered = rank((tight, wide))
    assert ordered[0].plan.ref == wide.ref


def test_the_expected_amount_is_the_edge_against_the_notional() -> None:
    ordered = rank((a_plan(0, net="100", notional="10000"),))
    assert ordered[0].expected_amount == dec("100")


def test_a_refused_plan_is_not_ranked() -> None:
    ordered = rank((a_plan(0, status=PlanStatus.REFUSED),))
    assert ordered == ()


def test_a_trimmed_plan_is_still_ranked() -> None:
    ordered = rank((a_plan(0, status=PlanStatus.TRIMMED),))
    assert len(ordered) == 1


def test_taking_only_the_touch_costs_no_penalty() -> None:
    terms = RankTerms(depth_penalty_bps=dec("1"))
    shallow = a_plan(0, net="10", levels=1)
    assert adjusted_edge(shallow, terms) == dec("10")


def test_sweeping_past_the_touch_costs_the_penalty_per_level() -> None:
    terms = RankTerms(depth_penalty_bps=dec("1"))
    deep = a_plan(0, net="10", levels=4)
    assert adjusted_edge(deep, terms) == dec("4")


def test_the_penalty_is_reported_on_the_ranked_line() -> None:
    terms = RankTerms(depth_penalty_bps=dec("1"))
    ordered = rank((a_plan(0, net="10", levels=4),), terms)
    assert ordered[0].penalty_bps == dec("6")
    assert ordered[0].levels_swept == 8


def test_a_deep_plan_can_lose_to_a_shallow_one_at_the_same_edge() -> None:
    terms = RankTerms(depth_penalty_bps=dec("1"))
    shallow = a_plan(0, net="10", levels=1)
    deep = a_plan(1, net="10", levels=5)
    assert rank((deep, shallow), terms)[0].plan.ref == shallow.ref


def test_a_negative_penalty_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        RankTerms(depth_penalty_bps=dec("-1"))
    assert caught.value.field == "depth_penalty_bps"


def test_a_venue_weight_of_zero_is_refused() -> None:
    with pytest.raises(BadArgument):
        RankTerms(venue_weights={"kraken": dec("0")})


def test_a_venue_nobody_weighted_counts_as_neutral() -> None:
    assert RankTerms().weight_for("kraken") == dec("1")


def test_a_distrusted_venue_pushes_its_plans_down() -> None:
    terms = RankTerms(venue_weights={"okx": dec("0.5")})
    trusted = a_plan(0, net="10", venues=("kraken", "bitstamp"))
    doubted = a_plan(1, net="10", venues=("kraken", "okx"))
    assert rank((doubted, trusted), terms)[0].plan.ref == trusted.ref


def test_two_identical_plans_keep_a_stable_order() -> None:
    first = a_plan(0)
    second = a_plan(1)
    assert [item.plan.ref for item in rank((second, first))] == [first.ref, second.ref]


def test_the_best_plan_is_the_top_of_the_ranking() -> None:
    tight = a_plan(0, net="9", notional="2000")
    wide = a_plan(1, net="4", notional="80000")
    top = best((tight, wide))
    assert top is not None
    assert top.plan.ref == wide.ref


def test_a_session_with_nothing_sendable_has_no_best_plan() -> None:
    assert best((a_plan(0, status=PlanStatus.REFUSED),)) is None
