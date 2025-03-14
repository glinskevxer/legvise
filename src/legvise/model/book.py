"""An order book snapshot, and what the desk insists is true of one.

A book arrives from a feed handler that this package does not own, so it is
checked rather than trusted. The four things checked here have all been seen in
production on at least one venue: a side arriving in the wrong order after a
resync, a zero size level left behind by a partial cancel, a negative price from
a bad decimal parse, and a locked book across a sequence gap.

The rules quote clauses so a rejected snapshot can be counted later. A feed that
produces BOOK.01 twenty times an hour is a feed handler bug, and the only way to
know that is to have written the code down when the snapshot was dropped.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from legvise.errors import BadArgument
from legvise.ids import Symbol, parse_symbol, venue_code
from legvise.money import ZERO, dec
from legvise.rules import refuse

__all__ = ["Book", "Level", "Side"]


class Side(str, Enum):
    """Which half of the book a level or an order sits on."""

    BID = "bid"
    ASK = "ask"

    @property
    def other(self) -> Side:
        """The opposite side."""
        return Side.ASK if self is Side.BID else Side.BID

    @property
    def takes(self) -> Side:
        """The side of the book an order on this side trades against."""
        return self.other


@dataclass(frozen=True, slots=True)
class Level:
    """One price and the size resting at it."""

    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        if self.price <= ZERO or self.size <= ZERO:
            raise refuse("BOOK.03", f"level at {self.price}")

    @property
    def notional(self) -> Decimal:
        """What the whole level is worth in the quote asset."""
        return self.price * self.size

    @classmethod
    def build(cls, price: str | Decimal, size: str | Decimal) -> Level:
        """Build a level from loose input."""
        return cls(price=dec(price, field="price"), size=dec(size, field="size"))


@dataclass(frozen=True, slots=True)
class Book:
    """One snapshot of one market on one venue."""

    venue: str
    symbol: Symbol
    observed_at: dt.datetime
    sequence: int
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if self.observed_at.tzinfo is None:
            raise BadArgument("observed_at", self.observed_at, "an instant needs a timezone")
        if self.sequence < 0:
            raise BadArgument("sequence", self.sequence, "a sequence number starts at zero")
        _check_order(self.bids, Side.BID, self.venue)
        _check_order(self.asks, Side.ASK, self.venue)
        if self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
            raise refuse("BOOK.04", f"{self.venue} {self.symbol}")

    @property
    def best_bid(self) -> Level | None:
        """The highest bid, or nothing on an empty side."""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Level | None:
        """The lowest ask, or nothing on an empty side."""
        return self.asks[0] if self.asks else None

    def side(self, side: Side) -> tuple[Level, ...]:
        """One side of the book, best price first."""
        return self.bids if side is Side.BID else self.asks

    def touch(self, side: Side) -> Level:
        """The best level on a side, refusing an empty one."""
        levels = self.side(side)
        if not levels:
            raise refuse("BOOK.02", f"{self.venue} {self.symbol} {side.value}")
        return levels[0]

    def is_two_sided(self) -> bool:
        """True when both sides carry at least one level."""
        return bool(self.bids) and bool(self.asks)

    @classmethod
    def build(
        cls,
        venue: str,
        symbol: str | Symbol,
        *,
        observed_at: dt.datetime,
        bids: tuple[tuple[str, str], ...] = (),
        asks: tuple[tuple[str, str], ...] = (),
        sequence: int = 0,
    ) -> Book:
        """Build a book from the tuples a feed handler produces."""
        return cls(
            venue=venue_code(venue),
            symbol=symbol if isinstance(symbol, Symbol) else parse_symbol(symbol),
            observed_at=observed_at,
            sequence=sequence,
            bids=tuple(Level.build(p, s) for p, s in bids),
            asks=tuple(Level.build(p, s) for p, s in asks),
        )


def _check_order(levels: tuple[Level, ...], side: Side, venue: str) -> None:
    for earlier, later in zip(levels, levels[1:], strict=False):
        wrong = earlier.price <= later.price if side is Side.BID else earlier.price >= later.price
        if wrong:
            raise refuse("BOOK.01", f"{venue} {side.value} side at {later.price}")
