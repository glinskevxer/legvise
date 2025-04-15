"""Fee ladders, which are where most naive arbitrage models go wrong.

A venue does not have "a fee". It has a ladder of tiers keyed on trailing
thirty day volume, a different rate for taking and for making, and in several
cases a discount for paying the fee in the venue's own token. A two leg plan
crosses two ladders, and eight basis points of round trip fee against a nine
basis point gross edge is the difference between a business and a hobby.

The ladder is stored as tiers in ascending volume order. `FeeLadder` owns the
ordering rule; nothing outside it should ever sort or search these by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ids import venue_code
from legvise.money import ZERO, dec

__all__ = ["FeeLadder", "FeeTier"]


@dataclass(frozen=True, slots=True)
class FeeTier:
    """One rung: the volume that reaches it and the two rates it pays."""

    min_volume_30d: Decimal
    maker_bps: Decimal
    taker_bps: Decimal

    def __post_init__(self) -> None:
        if self.min_volume_30d < ZERO:
            raise BadArgument(
                "min_volume_30d", str(self.min_volume_30d), "a volume threshold is not negative"
            )
        if self.taker_bps < ZERO:
            raise BadArgument("taker_bps", str(self.taker_bps), "nobody is paid to take")
        if self.maker_bps < -self.taker_bps:
            raise BadArgument(
                "maker_bps",
                str(self.maker_bps),
                "a rebate deeper than the taker fee would be an arbitrage on the venue itself",
            )

    @property
    def is_rebate(self) -> bool:
        """True when resting on this tier pays rather than costs."""
        return self.maker_bps < ZERO

    @classmethod
    def build(
        cls, min_volume_30d: str | Decimal, maker_bps: str | Decimal, taker_bps: str | Decimal
    ) -> FeeTier:
        """Build a tier from loose input."""
        return cls(
            min_volume_30d=dec(min_volume_30d, field="min_volume_30d"),
            maker_bps=dec(maker_bps, field="maker_bps"),
            taker_bps=dec(taker_bps, field="taker_bps"),
        )


@dataclass(frozen=True, slots=True)
class FeeLadder:
    """Every tier a venue publishes, in ascending volume order."""

    venue: str
    tiers: tuple[FeeTier, ...]

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if not self.tiers:
            raise BadArgument("tiers", "()", "a ladder needs at least one rung")
        if self.tiers[0].min_volume_30d != ZERO:
            raise BadArgument(
                "tiers",
                str(self.tiers[0].min_volume_30d),
                "the first rung has to start at zero volume",
            )
        thresholds = [t.min_volume_30d for t in self.tiers]
        if thresholds != sorted(thresholds) or len(set(thresholds)) != len(thresholds):
            raise BadArgument("tiers", str(thresholds), "rungs go up, one threshold each")

    @property
    def base(self) -> FeeTier:
        """The rung a venue puts a new account on."""
        return self.tiers[0]

    @property
    def best(self) -> FeeTier:
        """The rung at the top of the ladder."""
        return self.tiers[-1]

    def depth(self) -> int:
        """How many rungs the ladder has."""
        return len(self.tiers)

    @classmethod
    def build(cls, venue: str, rungs: tuple[tuple[str, str, str], ...]) -> FeeLadder:
        """Build a ladder from `(volume, maker_bps, taker_bps)` triples."""
        return cls(
            venue=venue_code(venue),
            tiers=tuple(FeeTier.build(v, m, t) for v, m, t in rungs),
        )
