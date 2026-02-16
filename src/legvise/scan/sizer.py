"""How big a plan can be, which is the smallest of four unrelated answers.

Four constraints, none of which knows about the others:

1. the **book** on each venue, which is the only one that changes by the second
2. the **inventory band** on each venue, which is the desk's own policy
3. the **exposure caps**, which are the desk's other policy and are measured in
   quote notional rather than base size
4. the **venue filters**, which round the answer onto a grid and then have their
   own opinion about whether what is left is big enough

The order matters. Caps are a notional and the other three are a base size, so
the cap has to be converted with a price, and the price is only known once the
book has been walked -- which means the walk happens against the smaller of the
first two, and the cap trims afterwards. Doing it the other way round prices the
cap conversion off a size the book cannot fill.

The conformance step goes last on purpose. Rounding down to the lot step can
only ever shrink the answer, and shrinking after the caps have run is safe;
shrinking before means the caps trim a size that no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.market.depth import reachable, walk
from legvise.market.normalize import conform_size, require_notional
from legvise.market.sweep import Sweep
from legvise.model.book import Book, Side
from legvise.model.instrument import Instrument
from legvise.model.inventory import Band, Position
from legvise.money import ZERO
from legvise.risk.bands import room_to_receive, room_to_spend
from legvise.risk.caps import CapSet, trim_to_caps
from legvise.rules import refuse

__all__ = ["SizeLimit", "Sizing", "size_leg"]


@dataclass(frozen=True, slots=True)
class SizeLimit:
    """One constraint's answer, in base units, and what it was."""

    name: str
    clause: str
    size: Decimal


@dataclass(frozen=True, slots=True)
class Sizing:
    """The size that survived, the sweep that priced it, and what bound it."""

    size: Decimal
    sweep: Sweep
    bound_by: str
    limits: tuple[SizeLimit, ...]

    @property
    def notional(self) -> Decimal:
        """The quote notional the sized leg comes to."""
        return self.sweep.notional


def _tightest(limits: tuple[SizeLimit, ...]) -> SizeLimit:
    return min(limits, key=lambda limit: limit.size)


def size_leg(
    book: Book,
    instrument: Instrument,
    *,
    side: Side,
    depth_limit_bps: Decimal,
    spending: Position,
    spending_band: Band,
    receiving: Position,
    receiving_band: Band,
    caps: CapSet,
    wanted: Decimal,
) -> Sizing:
    """Work out how much of `wanted` this venue can actually take.

    `side` is the side of the book being taken. `spending` is the balance that
    goes down and `receiving` is the one that goes up, which is the base and the
    quote the other way round depending on which side this is.
    """
    if wanted <= ZERO:
        raise BadArgument("wanted", str(wanted), "sizing needs something to size")

    within = reachable(book, side, depth_limit_bps)
    if within.is_empty:
        raise refuse("DEPTH.01", f"{book.venue} {book.symbol} {side.value} has nothing reachable")

    limits = (
        SizeLimit("wanted", "", wanted),
        SizeLimit("depth", "DEPTH.02", within.size),
        SizeLimit("floor", "BAND.01", _spendable_in_base(book, side, spending, spending_band)),
        SizeLimit("ceiling", "BAND.02", _receivable_in_base(book, side, receiving, receiving_band)),
    )
    first_pass = _tightest(limits)
    if first_pass.size <= ZERO:
        raise refuse(first_pass.clause or "DEPTH.01", f"{book.venue} {book.symbol} sizes to zero")

    priced = walk(book, side, first_pass.size)
    trimmed = trim_to_caps(caps, priced.notional, subject=f"{book.venue} {book.symbol}")
    size = first_pass.size
    bound = first_pass.name
    if trimmed.was_trimmed:
        size = first_pass.size * trimmed.allowed / priced.notional
        bound = trimmed.bound_by or "CAP.01"

    conformed = conform_size(instrument, size)
    final = walk(book, side, conformed)
    require_notional(instrument, final.notional)
    return Sizing(size=conformed, sweep=final, bound_by=bound, limits=limits)


def _spendable_in_base(book: Book, side: Side, position: Position, band: Band) -> Decimal:
    """Room under the floor, converted into base units of this market."""
    room = room_to_spend(position, band)
    if side is Side.BID:
        return room
    return room / book.touch(side).price


def _receivable_in_base(book: Book, side: Side, position: Position, band: Band) -> Decimal:
    """Room under the ceiling, converted into base units of this market."""
    room = room_to_receive(position, band)
    if side is Side.ASK:
        return room
    return room / book.touch(side).price
