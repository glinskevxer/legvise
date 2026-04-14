"""Where the desk's inventory is against where it wants to be.

The `inventory show` command answers "what is on file". This answers the harder
question, which is "what would have to move, and in which direction, to put
every asset back on its target".

The number that matters is the **net move**: for one asset across every venue,
the surpluses and the deficits mostly cancel, and what is left is the amount
that actually has to be bought or sold rather than transferred. A desk that
reads the per venue gaps and not the net one arranges four transfers where two
would have done.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.model.inventory import Band, Position
from legvise.money import ZERO
from legvise.risk.bands import room_for

__all__ = ["AssetPlan", "InventoryReport", "VenueGap", "build_inventory_report"]


@dataclass(frozen=True, slots=True)
class VenueGap:
    """One asset on one venue, and how far it is from its target."""

    venue: str
    asset: str
    held: Decimal
    target: Decimal
    state: str

    @property
    def gap(self) -> Decimal:
        """Positive when the venue is long of its target."""
        return self.held - self.target

    @property
    def needs_moving(self) -> bool:
        """True when the venue is anywhere other than its target."""
        return self.gap != ZERO


@dataclass(frozen=True, slots=True)
class AssetPlan:
    """One asset across every venue, and what it would take to square it."""

    asset: str
    gaps: tuple[VenueGap, ...]

    @property
    def surplus(self) -> Decimal:
        """Everything held above target, added up."""
        return sum((gap.gap for gap in self.gaps if gap.gap > ZERO), start=ZERO)

    @property
    def deficit(self) -> Decimal:
        """Everything held below target, added up as a positive number."""
        return -sum((gap.gap for gap in self.gaps if gap.gap < ZERO), start=ZERO)

    @property
    def transferable(self) -> Decimal:
        """How much of the gap can be closed by moving inventory around."""
        return min(self.surplus, self.deficit)

    @property
    def net_move(self) -> Decimal:
        """What is left after the transfers. Positive means sell, negative buy."""
        return self.surplus - self.deficit

    @property
    def is_square(self) -> bool:
        """True when every venue is on its target."""
        return self.surplus == ZERO and self.deficit == ZERO


@dataclass(frozen=True, slots=True)
class InventoryReport:
    """Every asset the desk holds, and what squaring it would take."""

    plans: tuple[AssetPlan, ...]

    @property
    def out_of_band(self) -> tuple[VenueGap, ...]:
        """Every venue and asset outside its band, worst first."""
        found = [gap for plan in self.plans for gap in plan.gaps if gap.state != "in band"]
        return tuple(sorted(found, key=lambda gap: (gap.state, gap.venue, gap.asset)))

    @property
    def needs_transfers(self) -> tuple[AssetPlan, ...]:
        """Assets where moving inventory would close part of the gap."""
        return tuple(plan for plan in self.plans if plan.transferable > ZERO)

    def plan_for(self, asset: str) -> AssetPlan | None:
        """One asset's plan, or nothing when the desk holds none of it."""
        for plan in self.plans:
            if plan.asset == asset:
                return plan
        return None


def _state(position: Position, band: Band | None) -> str:
    if band is None:
        return "no band"
    room = room_for(position, band)
    if room.is_below_floor:
        return "under floor"
    if room.is_above_ceiling:
        return "over ceiling"
    return "in band"


def build_inventory_report(
    positions: tuple[Position, ...], bands: dict[tuple[str, str], Band]
) -> InventoryReport:
    """Collapse the desk's positions and bands into one report.

    A position with no band contributes a gap of nothing rather than being
    dropped: an asset nobody has set a policy for is worth seeing on the page.
    """
    by_asset: dict[str, list[VenueGap]] = {}
    for position in sorted(positions, key=lambda item: item.key):
        band = bands.get(position.key)
        by_asset.setdefault(position.asset, []).append(
            VenueGap(
                venue=position.venue,
                asset=position.asset,
                held=position.total,
                target=band.target if band else position.total,
                state=_state(position, band),
            )
        )
    return InventoryReport(
        plans=tuple(
            AssetPlan(asset=asset, gaps=tuple(gaps)) for asset, gaps in sorted(by_asset.items())
        )
    )
