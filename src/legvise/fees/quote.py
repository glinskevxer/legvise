"""What one leg costs in fees, in the quote asset, rounded the desk's way.

Two rounding rules, and they point in opposite directions on purpose:

- a **fee owed** rounds up to the quote asset's smallest unit, so the desk never
  books less than it will pay
- a **rebate earned** rounds down, so the desk never books more than it will get

Rounding both the same way is the sort of thing that nets out to nothing on a
spreadsheet and to a slow leak across forty thousand fills a month.

The other thing this module owns is the fee asset. A venue that charges in its
own token converts at a rate the desk records; if that rate is missing the
charge cannot be priced and the leg is refused rather than charged at par.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.fees.ladder import effective_bps
from legvise.model.fee import FeeTier
from legvise.money import ZERO, apply_bps, dec, quantize_down, quantize_up, to_bps
from legvise.rules import refuse

__all__ = ["FeeCharge", "FeeContext", "charge_for"]

QUOTE_UNIT = dec("0.00000001")


@dataclass(frozen=True, slots=True)
class FeeContext:
    """Everything about a venue that changes what a leg's fee comes to."""

    venue: str
    tier: FeeTier
    pays_maker_rebate: bool
    fee_asset: str | None = None
    fee_asset_rate: Decimal | None = None
    fee_asset_discount_bps: Decimal = ZERO

    def __post_init__(self) -> None:
        if self.fee_asset is not None and self.fee_asset_rate is None:
            raise refuse("FEE.01", f"{self.venue} charges in {self.fee_asset} at no known rate")
        if self.fee_asset_rate is not None and self.fee_asset_rate <= ZERO:
            raise BadArgument(
                "fee_asset_rate", str(self.fee_asset_rate), "a conversion rate has to be positive"
            )
        if self.fee_asset_discount_bps < ZERO:
            raise BadArgument(
                "fee_asset_discount_bps",
                str(self.fee_asset_discount_bps),
                "a discount is not negative",
            )


@dataclass(frozen=True, slots=True)
class FeeCharge:
    """What one leg pays, and enough detail to argue with a venue about it."""

    venue: str
    rate_bps: Decimal
    notional: Decimal
    quote_amount: Decimal
    asset: str
    asset_amount: Decimal
    is_rebate: bool

    @property
    def signed_quote_amount(self) -> Decimal:
        """Positive when the desk pays, negative when the venue does."""
        return -self.quote_amount if self.is_rebate else self.quote_amount


def _rate_after_discount(rate_bps: Decimal, discount_bps: Decimal) -> Decimal:
    if rate_bps <= ZERO or discount_bps == ZERO:
        return rate_bps
    reduced = rate_bps - apply_bps(rate_bps, discount_bps)
    return max(reduced, ZERO)


def charge_for(
    context: FeeContext, notional: Decimal, *, resting: bool, unit: Decimal = QUOTE_UNIT
) -> FeeCharge:
    """Price one leg's fee against a notional in the quote asset."""
    if notional <= ZERO:
        raise BadArgument("notional", str(notional), "a fee needs something to charge against")
    rate = effective_bps(context.tier, resting, venue_pays_rebate=context.pays_maker_rebate)
    rate = _rate_after_discount(rate, context.fee_asset_discount_bps)
    raw = apply_bps(notional, rate)
    is_rebate = raw < ZERO
    magnitude = -raw if is_rebate else raw
    quote_amount = (
        quantize_down(magnitude, unit, field="unit")
        if is_rebate
        else quantize_up(magnitude, unit, field="unit")
    )
    asset, asset_amount = _in_fee_asset(context, quote_amount, unit)
    return FeeCharge(
        venue=context.venue,
        rate_bps=rate,
        notional=notional,
        quote_amount=quote_amount,
        asset=asset,
        asset_amount=asset_amount,
        is_rebate=is_rebate,
    )


def _in_fee_asset(context: FeeContext, quote_amount: Decimal, unit: Decimal) -> tuple[str, Decimal]:
    if context.fee_asset is None or context.fee_asset_rate is None:
        return ("quote", quote_amount)
    converted = quote_amount / context.fee_asset_rate
    return (context.fee_asset, quantize_up(converted, unit, field="unit"))


def round_trip_bps(first: FeeCharge, second: FeeCharge) -> Decimal:
    """Both legs' fees expressed as basis points of the first leg's notional."""
    if first.notional <= ZERO:
        raise BadArgument("notional", str(first.notional), "a round trip needs a notional")
    total = first.signed_quote_amount + second.signed_quote_amount
    return to_bps(total, first.notional, field="notional")
