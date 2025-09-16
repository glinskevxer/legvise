"""What actually came back from the venue, against what the plan expected.

A plan is a forecast. A fill is what happened. The gap between them is the only
number that pays anybody, and a desk that records plans without fills is running
on its own opinion of itself.

Two things make this less simple than it looks.

A leg can fill in pieces, at different prices, over several seconds. So a fill
is not one row per leg; it is many, and the leg's realised price is their
size-weighted average.

And a leg can fail while its partner succeeds. That is the expensive case, it
is the one the desk most needs to count, and it is why `Execution` records a
status per leg rather than one status for the whole plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from legvise.errors import BadArgument
from legvise.ids import venue_code
from legvise.model.book import Side
from legvise.money import ZERO, dec

__all__ = ["Fill", "LegOutcome", "LegResult"]


class LegOutcome(str, Enum):
    """How one leg of a plan ended."""

    FILLED = "filled"
    PARTIAL = "partial"
    MISSED = "missed"
    CANCELLED = "cancelled"

    @property
    def traded(self) -> bool:
        """True when the desk ended up with a position from this leg."""
        return self in (LegOutcome.FILLED, LegOutcome.PARTIAL)


@dataclass(frozen=True, slots=True)
class Fill:
    """One execution against one leg, at one price."""

    plan_ref: str
    leg_index: int
    venue: str
    takes: Side
    price: Decimal
    size: Decimal
    fee_amount: Decimal
    filled_at: str

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if self.leg_index < 0:
            raise BadArgument("leg_index", self.leg_index, "a leg index starts at zero")
        if self.price <= ZERO:
            raise BadArgument("price", str(self.price), "a fill has a positive price")
        if self.size <= ZERO:
            raise BadArgument("size", str(self.size), "a fill has a positive size")
        if self.fee_amount < ZERO:
            raise BadArgument("fee_amount", str(self.fee_amount), "a fill fee is not negative")

    @property
    def notional(self) -> Decimal:
        """What the fill is worth in the quote asset, before the fee."""
        return self.price * self.size

    @classmethod
    def build(
        cls,
        plan_ref: str,
        leg_index: int,
        venue: str,
        takes: Side,
        *,
        price: str | Decimal,
        size: str | Decimal,
        fee_amount: str | Decimal = "0",
        filled_at: str,
    ) -> Fill:
        """Build a fill from loose input."""
        return cls(
            plan_ref=plan_ref,
            leg_index=leg_index,
            venue=venue_code(venue),
            takes=takes,
            price=dec(price, field="price"),
            size=dec(size, field="size"),
            fee_amount=dec(fee_amount, field="fee_amount"),
            filled_at=filled_at,
        )


@dataclass(frozen=True, slots=True)
class LegResult:
    """Every fill against one leg, collapsed into what the leg achieved."""

    plan_ref: str
    leg_index: int
    expected_price: Decimal
    expected_size: Decimal
    fills: tuple[Fill, ...]

    @property
    def filled_size(self) -> Decimal:
        """How much of the leg actually traded."""
        return sum((fill.size for fill in self.fills), start=ZERO)

    @property
    def filled_notional(self) -> Decimal:
        """What the traded part came to, before fees."""
        return sum((fill.notional for fill in self.fills), start=ZERO)

    @property
    def fees_paid(self) -> Decimal:
        """Everything the venue charged across the fills."""
        return sum((fill.fee_amount for fill in self.fills), start=ZERO)

    @property
    def realised_price(self) -> Decimal:
        """The size weighted price the leg actually got."""
        if self.filled_size == ZERO:
            raise BadArgument("fills", "()", "a leg that never traded has no realised price")
        return self.filled_notional / self.filled_size

    @property
    def outcome(self) -> LegOutcome:
        """What became of the leg."""
        if self.filled_size == ZERO:
            return LegOutcome.MISSED
        if self.filled_size < self.expected_size:
            return LegOutcome.PARTIAL
        return LegOutcome.FILLED

    @property
    def fill_ratio(self) -> Decimal:
        """The share of the intended size that traded."""
        if self.expected_size <= ZERO:
            raise BadArgument("expected_size", str(self.expected_size), "a leg wanted something")
        return self.filled_size / self.expected_size
