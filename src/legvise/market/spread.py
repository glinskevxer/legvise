"""Reading a book at the touch, and reading two books against each other.

Nothing here decides anything. These are the cheap numbers a scan computes
first, to throw away the ninety-odd percent of symbol pairs that are nowhere
near crossing before spending a depth walk on them.

The one that matters is `raw_cross_bps`. It answers a single question: if the
desk bought the whole touch on one venue and sold it on the other, how many
basis points would it be ahead **before any cost at all**. That number is
always optimistic. It ignores fees, depth, the lot step and the fact that the
two books were not observed at the same instant. A desk that trades off it
loses money, and a desk that does not compute it first wastes its scan budget.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from legvise.model.book import Book, Side
from legvise.money import ZERO, bps_between
from legvise.rules import refuse

__all__ = [
    "Touch",
    "TwoSided",
    "microprice",
    "mid",
    "raw_cross_bps",
    "spread_bps",
    "touch_of",
    "two_sided",
]


class Touch(NamedTuple):
    """The best price and size on one side."""

    price: Decimal
    size: Decimal


class TwoSided(NamedTuple):
    """Both touches of one book, when both sides are there."""

    bid: Touch
    ask: Touch

    @property
    def mid(self) -> Decimal:
        """Halfway between the two touches."""
        return (self.bid.price + self.ask.price) / Decimal(2)

    @property
    def spread(self) -> Decimal:
        """The gap between the touches, in the quote asset."""
        return self.ask.price - self.bid.price


def touch_of(book: Book, side: Side) -> Touch:
    """The best level on a side, as a price and a size."""
    level = book.touch(side)
    return Touch(price=level.price, size=level.size)


def two_sided(book: Book) -> TwoSided:
    """Both touches, refusing a book that only has one side."""
    if not book.is_two_sided():
        raise refuse("BOOK.02", f"{book.venue} {book.symbol}")
    return TwoSided(bid=touch_of(book, Side.BID), ask=touch_of(book, Side.ASK))


def mid(book: Book) -> Decimal:
    """The midpoint of the touch."""
    return two_sided(book).mid


def spread_bps(book: Book) -> Decimal:
    """How wide the book is at the touch, in basis points of the mid."""
    sides = two_sided(book)
    return bps_between(sides.mid, sides.ask.price) * Decimal(2)


def microprice(book: Book) -> Decimal:
    """The size-weighted midpoint, which leans toward the thinner side.

    A book with 40 bid and 1 offered is far more likely to trade up than down,
    and the mid says nothing about that. This is not used to price a leg; it is
    used to rank which of two nearly identical opportunities to look at first.
    """
    sides = two_sided(book)
    total = sides.bid.size + sides.ask.size
    if total == ZERO:  # pragma: no cover - a level with zero size cannot be built
        return sides.mid
    weighted = sides.bid.price * sides.ask.size + sides.ask.price * sides.bid.size
    return weighted / total


def raw_cross_bps(buy_from: Book, sell_into: Book) -> Decimal:
    """Touch-to-touch edge in basis points, before any cost whatsoever.

    Negative when the two books do not cross, which is the normal case and is
    not an error. The sign is what a scan filters on.
    """
    if buy_from.symbol != sell_into.symbol:
        raise refuse("EDGE.02", f"{buy_from.symbol} against {sell_into.symbol}")
    ask = touch_of(buy_from, Side.ASK)
    bid = touch_of(sell_into, Side.BID)
    return bps_between(ask.price, bid.price)


def crosses(buy_from: Book, sell_into: Book) -> bool:
    """True when the bid on one venue sits above the ask on the other."""
    return raw_cross_bps(buy_from, sell_into) > ZERO
