"""Walking a book, which is the only honest way to price a leg.

Top of book is a lie the moment the size is bigger than the touch. A desk that
prices a 40 BTC leg off a 0.3 BTC best ask is reading a number that does not
exist, and the difference shows up as slippage in the attribution report a week
later, where nobody can do anything about it.

So every price in this package comes from a sweep. `walk` fills a target size
level by level and reports what it actually cost; `reachable` answers the
opposite question, which is how much size sits inside a price limit.

Both refuse to invent liquidity. A walk that runs out of book comes back
incomplete rather than extrapolating the last level, and the caller decides
whether a partial fill is worth having.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from legvise.errors import BadArgument
from legvise.model.book import Book, Level, Side
from legvise.money import ZERO, apply_bps, bps_between
from legvise.rules import refuse

__all__ = ["Sweep", "reachable", "sweep_cost", "walk"]


class Sweep(NamedTuple):
    """What a walk through the book actually got."""

    side: Side
    size: Decimal
    notional: Decimal
    levels: int
    worst_price: Decimal
    complete: bool

    @property
    def vwap(self) -> Decimal:
        """The average price paid across the whole sweep."""
        if self.size == ZERO:
            raise BadArgument("size", "0", "an empty sweep has no average price")
        return self.notional / self.size

    @property
    def is_empty(self) -> bool:
        """True when the walk got nothing at all."""
        return self.size == ZERO


def _empty(side: Side) -> Sweep:
    return Sweep(
        side=side,
        size=ZERO,
        notional=ZERO,
        levels=0,
        worst_price=ZERO,
        complete=False,
    )


def walk(book: Book, side: Side, target: Decimal) -> Sweep:
    """Fill `target` size against `side` of `book`, level by level.

    `side` is the side of the book being taken, not the side of the order. A buy
    takes the asks.
    """
    if target <= ZERO:
        raise BadArgument("target", str(target), "a walk needs a positive size")
    levels = book.side(side)
    if not levels:
        return _empty(side)
    return _consume(levels, side, target)


def _consume(levels: tuple[Level, ...], side: Side, target: Decimal) -> Sweep:
    remaining = target
    size = ZERO
    notional = ZERO
    touched = 0
    worst = ZERO
    for level in levels:
        if remaining <= ZERO:
            break
        take = min(remaining, level.size)
        size += take
        notional += take * level.price
        worst = level.price
        touched += 1
        remaining -= take
    return Sweep(
        side=side,
        size=size,
        notional=notional,
        levels=touched,
        worst_price=worst,
        complete=remaining <= ZERO,
    )


def walk_for_notional(book: Book, side: Side, budget: Decimal) -> Sweep:
    """Fill against `side` until `budget` of the quote asset is used up.

    The mirror of `walk`, and the one a conversion loop needs: a hop that starts
    holding the quote asset knows what it has to spend, not what size that buys.
    Working it out by dividing the budget by the touch and then walking is wrong
    the moment the first level runs out, because the average price rises as the
    walk goes on and the affordable size falls with it.
    """
    if budget <= ZERO:
        raise BadArgument("budget", str(budget), "a walk needs a positive budget")
    levels = book.side(side)
    if not levels:
        return _empty(side)
    remaining = budget
    size = ZERO
    notional = ZERO
    touched = 0
    worst = ZERO
    for level in levels:
        if remaining <= ZERO:
            break
        affordable = remaining / level.price
        worst = level.price
        touched += 1
        if affordable <= level.size:
            # This level covers the rest. Book the remaining budget exactly
            # rather than multiplying the divided size back up: the round trip
            # through a division leaves dust, and dust here reads as an
            # unfillable walk.
            size += affordable
            notional += remaining
            remaining = ZERO
            break
        size += level.size
        spent = level.size * level.price
        notional += spent
        remaining -= spent
    return Sweep(
        side=side,
        size=size,
        notional=notional,
        levels=touched,
        worst_price=worst,
        complete=remaining <= ZERO,
    )


def reachable(book: Book, side: Side, limit_bps: Decimal) -> Sweep:
    """Everything resting within `limit_bps` of the touch on `side`.

    The limit is measured away from the touch in the direction that costs money:
    buying, that is upward through the asks; selling, downward through the bids.
    """
    if limit_bps <= ZERO:
        raise BadArgument("limit_bps", str(limit_bps), "a depth limit has to be positive")
    levels = book.side(side)
    if not levels:
        return _empty(side)
    touch = levels[0].price
    edge = apply_bps(touch, limit_bps)
    worst_allowed = touch + edge if side is Side.ASK else touch - edge
    inside = tuple(level for level in levels if _within(level.price, worst_allowed, side))
    if not inside:
        return _empty(side)
    total = sum((level.size for level in inside), start=ZERO)
    return _consume(inside, side, total)


def _within(price: Decimal, worst_allowed: Decimal, side: Side) -> bool:
    return price <= worst_allowed if side is Side.ASK else price >= worst_allowed


def sweep_cost(book: Book, side: Side, target: Decimal, limit_bps: Decimal) -> Sweep:
    """Walk for `target`, refusing to go further than the venue depth limit.

    This is the function the scanner calls. It fails in two different ways on
    purpose: DEPTH.01 when the book simply does not hold the size, DEPTH.02 when
    it does but only outside the price the desk is willing to reach for.
    """
    within = reachable(book, side, limit_bps)
    if within.is_empty or within.size < target:
        got = walk(book, side, target)
        if not got.complete:
            raise refuse("DEPTH.01", f"{book.venue} {book.symbol} {side.value} for {target}")
        raise refuse("DEPTH.02", f"{book.venue} {book.symbol} {side.value} for {target}")
    return _consume(book.side(side), side, target)


def slippage_bps(book: Book, sweep: Sweep) -> Decimal:
    """How far the sweep's average price sits from the touch, in basis points.

    Always non-negative: a sweep can only ever pay away from the touch.
    """
    touch = book.touch(sweep.side).price
    if sweep.side is Side.ASK:
        return bps_between(touch, sweep.vwap)
    return bps_between(sweep.vwap, touch)
