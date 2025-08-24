"""A conversion cycle inside one venue: USD to BTC to ETH and back to USD.

Cross-venue arbitrage needs two venues and a transfer story. A triangular cycle
needs neither -- every leg settles on the same venue, against the same balances,
in the same second. That makes it the cheaper opportunity to act on and the
harder one to find, because the search space is every ordered loop through the
venue's currency graph rather than one pair.

The arithmetic is a product, not a sum. Three hops at 1.0004, 0.9999 and 1.0001
compound; adding their basis points is close enough at these sizes and wrong in
a way that grows, so this module multiplies.

A hop's direction decides which side of the book it takes and therefore which
way the price goes into the product. Holding the base and wanting the quote
means selling, which takes the bid at `price`. Holding the quote and wanting the
base means buying, which takes the ask at `1 / price`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ids import Symbol, asset_code, venue_code
from legvise.model.book import Side
from legvise.money import ZERO, dec

__all__ = ["Cycle", "Hop"]

ONE = dec("1")
BPS = dec("10000")


@dataclass(frozen=True, slots=True)
class Hop:
    """One conversion, on one market, in one direction."""

    from_asset: str
    to_asset: str
    symbol: Symbol
    price: Decimal

    def __post_init__(self) -> None:
        if self.from_asset != asset_code(self.from_asset):
            raise BadArgument("from_asset", self.from_asset, "asset codes are stored normalised")
        if self.to_asset != asset_code(self.to_asset):
            raise BadArgument("to_asset", self.to_asset, "asset codes are stored normalised")
        if self.from_asset == self.to_asset:
            raise BadArgument("to_asset", self.to_asset, "a hop has to change something")
        if self.price <= ZERO:
            raise BadArgument("price", str(self.price), "a hop has a positive price")
        pair = {self.symbol.base, self.symbol.quote}
        if pair != {self.from_asset, self.to_asset}:
            raise BadArgument(
                "symbol",
                str(self.symbol),
                f"does not connect {self.from_asset} to {self.to_asset}",
            )

    @property
    def takes(self) -> Side:
        """Which side of the book this hop lifts."""
        return Side.BID if self.from_asset == self.symbol.base else Side.ASK

    @property
    def is_sell(self) -> bool:
        """True when the hop sells the market's base asset."""
        return self.takes is Side.BID

    @property
    def rate(self) -> Decimal:
        """Units of `to_asset` one unit of `from_asset` converts into."""
        return self.price if self.is_sell else ONE / self.price

    def convert(self, amount: Decimal) -> Decimal:
        """What `amount` of the from asset becomes, before any fee."""
        if amount <= ZERO:
            raise BadArgument("amount", str(amount), "a hop converts a positive amount")
        return amount * self.rate


@dataclass(frozen=True, slots=True)
class Cycle:
    """A loop of hops on one venue that starts and ends at the same asset."""

    venue: str
    hops: tuple[Hop, ...]

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if len(self.hops) < 3:
            raise BadArgument("hops", len(self.hops), "a cycle is three hops or more")
        for earlier, later in zip(self.hops, self.hops[1:], strict=False):
            if earlier.to_asset != later.from_asset:
                raise BadArgument(
                    "hops",
                    f"{earlier.to_asset} then {later.from_asset}",
                    "each hop starts where the last one finished",
                )
        if self.hops[-1].to_asset != self.hops[0].from_asset:
            raise BadArgument(
                "hops", self.hops[-1].to_asset, "a cycle comes back to where it began"
            )
        visited = [hop.from_asset for hop in self.hops]
        if len(set(visited)) != len(visited):
            raise BadArgument("hops", str(visited), "a cycle visits each asset once")

    @property
    def start(self) -> str:
        """The asset the cycle begins and ends with."""
        return self.hops[0].from_asset

    @property
    def assets(self) -> tuple[str, ...]:
        """Every asset the cycle passes through, starting asset first."""
        return tuple(hop.from_asset for hop in self.hops)

    @property
    def length(self) -> int:
        """How many hops the cycle has."""
        return len(self.hops)

    @property
    def product(self) -> Decimal:
        """What one unit of the starting asset comes back as, before costs."""
        out = ONE
        for hop in self.hops:
            out = out * hop.rate
        return out

    @property
    def gross_bps(self) -> Decimal:
        """The cycle's edge before any cost, in basis points."""
        return (self.product - ONE) * BPS

    def reversed(self) -> Cycle:
        """The same loop walked the other way round.

        Only one direction of a triangle is ever profitable, and which one is
        not obvious from the assets, so a search that only tries one misses half
        the opportunities.
        """
        return Cycle(venue=self.venue, hops=tuple(reversed([_flip(h) for h in self.hops])))


def _flip(hop: Hop) -> Hop:
    return Hop(
        from_asset=hop.to_asset,
        to_asset=hop.from_asset,
        symbol=hop.symbol,
        price=hop.price,
    )
