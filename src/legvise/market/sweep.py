"""What a walk through a book came back with.

Split out of `market.depth` because it is a value, not an algorithm, and the
distinction earns its keep: five modules want to hold a `Sweep`, describe one in
a signature or read one back, and only one of them wants to know how a book is
walked. Before the split, `scan.direct` imported the whole walking machinery to
name a return type.

`vwap` refuses on an empty sweep rather than returning zero. A sweep that got
nothing has no average price, and zero is a number a caller will happily divide
by.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from legvise.errors import BadArgument
from legvise.model.book import Level, Side
from legvise.money import ZERO

__all__ = ["Sweep", "consume", "empty_sweep"]


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


def empty_sweep(side: Side) -> Sweep:
    """The sweep a walk against a side with nothing on it comes back with."""
    return Sweep(
        side=side,
        size=ZERO,
        notional=ZERO,
        levels=0,
        worst_price=ZERO,
        complete=False,
    )


def consume(levels: tuple[Level, ...], side: Side, target: Decimal) -> Sweep:
    """Take `target` size off the front of `levels`, level by level."""
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
