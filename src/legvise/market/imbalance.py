"""Which way a book is leaning, and how far down it that lean survives.

The mid says where a book is. It says nothing about where it is going, and on a
crossing pair the desk is about to take one side of two books at once, so the
direction matters.

Two measures, and they disagree often enough to be worth having both.

**Touch imbalance** is the classic one: bid size against ask size at the top,
scaled to sit between minus one and one. It is what everybody computes and it is
noisy, because the touch is where a single order changes the answer.

**Depth imbalance** asks the same question over everything inside a price band.
It moves more slowly and it is harder to push around, which is exactly why the
two disagreeing is informative: a book whose touch leans hard one way and whose
depth leans the other is usually one somebody is working an order in.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from legvise.errors import BadArgument
from legvise.market.depth import reachable
from legvise.model.book import Book, Side
from legvise.money import ZERO, dec
from legvise.rules import refuse

__all__ = ["Imbalance", "depth_imbalance", "imbalance_at", "touch_imbalance"]

ONE = dec("1")


class Imbalance(NamedTuple):
    """How a book leans, and the two sides the lean was measured from."""

    bid_size: Decimal
    ask_size: Decimal

    @property
    def ratio(self) -> Decimal:
        """Between minus one and one. Positive means more bid than ask."""
        total = self.bid_size + self.ask_size
        if total <= ZERO:
            raise BadArgument("sizes", "0", "an imbalance needs something on at least one side")
        return (self.bid_size - self.ask_size) / total

    @property
    def leans_bid(self) -> bool:
        """True when there is more resting on the bid."""
        return self.bid_size > self.ask_size

    @property
    def is_balanced(self) -> bool:
        """True when the two sides are the same size."""
        return self.bid_size == self.ask_size


def touch_imbalance(book: Book) -> Imbalance:
    """How the top of the book leans."""
    if not book.is_two_sided():
        raise refuse("BOOK.02", f"{book.venue} {book.symbol}")
    return Imbalance(
        bid_size=book.touch(Side.BID).size,
        ask_size=book.touch(Side.ASK).size,
    )


def depth_imbalance(book: Book, limit_bps: Decimal) -> Imbalance:
    """How the book leans across everything inside `limit_bps` of the touch."""
    if not book.is_two_sided():
        raise refuse("BOOK.02", f"{book.venue} {book.symbol}")
    return Imbalance(
        bid_size=reachable(book, Side.BID, limit_bps).size,
        ask_size=reachable(book, Side.ASK, limit_bps).size,
    )


def imbalance_at(book: Book, limit_bps: Decimal) -> tuple[Imbalance, Imbalance]:
    """Both measures at once, touch first."""
    return (touch_imbalance(book), depth_imbalance(book, limit_bps))


def disagreement(book: Book, limit_bps: Decimal) -> Decimal:
    """How far the two measures are apart, always non-negative.

    A large number here means the touch and the depth are telling different
    stories, which is a reason to size smaller rather than a reason to trade.
    """
    touch, depth = imbalance_at(book, limit_bps)
    gap = touch.ratio - depth.ratio
    return -gap if gap < ZERO else gap


def leans_toward(book: Book, limit_bps: Decimal) -> Side | None:
    """The side both measures agree the book leans toward, or nothing."""
    touch, depth = imbalance_at(book, limit_bps)
    if touch.is_balanced or depth.is_balanced:
        return None
    if touch.leans_bid != depth.leans_bid:
        return None
    return Side.BID if touch.leans_bid else Side.ASK
