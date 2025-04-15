"""Fee tiers and the shape a ladder has to have."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.model.fee import FeeLadder, FeeTier

RUNGS = (
    ("0", "10", "16"),
    ("1000000", "6", "10"),
    ("25000000", "0", "6"),
    ("100000000", "-2", "4"),
)


def test_a_tier_carries_both_rates() -> None:
    tier = FeeTier.build("0", "10", "16")
    assert tier.maker_bps == 10
    assert tier.taker_bps == 16
    assert not tier.is_rebate


def test_a_negative_maker_rate_reads_as_a_rebate() -> None:
    assert FeeTier.build("0", "-2", "5").is_rebate


def test_a_negative_volume_threshold_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        FeeTier.build("-1", "10", "16")
    assert caught.value.field == "min_volume_30d"


def test_a_negative_taker_rate_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        FeeTier.build("0", "0", "-1")
    assert "nobody is paid to take" in caught.value.why


def test_a_rebate_deeper_than_the_taker_fee_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        FeeTier.build("0", "-6", "5")
    assert caught.value.field == "maker_bps"


def test_a_rebate_exactly_matching_the_taker_fee_is_allowed() -> None:
    assert FeeTier.build("0", "-5", "5").is_rebate


def test_a_ladder_keeps_its_rungs_in_order() -> None:
    ladder = FeeLadder.build("kraken", RUNGS)
    assert ladder.depth() == 4
    assert ladder.base.taker_bps == 16
    assert ladder.best.maker_bps == -2


def test_a_ladder_needs_at_least_one_rung() -> None:
    with pytest.raises(BadArgument) as caught:
        FeeLadder.build("kraken", ())
    assert caught.value.field == "tiers"


def test_a_ladder_has_to_start_at_zero_volume() -> None:
    with pytest.raises(BadArgument) as caught:
        FeeLadder.build("kraken", (("1000", "10", "16"),))
    assert "start at zero" in caught.value.why


def test_rungs_out_of_order_are_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        FeeLadder.build("kraken", (("0", "10", "16"), ("100", "6", "10"), ("50", "4", "8")))
    assert "rungs go up" in caught.value.why


def test_two_rungs_at_the_same_threshold_are_refused() -> None:
    with pytest.raises(BadArgument):
        FeeLadder.build("kraken", (("0", "10", "16"), ("0", "6", "10")))


def test_a_venue_code_is_normalised_on_the_way_in() -> None:
    assert FeeLadder.build(" Kraken ", RUNGS).venue == "kraken"


def test_a_ladder_is_immutable() -> None:
    ladder = FeeLadder.build("kraken", RUNGS)
    with pytest.raises(AttributeError):
        ladder.tiers = ()  # type: ignore[misc]


def test_a_single_rung_ladder_is_its_own_base_and_best() -> None:
    ladder = FeeLadder.build("bitstamp", (("0", "20", "30"),))
    assert ladder.base == ladder.best
    assert ladder.depth() == 1
