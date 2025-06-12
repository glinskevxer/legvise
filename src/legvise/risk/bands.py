"""What the inventory bands allow a leg to do, and what they charge it for.

The two directions are not symmetric and that asymmetry is the point.

Going **down**, the floor is a wall. A venue that runs out of the asset it sells
cannot trade at all until a transfer clears, which on some networks is forty
minutes. So a leg that would break the floor is refused outright, and the
refusal quotes BAND.01.

Going **up**, the ceiling is a price. Ending up long of the ceiling is fine and
sometimes unavoidable; it just means somebody will have to move the excess back,
and the cost of doing that belongs against the plan that caused it. So a leg
that lifts an asset over the ceiling is allowed and quoted BAND.02, which the
router later turns into a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.model.inventory import Band, Position
from legvise.money import ZERO
from legvise.rules import refuse

__all__ = [
    "BandRoom",
    "excess_above_ceiling",
    "room_to_receive",
    "room_to_spend",
    "require_room_to_spend",
    "room_for",
]


@dataclass(frozen=True, slots=True)
class BandRoom:
    """How much room a leg has in both directions, and what it would trip."""

    venue: str
    asset: str
    spendable: Decimal
    receivable: Decimal
    holding: Decimal
    target_gap: Decimal

    @property
    def is_below_floor(self) -> bool:
        """True when the desk is already under the floor before doing anything."""
        return self.spendable < ZERO

    @property
    def is_above_ceiling(self) -> bool:
        """True when the desk is already over the ceiling before doing anything."""
        return self.receivable < ZERO


def _match(position: Position, band: Band) -> None:
    if position.key != (band.venue, band.asset):
        raise BadArgument(
            "band",
            f"{band.venue}:{band.asset}",
            f"this position is {position.venue}:{position.asset}",
        )


def room_for(position: Position, band: Band) -> BandRoom:
    """Measure a position against its band in both directions."""
    _match(position, band)
    return BandRoom(
        venue=position.venue,
        asset=position.asset,
        spendable=band.headroom_below(position.free),
        receivable=band.headroom_above(position.total),
        holding=position.total,
        target_gap=band.distance_from_target(position.total),
    )


def room_to_spend(position: Position, band: Band) -> Decimal:
    """How much of the free balance a leg may take before the floor stops it.

    Never negative: a desk already under its floor has no room, not negative
    room, and reporting it as negative makes every downstream `min` wrong.
    """
    return max(room_for(position, band).spendable, ZERO)


def room_to_receive(position: Position, band: Band) -> Decimal:
    """How much more can arrive before the ceiling is crossed, floored at zero."""
    return max(room_for(position, band).receivable, ZERO)


def require_room_to_spend(position: Position, band: Band, amount: Decimal) -> Decimal:
    """Refuse a leg that would take the asset below its floor."""
    if amount <= ZERO:
        raise BadArgument("amount", str(amount), "a leg takes a positive amount")
    room = room_to_spend(position, band)
    if amount > room:
        raise refuse(
            "BAND.01",
            f"{position.venue} {position.asset} has {room} spendable against {amount}",
        )
    return room - amount


def excess_above_ceiling(position: Position, band: Band, incoming: Decimal) -> Decimal:
    """How far over the ceiling `incoming` would push the holding.

    Zero when it stays inside. This is the quantity the rebalance router prices,
    and it counts only the part that is actually over the line: a position that
    starts under the ceiling and ends over it is charged for the overshoot, not
    for the whole incoming amount.
    """
    if incoming < ZERO:
        raise BadArgument("incoming", str(incoming), "an arriving amount is not negative")
    _match(position, band)
    after = position.total + incoming
    return max(after - band.ceiling, ZERO)
