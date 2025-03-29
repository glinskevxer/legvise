"""Bending a theoretical order into one the venue will actually accept.

The scanner works in real numbers. The venue works in ticks and lots and has a
minimum notional, and it rejects anything else. Between the two sits this
module, and the direction of every rounding here is chosen so the rounded order
is never worse than the one that was priced:

- a size rounds **down** to the lot step, because rounding up asks for depth the
  sweep did not price
- a buy limit rounds **up** to the tick and a sell limit rounds **down**, so the
  order stays marketable against the level it was priced against
- the notional is then rechecked, because rounding a size down can drop an order
  under the venue minimum, and that rejection arrives after the other leg has
  already gone out

That last point is the whole reason this is a separate step rather than three
lines inside the sizer.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from legvise.model.book import Side
from legvise.model.instrument import Instrument
from legvise.money import ZERO, quantize_down, quantize_up, step_multiple
from legvise.rules import refuse

__all__ = [
    "ConformedOrder",
    "conform_order",
    "conform_price",
    "conform_size",
    "fits_notional",
    "require_notional",
]


class ConformedOrder(NamedTuple):
    """A price and a size the venue will take, and what they came from."""

    side: Side
    price: Decimal
    size: Decimal
    requested_size: Decimal

    @property
    def notional(self) -> Decimal:
        """What the order is worth in the quote asset."""
        return self.price * self.size

    @property
    def size_given_up(self) -> Decimal:
        """How much size the lot step cost, never negative."""
        return self.requested_size - self.size


def conform_size(instrument: Instrument, size: Decimal) -> Decimal:
    """Round a size down onto the venue's lot grid."""
    conformed = quantize_down(size, instrument.lot_step, field="lot_step")
    if conformed <= ZERO:
        raise refuse("TICK.02", f"{instrument.venue} {instrument.symbol} size {size}")
    return conformed


def conform_price(instrument: Instrument, price: Decimal, side: Side) -> Decimal:
    """Round a limit price onto the venue's tick grid, keeping it marketable.

    `side` is the side of the book being taken. Taking the asks means buying, so
    the limit goes up; taking the bids means selling, so it goes down.
    """
    if price <= ZERO:
        raise refuse("TICK.01", f"{instrument.venue} {instrument.symbol} price {price}")
    tick = instrument.tick_size
    conformed = (
        quantize_up(price, tick, field="tick_size")
        if side is Side.ASK
        else quantize_down(price, tick, field="tick_size")
    )
    if conformed <= ZERO:
        raise refuse("TICK.01", f"{instrument.venue} {instrument.symbol} price {price}")
    return conformed


def fits_notional(instrument: Instrument, notional: Decimal) -> bool:
    """True when a notional sits inside the venue's two limits."""
    return instrument.min_notional <= notional <= instrument.max_notional


def require_notional(instrument: Instrument, notional: Decimal) -> Decimal:
    """Refuse a notional the venue would bounce, naming which end it broke."""
    if notional < instrument.min_notional:
        raise refuse("TICK.03", f"{instrument.venue} {instrument.symbol} at {notional}")
    if notional > instrument.max_notional:
        raise refuse("TICK.04", f"{instrument.venue} {instrument.symbol} at {notional}")
    return notional


def conform_order(
    instrument: Instrument, side: Side, price: Decimal, size: Decimal
) -> ConformedOrder:
    """Put a priced order onto the venue's grids and check what is left of it."""
    conformed_price = conform_price(instrument, price, side)
    conformed_size = conform_size(instrument, size)
    require_notional(instrument, conformed_price * conformed_size)
    return ConformedOrder(
        side=side,
        price=conformed_price,
        size=conformed_size,
        requested_size=size,
    )


def is_conformed(instrument: Instrument, price: Decimal, size: Decimal) -> bool:
    """True when a price and a size already sit on both grids."""
    return step_multiple(price, instrument.tick_size) and step_multiple(size, instrument.lot_step)
