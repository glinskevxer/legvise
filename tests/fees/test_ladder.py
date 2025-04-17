"""Resolving a trailing volume onto a rung of the ladder."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.fees.ladder import (
    effective_bps,
    leg_is_passive,
    resolve,
    rung_index,
    taker_bps_at,
)
from legvise.model.book import Side
from legvise.model.fee import FeeLadder
from legvise.money import dec

LADDER = FeeLadder.build(
    "kraken",
    (
        ("0", "10", "16"),
        ("1000000", "6", "10"),
        ("25000000", "0", "6"),
        ("100000000", "-2", "4"),
    ),
)


def test_no_volume_stands_on_the_base_rung() -> None:
    assert rung_index(LADDER, dec("0")) == 0
    assert resolve(LADDER, dec("0")).taker_bps == 16


def test_volume_below_the_next_threshold_stays_put() -> None:
    assert rung_index(LADDER, dec("999999.99")) == 0


def test_volume_exactly_on_a_threshold_reaches_it() -> None:
    assert rung_index(LADDER, dec("1000000")) == 1
    assert resolve(LADDER, dec("1000000")).taker_bps == 10


def test_volume_past_several_thresholds_takes_the_highest_reached() -> None:
    assert rung_index(LADDER, dec("30000000")) == 2


def test_volume_beyond_the_top_rung_stops_at_the_top() -> None:
    assert rung_index(LADDER, dec("9999999999")) == 3
    assert resolve(LADDER, dec("9999999999")).is_rebate


def test_negative_volume_is_refused() -> None:
    with pytest.raises(BadArgument):
        rung_index(LADDER, dec("-1"))


def test_an_unrecorded_volume_is_refused_rather_than_read_as_zero() -> None:
    with pytest.raises(Refused) as caught:
        resolve(LADDER, None)
    assert caught.value.why.startswith("FEE.01")


def test_the_taker_rate_is_readable_without_the_tier() -> None:
    assert taker_bps_at(LADDER, dec("2000000")) == 10


def test_an_aggressive_leg_pays_the_taker_rate() -> None:
    tier = resolve(LADDER, dec("0"))
    assert effective_bps(tier, False, venue_pays_rebate=False) == 16


def test_a_resting_leg_pays_the_maker_rate() -> None:
    tier = resolve(LADDER, dec("0"))
    assert effective_bps(tier, True, venue_pays_rebate=False) == 10


def test_a_rebate_is_credited_where_the_venue_pays_one() -> None:
    tier = resolve(LADDER, dec("100000000"))
    assert effective_bps(tier, True, venue_pays_rebate=True) == -2


def test_a_rebate_the_venue_does_not_pay_the_desk_is_refused() -> None:
    tier = resolve(LADDER, dec("100000000"))
    with pytest.raises(Refused) as caught:
        effective_bps(tier, True, venue_pays_rebate=False)
    assert caught.value.why.startswith("FEE.02")


def test_a_venue_that_pays_rebates_changes_nothing_on_a_positive_rung() -> None:
    tier = resolve(LADDER, dec("0"))
    assert effective_bps(tier, True, venue_pays_rebate=True) == 10


def test_a_resting_leg_is_passive_on_either_side() -> None:
    assert leg_is_passive(Side.BID, True)
    assert leg_is_passive(Side.ASK, True)
    assert not leg_is_passive(Side.ASK, False)


def test_a_single_rung_ladder_always_resolves_to_it() -> None:
    flat = FeeLadder.build("bitstamp", (("0", "20", "30"),))
    assert rung_index(flat, dec("500000000")) == 0
