"""Whether the desk can pay a fee in the asset it is billed in."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.fees.balance import (
    cycles_funded,
    discount_is_safe,
    funding_for,
    require_funded,
)
from legvise.fees.quote import FeeContext, charge_for
from legvise.model.fee import FeeTier
from legvise.model.inventory import Position
from legvise.money import dec

AS_OF = "2026-02-26T09:00:00+00:00"
TIER = FeeTier.build("0", "0", "16")


def context(**changes: object) -> FeeContext:
    fields: dict[str, object] = {
        "venue": "okx",
        "tier": TIER,
        "pays_maker_rebate": False,
        "fee_asset": "OKB",
        "fee_asset_rate": dec("50"),
        "fee_asset_discount_bps": dec("2500"),
    }
    fields.update(changes)
    return FeeContext(**fields)  # type: ignore[arg-type]


def a_charge(notional: str = "10000", **changes: object) -> object:
    return charge_for(context(**changes), dec(notional), resting=False)


def holding(free: str, asset: str = "OKB") -> Position:
    return Position.build("okx", asset, free=free, as_of=AS_OF)


def test_a_charge_in_the_quote_asset_needs_no_separate_balance() -> None:
    quote_only = charge_for(
        context(fee_asset=None, fee_asset_rate=None, fee_asset_discount_bps=dec("0")),
        dec("10000"),
        resting=False,
    )
    found = funding_for(quote_only, None)
    assert found.is_funded
    assert found.needed == dec("0")


def test_a_charge_in_a_token_the_desk_holds_none_of_is_unfunded() -> None:
    found = funding_for(a_charge(), None)  # type: ignore[arg-type]
    assert not found.is_funded
    assert found.available == dec("0")
    assert found.shortfall == found.needed


def test_a_charge_the_balance_covers_is_funded() -> None:
    found = funding_for(a_charge(), holding("100"))  # type: ignore[arg-type]
    assert found.is_funded
    assert found.shortfall == dec("0")
    assert found.remaining == dec("100") - found.needed


def test_a_balance_exactly_covering_the_charge_is_funded() -> None:
    charge = a_charge()
    found = funding_for(charge, holding(str(charge.asset_amount)))  # type: ignore[attr-defined,arg-type]
    assert found.is_funded
    assert found.remaining == dec("0")


def test_a_balance_one_unit_short_is_not_funded() -> None:
    charge = a_charge()
    short = charge.asset_amount - dec("0.00000001")  # type: ignore[attr-defined]
    found = funding_for(charge, holding(str(short)))  # type: ignore[arg-type]
    assert not found.is_funded
    assert found.shortfall == dec("0.00000001")


def test_locked_balance_does_not_count_toward_the_fee() -> None:
    locked = Position.build("okx", "OKB", free="0", locked="1000", as_of=AS_OF)
    assert not funding_for(a_charge(), locked).is_funded  # type: ignore[arg-type]


def test_a_position_in_the_wrong_asset_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        funding_for(a_charge(), holding("100", asset="BTC"))  # type: ignore[arg-type]
    assert "this charge is in OKB" in caught.value.why


def test_requiring_funding_passes_when_the_balance_covers_it() -> None:
    assert require_funded(a_charge(), holding("100")).is_funded  # type: ignore[arg-type]


def test_requiring_funding_quotes_the_fee_clause_when_it_does_not() -> None:
    with pytest.raises(Refused) as caught:
        require_funded(a_charge(), None)  # type: ignore[arg-type]
    assert caught.value.why.startswith("FEE.01")
    assert "okx bills" in caught.value.subject


def test_the_cycle_count_says_how_many_more_charges_fit() -> None:
    charge = a_charge()
    ten = charge.asset_amount * dec("10")  # type: ignore[attr-defined]
    assert cycles_funded(charge, holding(str(ten))) == 10  # type: ignore[arg-type]


def test_a_charge_with_nothing_to_pay_reports_no_cycles() -> None:
    quote_only = charge_for(
        context(fee_asset=None, fee_asset_rate=None, fee_asset_discount_bps=dec("0")),
        dec("10000"),
        resting=False,
    )
    assert cycles_funded(quote_only, None) == 0


def test_a_discount_the_desk_cannot_fund_is_not_safe() -> None:
    assert not discount_is_safe(context(), None, a_charge())  # type: ignore[arg-type]


def test_a_discount_the_desk_can_fund_is_safe() -> None:
    assert discount_is_safe(context(), holding("100"), a_charge())  # type: ignore[arg-type]


def test_a_venue_with_no_fee_asset_has_no_discount_to_lose() -> None:
    plain = context(fee_asset=None, fee_asset_rate=None, fee_asset_discount_bps=dec("0"))
    assert discount_is_safe(plain, None, charge_for(plain, dec("10000"), resting=False))
