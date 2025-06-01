"""What the desk is holding where, and where it wants to be holding it.

This is a **prefunded** desk. Nothing is transferred between venues at trade
time; both legs of a plan execute against balances that are already sitting on
each venue. That single fact drives most of the design: a leg is limited by the
inventory on its own venue, and the cost of getting inventory back where it
belongs is a separate, slower, amortised thing.

A band is the desk's policy for one asset on one venue. The floor is a hard
stop -- crossing it means the next opportunity cannot be taken at all. The
ceiling is soft: crossing it is allowed, and it books a rebalancing cost
against the plan that pushed it over.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ids import asset_code, venue_code
from legvise.money import ZERO, dec

__all__ = ["Band", "Position"]


@dataclass(frozen=True, slots=True)
class Position:
    """What one asset's balance on one venue is, split by what is usable."""

    venue: str
    asset: str
    free: Decimal
    locked: Decimal
    as_of: str

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if self.asset != asset_code(self.asset):
            raise BadArgument("asset", self.asset, "asset codes are stored normalised")
        if self.free < ZERO:
            raise BadArgument("free", str(self.free), "a free balance is not negative")
        if self.locked < ZERO:
            raise BadArgument("locked", str(self.locked), "a locked balance is not negative")

    @property
    def total(self) -> Decimal:
        """Everything the desk holds, usable or not."""
        return self.free + self.locked

    @property
    def key(self) -> tuple[str, str]:
        """The pair the store keys on."""
        return (self.venue, self.asset)

    def after_taking(self, amount: Decimal) -> Position:
        """The position that would result from spending `amount` of free balance."""
        if amount < ZERO:
            raise BadArgument("amount", str(amount), "use after_receiving to add")
        return Position(
            venue=self.venue,
            asset=self.asset,
            free=self.free - amount,
            locked=self.locked,
            as_of=self.as_of,
        )

    def after_receiving(self, amount: Decimal) -> Position:
        """The position that would result from receiving `amount`."""
        if amount < ZERO:
            raise BadArgument("amount", str(amount), "use after_taking to subtract")
        return Position(
            venue=self.venue,
            asset=self.asset,
            free=self.free + amount,
            locked=self.locked,
            as_of=self.as_of,
        )

    @classmethod
    def build(
        cls,
        venue: str,
        asset: str,
        *,
        free: str | Decimal,
        locked: str | Decimal = "0",
        as_of: str,
    ) -> Position:
        """Build a position from loose input."""
        return cls(
            venue=venue_code(venue),
            asset=asset_code(asset),
            free=dec(free, field="free"),
            locked=dec(locked, field="locked"),
            as_of=as_of,
        )


@dataclass(frozen=True, slots=True)
class Band:
    """The desk's floor, target and ceiling for one asset on one venue."""

    venue: str
    asset: str
    floor: Decimal
    target: Decimal
    ceiling: Decimal

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if self.asset != asset_code(self.asset):
            raise BadArgument("asset", self.asset, "asset codes are stored normalised")
        if self.floor < ZERO:
            raise BadArgument("floor", str(self.floor), "a floor is not negative")
        if not self.floor <= self.target <= self.ceiling:
            raise BadArgument(
                "target",
                str(self.target),
                "the target has to sit between the floor and the ceiling",
            )

    @property
    def width(self) -> Decimal:
        """How much room there is between the floor and the ceiling."""
        return self.ceiling - self.floor

    def headroom_above(self, holding: Decimal) -> Decimal:
        """How much more can be held before the ceiling. Negative once over it."""
        return self.ceiling - holding

    def headroom_below(self, holding: Decimal) -> Decimal:
        """How much can be spent before the floor. Negative once under it."""
        return holding - self.floor

    def distance_from_target(self, holding: Decimal) -> Decimal:
        """Signed distance from the target: positive when long of it."""
        return holding - self.target

    @classmethod
    def build(
        cls,
        venue: str,
        asset: str,
        *,
        floor: str | Decimal,
        target: str | Decimal,
        ceiling: str | Decimal,
    ) -> Band:
        """Build a band from loose input."""
        return cls(
            venue=venue_code(venue),
            asset=asset_code(asset),
            floor=dec(floor, field="floor"),
            target=dec(target, field="target"),
            ceiling=dec(ceiling, field="ceiling"),
        )
