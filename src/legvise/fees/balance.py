"""Whether the desk can actually pay the fee it is about to owe.

A venue that charges in its own token takes the token, and when the balance runs
out it silently falls back to charging in the quote asset at the undiscounted
rate. The plan priced twelve basis points and the desk pays sixteen, and nothing
anywhere says so: the fee is charged, the trade settles, and the only trace is
four basis points that never arrive.

So the balance is a precondition, checked before the discount is priced. The
check is deliberately conservative -- it counts free balance only, because a fee
asset locked in an open order is not available to pay a fee.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.fees.quote import FeeCharge, FeeContext
from legvise.model.inventory import Position
from legvise.money import ZERO
from legvise.rules import refuse

__all__ = ["FeeFunding", "cycles_funded", "funding_for", "require_funded"]


@dataclass(frozen=True, slots=True)
class FeeFunding:
    """What paying one charge in the fee asset would leave behind."""

    asset: str
    needed: Decimal
    available: Decimal

    @property
    def is_funded(self) -> bool:
        """True when the free balance covers the charge."""
        return self.available >= self.needed

    @property
    def shortfall(self) -> Decimal:
        """How much more of the fee asset the desk needs, floored at zero."""
        return max(self.needed - self.available, ZERO)

    @property
    def remaining(self) -> Decimal:
        """What is left after paying, floored at zero."""
        return max(self.available - self.needed, ZERO)


def funding_for(charge: FeeCharge, position: Position | None) -> FeeFunding:
    """Measure one charge against the balance that would pay it.

    A charge in the quote asset is always funded here: the trade itself settles
    in that asset, so there is nothing separate to run out of.
    """
    if charge.asset == "quote":
        return FeeFunding(asset="quote", needed=ZERO, available=ZERO)
    if position is None:
        return FeeFunding(asset=charge.asset, needed=charge.asset_amount, available=ZERO)
    if position.asset != charge.asset:
        raise BadArgument("position", position.asset, f"this charge is in {charge.asset}")
    return FeeFunding(
        asset=charge.asset,
        needed=charge.asset_amount,
        available=position.free,
    )


def require_funded(charge: FeeCharge, position: Position | None) -> FeeFunding:
    """Refuse a charge the desk cannot pay in the asset it is billed in."""
    found = funding_for(charge, position)
    if found.is_funded:
        return found
    raise refuse(
        "FEE.01",
        f"{charge.venue} bills {found.needed} {found.asset} and the desk has {found.available}",
    )


def cycles_funded(charge: FeeCharge, position: Position | None) -> int:
    """How many more charges this size the balance would cover.

    The number an operator wants at four in the morning: not "is it funded" but
    "how long have I got". Unbounded charges in the quote asset report zero,
    because the question does not apply to them.
    """
    found = funding_for(charge, position)
    if found.needed <= ZERO:
        return 0
    return int(found.available / found.needed)


def discount_is_safe(context: FeeContext, position: Position | None, charge: FeeCharge) -> bool:
    """True when the desk may rely on the fee asset discount it just priced.

    A context with no fee asset has no discount to lose, so it is always safe.
    """
    if context.fee_asset is None:
        return True
    return funding_for(charge, position).is_funded
