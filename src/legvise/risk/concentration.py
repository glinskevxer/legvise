"""How much of the desk is in one asset, and how much of that is on one venue.

The exposure caps in `risk.caps` are absolute: this venue may hold this much
notional. Concentration is the other question, and the caps cannot answer it. A
desk inside every absolute cap can still be ninety percent in one asset, or hold
its entire position in that asset on the venue with the worst withdrawal record,
and both of those are the kind of thing that is obvious afterwards.

Two ratios, both measured against the desk's total marked value:

- **asset share** is what fraction of the desk one asset is
- **venue share** is what fraction of one asset sits on one venue

A limit on the first stops the desk becoming a directional bet by accident. A
limit on the second stops the desk being unable to trade an asset because the
only venue holding it has suspended withdrawals.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.model.inventory import Position
from legvise.money import ZERO, dec
from legvise.rules import refuse

__all__ = ["Concentration", "ConcentrationLimits", "measure"]

ONE = dec("1")


@dataclass(frozen=True, slots=True)
class ConcentrationLimits:
    """The two shares the desk will not go past."""

    most_of_desk_in_one_asset: Decimal
    most_of_an_asset_on_one_venue: Decimal

    def __post_init__(self) -> None:
        for name, value in (
            ("most_of_desk_in_one_asset", self.most_of_desk_in_one_asset),
            ("most_of_an_asset_on_one_venue", self.most_of_an_asset_on_one_venue),
        ):
            if not ZERO < value <= ONE:
                raise BadArgument(name, str(value), "a share sits above zero and at most one")


@dataclass(frozen=True, slots=True)
class Concentration:
    """What the desk is actually holding, as shares."""

    total_value: Decimal
    by_asset: dict[str, Decimal]
    by_asset_venue: dict[tuple[str, str], Decimal]

    def asset_share(self, asset: str) -> Decimal:
        """What fraction of the desk one asset is."""
        if self.total_value <= ZERO:
            return ZERO
        return self.by_asset.get(asset, ZERO) / self.total_value

    def venue_share(self, asset: str, venue: str) -> Decimal:
        """What fraction of one asset sits on one venue."""
        held = self.by_asset.get(asset, ZERO)
        if held <= ZERO:
            return ZERO
        return self.by_asset_venue.get((asset, venue), ZERO) / held

    @property
    def busiest_asset(self) -> str | None:
        """The asset the desk holds most of, by value."""
        if not self.by_asset:
            return None
        return max(self.by_asset, key=lambda asset: (self.by_asset[asset], asset))


def measure(positions: tuple[Position, ...], marks: dict[str, Decimal]) -> Concentration:
    """Value every position and collapse it into the two share tables.

    `marks` prices each asset in the desk's reporting currency. An asset with no
    mark is refused rather than valued at zero: a position nobody can price is
    the position most likely to be the problem.
    """
    by_asset: dict[str, Decimal] = {}
    by_pair: dict[tuple[str, str], Decimal] = {}
    total = ZERO
    for position in positions:
        mark = marks.get(position.asset)
        if mark is None:
            raise BadArgument("marks", position.asset, "no mark price for a held asset")
        if mark < ZERO:
            raise BadArgument("marks", str(mark), "a mark price is not negative")
        value = position.total * mark
        by_asset[position.asset] = by_asset.get(position.asset, ZERO) + value
        key = (position.asset, position.venue)
        by_pair[key] = by_pair.get(key, ZERO) + value
        total += value
    return Concentration(total_value=total, by_asset=by_asset, by_asset_venue=by_pair)


def require_within(found: Concentration, limits: ConcentrationLimits) -> Concentration:
    """Refuse a desk that is past either share limit."""
    for asset in sorted(found.by_asset):
        share = found.asset_share(asset)
        if share > limits.most_of_desk_in_one_asset:
            raise refuse(
                "CAP.02",
                f"{asset} is {share} of the desk against {limits.most_of_desk_in_one_asset}",
            )
    for asset, venue in sorted(found.by_asset_venue):
        share = found.venue_share(asset, venue)
        if share > limits.most_of_an_asset_on_one_venue:
            raise refuse(
                "CAP.02",
                f"{share} of the desk's {asset} is on {venue}"
                f" against {limits.most_of_an_asset_on_one_venue}",
            )
    return found
