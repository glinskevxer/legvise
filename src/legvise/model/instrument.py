"""A market on one venue, and the four filters an order has to satisfy on it.

Every venue publishes these under a different name -- tick size, price
increment, quote increment; lot step, base increment, step size -- and the desk
stores its own four. An order that breaks any of them is rejected by the venue
after the round trip, which on an arbitrage leg means the other leg is already
filled and the desk is naked. So they are checked here, before anything is sent.

`venue_symbol` is the venue's own spelling, carried along for whoever writes the
order out. Nothing in the pricing path reads it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ids import Symbol, parse_symbol, venue_code
from legvise.money import ZERO, dec

__all__ = ["Instrument"]


@dataclass(frozen=True, slots=True)
class Instrument:
    """One tradable market, on one venue, with the venue's filters attached."""

    venue: str
    symbol: Symbol
    venue_symbol: str
    tick_size: Decimal
    lot_step: Decimal
    min_notional: Decimal
    max_notional: Decimal
    active: bool

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if not self.venue_symbol.strip():
            raise BadArgument("venue_symbol", self.venue_symbol, "the venue calls it something")
        for name, value in (
            ("tick_size", self.tick_size),
            ("lot_step", self.lot_step),
            ("min_notional", self.min_notional),
        ):
            if value <= ZERO:
                raise BadArgument(name, str(value), "has to be positive")
        if self.max_notional <= self.min_notional:
            raise BadArgument(
                "max_notional",
                str(self.max_notional),
                "the maximum has to leave room above the minimum",
            )

    @property
    def base(self) -> str:
        """The asset being bought or sold."""
        return self.symbol.base

    @property
    def quote(self) -> str:
        """The asset the price is denominated in."""
        return self.symbol.quote

    @property
    def key(self) -> tuple[str, str]:
        """The pair of strings the store keys on."""
        return (self.venue, str(self.symbol))

    @classmethod
    def build(
        cls,
        venue: str,
        symbol: str,
        *,
        venue_symbol: str | None = None,
        tick_size: str | Decimal,
        lot_step: str | Decimal,
        min_notional: str | Decimal,
        max_notional: str | Decimal,
        active: bool = True,
    ) -> Instrument:
        """Build an instrument from loose input, normalising as it goes.

        A venue spelling that is not given defaults to the desk's, which is right
        for the venues that already use `BASE-QUOTE` and wrong for the rest --
        those have to say so.
        """
        parsed = parse_symbol(symbol)
        return cls(
            venue=venue_code(venue),
            symbol=parsed,
            venue_symbol=(venue_symbol or str(parsed)).strip(),
            tick_size=dec(tick_size, field="tick_size"),
            lot_step=dec(lot_step, field="lot_step"),
            min_notional=dec(min_notional, field="min_notional"),
            max_notional=dec(max_notional, field="max_notional"),
            active=active,
        )
