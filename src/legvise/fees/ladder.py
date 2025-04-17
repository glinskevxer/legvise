"""Working out which rung of a fee ladder the desk is actually standing on.

Trailing volume is measured by the venue, not by this package, so it arrives as
a number the operator or a nightly job puts on file. What this module owns is
the resolution rule, which is duller and more error prone than it sounds:

- the rung is the **highest** one whose threshold the volume has reached
- a volume exactly on a threshold reaches it, because every venue publishes
  these as "30d volume >= X"
- volume the desk has not recorded is not zero volume, it is unknown, and
  pricing a leg on the base rung because nobody ran the nightly job quietly
  overstates every cost by six basis points

That last one is why `resolve` refuses rather than defaulting.
"""

from __future__ import annotations

from decimal import Decimal

from legvise.errors import BadArgument
from legvise.model.book import Side
from legvise.model.fee import FeeLadder, FeeTier
from legvise.money import ZERO
from legvise.rules import refuse

__all__ = ["effective_bps", "resolve", "rung_index", "taker_bps_at"]


def rung_index(ladder: FeeLadder, volume_30d: Decimal) -> int:
    """Which rung of the ladder a trailing volume reaches, counting from zero."""
    if volume_30d < ZERO:
        raise BadArgument("volume_30d", str(volume_30d), "trailing volume is not negative")
    found = 0
    for index, tier in enumerate(ladder.tiers):
        if volume_30d >= tier.min_volume_30d:
            found = index
        else:
            break
    return found


def resolve(ladder: FeeLadder, volume_30d: Decimal | None) -> FeeTier:
    """The tier the desk pays on, refusing an unknown volume.

    `None` means nobody has recorded a volume for this venue. That is a
    different thing from zero and it is not safe to guess, so it fails.
    """
    if volume_30d is None:
        raise refuse("FEE.01", f"{ladder.venue} has no recorded 30 day volume")
    return ladder.tiers[rung_index(ladder, volume_30d)]


def taker_bps_at(ladder: FeeLadder, volume_30d: Decimal | None) -> Decimal:
    """The taker rate the desk pays right now."""
    return resolve(ladder, volume_30d).taker_bps


def effective_bps(tier: FeeTier, side_is_passive: bool, *, venue_pays_rebate: bool) -> Decimal:
    """The rate one leg actually pays, in basis points.

    A resting leg pays the maker rate. A rebate only counts where the venue
    actually pays one, because several venues publish a negative maker number
    that they only honour for registered market makers, and the desk is not one
    everywhere it trades.
    """
    if not side_is_passive:
        return tier.taker_bps
    if tier.is_rebate and not venue_pays_rebate:
        raise refuse("FEE.02", "a maker rebate this venue does not pay the desk")
    return tier.maker_bps


def leg_is_passive(order_side: Side, resting: bool) -> bool:
    """Whether a leg on `order_side` is providing liquidity.

    The side does not decide this on its own; a resting order is passive on
    either side. The argument is here so call sites read as a sentence.
    """
    del order_side
    return resting
