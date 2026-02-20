"""One order inside a plan, and what it does to the two balances it touches.

Split out of `model.plan` because a leg is the thing every other layer handles.
`store.fills` matches fills to legs, `ledger.attribution` measures drift per leg,
`report.export` writes one row per leg, and none of them wants a plan. Before the
split every one of them imported `Plan` to name a `Leg`.

The two delta properties are the ones worth reading twice. A leg that takes the
asks is a buy: the base arrives and the quote leaves. Getting that backwards is
the kind of sign error that passes every test built from the same mistake, so
they are written once here and used everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ids import Symbol, venue_code
from legvise.model.book import Side
from legvise.money import ZERO

__all__ = ["Leg"]


@dataclass(frozen=True, slots=True)
class Leg:
    """One order in a plan, priced against the book it was read from."""

    venue: str
    symbol: Symbol
    takes: Side
    price: Decimal
    size: Decimal
    fee_bps: Decimal
    fee_amount: Decimal
    levels_swept: int
    slippage_bps: Decimal

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if self.price <= ZERO:
            raise BadArgument("price", str(self.price), "a leg has a positive price")
        if self.size <= ZERO:
            raise BadArgument("size", str(self.size), "a leg has a positive size")
        if self.levels_swept < 1:
            raise BadArgument("levels_swept", self.levels_swept, "a leg touches at least one level")
        if self.slippage_bps < ZERO:
            raise BadArgument("slippage_bps", str(self.slippage_bps), "slippage is not negative")

    @property
    def notional(self) -> Decimal:
        """What the leg is worth in the quote asset."""
        return self.price * self.size

    @property
    def is_buy(self) -> bool:
        """True when this leg lifts offers."""
        return self.takes is Side.ASK

    @property
    def base_delta(self) -> Decimal:
        """How the base asset moves on this venue: positive when it arrives."""
        return self.size if self.is_buy else -self.size

    @property
    def quote_delta(self) -> Decimal:
        """How the quote asset moves on this venue: positive when it arrives."""
        return -self.notional if self.is_buy else self.notional
