"""What the desk thinks it holds against what the venue says it holds.

The balances in `store.inventory` are whatever the last reconciliation job wrote.
Between runs they drift: a fill the desk never saw, a fee charged in an asset
nobody was tracking, a withdrawal that landed while the job was not looking. The
drift is small and it compounds, and the first thing it breaks is sizing, quietly
and in the direction of trading more than the desk actually has.

So a reconciliation is a comparison, not an overwrite. It produces a list of
differences with a tolerance, and the operator decides what to do about them.
The tolerance is per asset because a dust threshold that makes sense for BTC is
absurd for USDT.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.model.inventory import Position
from legvise.money import ZERO

__all__ = ["Difference", "Reconciliation", "reconcile"]

DEFAULT_TOLERANCE = Decimal("0")


@dataclass(frozen=True, slots=True)
class Difference:
    """One balance the desk and the venue disagree about."""

    venue: str
    asset: str
    ours: Decimal
    theirs: Decimal
    tolerance: Decimal

    @property
    def drift(self) -> Decimal:
        """How far the venue is from the desk's record. Positive means more."""
        return self.theirs - self.ours

    @property
    def is_material(self) -> bool:
        """True when the drift is bigger than the asset's tolerance."""
        return abs(self.drift) > self.tolerance

    @property
    def direction(self) -> str:
        """Which way the drift goes, in words an operator can act on."""
        if self.drift > ZERO:
            return "venue holds more"
        if self.drift < ZERO:
            return "venue holds less"
        return "agreed"


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """Every difference between one snapshot and the desk's record."""

    differences: tuple[Difference, ...]

    @property
    def material(self) -> tuple[Difference, ...]:
        """The differences worth acting on."""
        return tuple(item for item in self.differences if item.is_material)

    @property
    def agrees(self) -> bool:
        """True when nothing material differs."""
        return not self.material

    @property
    def missing_from_ours(self) -> tuple[Difference, ...]:
        """Balances the venue reports that the desk has no record of."""
        return tuple(item for item in self.differences if item.ours == ZERO and item.theirs > ZERO)

    @property
    def missing_from_theirs(self) -> tuple[Difference, ...]:
        """Balances the desk records that the venue does not report."""
        return tuple(item for item in self.differences if item.theirs == ZERO and item.ours > ZERO)

    def worst(self) -> Difference | None:
        """The biggest material drift, or nothing when everything agrees."""
        found = self.material
        if not found:
            return None
        return max(found, key=lambda item: (abs(item.drift), item.venue, item.asset))


def reconcile(
    ours: tuple[Position, ...],
    theirs: dict[tuple[str, str], Decimal],
    tolerances: dict[str, Decimal] | None = None,
) -> Reconciliation:
    """Compare the desk's positions against a snapshot keyed by venue and asset.

    Every key on either side appears in the result, including the ones only one
    side knows about. A balance the desk has no row for is the interesting case
    and dropping it would make the report useless.
    """
    limits = tolerances or {}
    for asset, allowed in limits.items():
        if allowed < ZERO:
            raise BadArgument("tolerances", asset, "a tolerance is not negative")
    recorded = {position.key: position.total for position in ours}
    keys = sorted(set(recorded) | set(theirs))
    found = tuple(
        Difference(
            venue=venue,
            asset=asset,
            ours=recorded.get((venue, asset), ZERO),
            theirs=theirs.get((venue, asset), ZERO),
            tolerance=limits.get(asset, DEFAULT_TOLERANCE),
        )
        for venue, asset in keys
    )
    return Reconciliation(differences=found)
