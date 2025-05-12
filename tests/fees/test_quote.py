"""Pricing a leg's fee, and the two rounding directions that keep it honest."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.fees.quote import FeeCharge, FeeContext, charge_for, round_trip_bps
from legvise.model.fee import FeeTier
from legvise.money import dec

FLAT = FeeTier.build("0", "10", "16")
REBATING = FeeTier.build("0", "-2", "5")


def context(**changes: object) -> FeeContext:
    fields: dict[str, object] = {
        "venue": "kraken",
        "tier": FLAT,
        "pays_maker_rebate": False,
    }
    fields.update(changes)
    return FeeContext(**fields)  # type: ignore[arg-type]


def test_a_taking_leg_pays_the_taker_rate() -> None:
    charge = charge_for(context(), dec("10000"), resting=False)
    assert charge.rate_bps == 16
    assert charge.quote_amount == dec("16")
    assert not charge.is_rebate


def test_a_resting_leg_pays_the_maker_rate() -> None:
    charge = charge_for(context(), dec("10000"), resting=True)
    assert charge.quote_amount == dec("10")


def test_a_fee_owed_rounds_up_to_the_smallest_unit() -> None:
    # 16 bps of this notional is exactly 0.000000015, half a unit past the grid.
    charge = charge_for(context(), dec("0.000009375"), resting=False)
    assert charge.quote_amount == dec("0.00000002")


def test_a_rebate_earned_rounds_down() -> None:
    # 2 bps of this notional is the same 0.000000015, and it rounds the other way.
    charge = charge_for(
        context(tier=REBATING, pays_maker_rebate=True), dec("0.000075"), resting=True
    )
    assert charge.is_rebate
    assert charge.quote_amount == dec("0.00000001")


def test_a_rebate_reads_as_negative_when_signed() -> None:
    charge = charge_for(context(tier=REBATING, pays_maker_rebate=True), dec("10000"), resting=True)
    assert charge.signed_quote_amount == dec("-2")


def test_a_fee_reads_as_positive_when_signed() -> None:
    charge = charge_for(context(), dec("10000"), resting=False)
    assert charge.signed_quote_amount == dec("16")


def test_a_rebate_the_venue_does_not_pay_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        charge_for(context(tier=REBATING), dec("10000"), resting=True)
    assert caught.value.why.startswith("FEE.02")


def test_a_fee_needs_something_to_charge_against() -> None:
    with pytest.raises(BadArgument):
        charge_for(context(), dec("0"), resting=False)


def test_a_fee_charged_in_the_venue_token_converts_at_the_recorded_rate() -> None:
    charge = charge_for(
        context(fee_asset="BNB", fee_asset_rate=dec("500")), dec("10000"), resting=False
    )
    assert charge.asset == "BNB"
    assert charge.asset_amount == dec("0.032")
    assert charge.quote_amount == dec("16")


def test_a_fee_asset_with_no_rate_is_refused_rather_than_charged_at_par() -> None:
    with pytest.raises(Refused) as caught:
        context(fee_asset="BNB")
    assert caught.value.why.startswith("FEE.01")


def test_a_conversion_rate_of_zero_is_refused() -> None:
    with pytest.raises(BadArgument):
        context(fee_asset="BNB", fee_asset_rate=dec("0"))


def test_a_fee_asset_discount_reduces_the_rate() -> None:
    charge = charge_for(
        context(fee_asset="BNB", fee_asset_rate=dec("500"), fee_asset_discount_bps=dec("2500")),
        dec("10000"),
        resting=False,
    )
    assert charge.rate_bps == 12
    assert charge.quote_amount == dec("12")


def test_a_discount_never_turns_a_fee_into_a_rebate() -> None:
    charge = charge_for(
        context(fee_asset="BNB", fee_asset_rate=dec("500"), fee_asset_discount_bps=dec("20000")),
        dec("10000"),
        resting=False,
    )
    assert charge.rate_bps == 0
    assert not charge.is_rebate


def test_a_discount_does_not_shrink_a_rebate() -> None:
    charge = charge_for(
        context(
            tier=REBATING,
            pays_maker_rebate=True,
            fee_asset="BNB",
            fee_asset_rate=dec("500"),
            fee_asset_discount_bps=dec("2500"),
        ),
        dec("10000"),
        resting=True,
    )
    assert charge.rate_bps == -2


def test_a_negative_discount_is_refused() -> None:
    with pytest.raises(BadArgument):
        context(fee_asset_discount_bps=dec("-1"))


def test_a_round_trip_adds_both_legs_against_the_first_notional() -> None:
    first = charge_for(context(), dec("10000"), resting=False)
    second = charge_for(context(venue="okx"), dec("10000"), resting=False)
    assert round_trip_bps(first, second) == 32


def test_a_round_trip_with_a_rebate_leg_costs_less() -> None:
    taking = charge_for(context(), dec("10000"), resting=False)
    resting = charge_for(
        context(venue="okx", tier=REBATING, pays_maker_rebate=True), dec("10000"), resting=True
    )
    assert round_trip_bps(taking, resting) == 14


def test_a_round_trip_off_a_zero_notional_is_refused() -> None:
    charge = FeeCharge(
        venue="kraken",
        rate_bps=dec("16"),
        notional=dec("0"),
        quote_amount=dec("0"),
        asset="quote",
        asset_amount=dec("0"),
        is_rebate=False,
    )
    with pytest.raises(BadArgument):
        round_trip_bps(charge, charge)
