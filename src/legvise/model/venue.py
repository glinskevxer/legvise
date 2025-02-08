"""A venue, and the three numbers the desk keeps about it beyond its name.

The staleness budget is per venue because feeds differ. A venue on a colocated
websocket earns a tight budget; one behind a rate limited REST poll gets a loose
one, and a loose budget is a real cost -- it widens the window in which the
book the scanner priced against has already moved.

The depth limit is how far into the book the desk is willing to sweep, measured
in basis points away from the touch rather than in levels, because a level is
not a unit: one venue's level three is another's level thirty.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ids import venue_code
from legvise.money import ZERO, dec

__all__ = ["Venue"]


@dataclass(frozen=True, slots=True)
class Venue:
    """One exchange the desk holds inventory on."""

    code: str
    display_name: str
    staleness_budget_ms: int
    depth_limit_bps: Decimal
    notional_cap: Decimal
    pays_maker_rebate: bool
    active: bool

    def __post_init__(self) -> None:
        if self.code != venue_code(self.code):
            raise BadArgument("code", self.code, "venue codes are stored normalised")
        if not self.display_name.strip():
            raise BadArgument("display_name", self.display_name, "a venue needs a name")
        if self.staleness_budget_ms <= 0:
            raise BadArgument(
                "staleness_budget_ms",
                self.staleness_budget_ms,
                "a budget of zero means no book is ever tradable",
            )
        if self.depth_limit_bps <= ZERO:
            raise BadArgument(
                "depth_limit_bps",
                str(self.depth_limit_bps),
                "a depth limit of zero leaves no book to sweep",
            )
        if self.notional_cap <= ZERO:
            raise BadArgument(
                "notional_cap",
                str(self.notional_cap),
                "a cap of zero means the venue is off, not capped",
            )

    @classmethod
    def build(
        cls,
        code: str,
        display_name: str,
        *,
        staleness_budget_ms: int,
        depth_limit_bps: str | Decimal,
        notional_cap: str | Decimal,
        pays_maker_rebate: bool = False,
        active: bool = True,
    ) -> Venue:
        """Build a venue from loose input, normalising as it goes."""
        return cls(
            code=venue_code(code),
            display_name=display_name.strip(),
            staleness_budget_ms=staleness_budget_ms,
            depth_limit_bps=dec(depth_limit_bps, field="depth_limit_bps"),
            notional_cap=dec(notional_cap, field="notional_cap"),
            pays_maker_rebate=pays_maker_rebate,
            active=active,
        )

    def deactivated(self) -> Venue:
        """The same venue, switched off."""
        return self.replacing(active=False)

    def replacing(self, **changes: object) -> Venue:
        """A copy with some fields changed, revalidated on the way through."""
        fields = {
            "code": self.code,
            "display_name": self.display_name,
            "staleness_budget_ms": self.staleness_budget_ms,
            "depth_limit_bps": self.depth_limit_bps,
            "notional_cap": self.notional_cap,
            "pays_maker_rebate": self.pays_maker_rebate,
            "active": self.active,
        }
        unknown = set(changes) - set(fields)
        if unknown:
            raise BadArgument("field", sorted(unknown)[0], "a venue has no such field")
        fields.update(changes)
        return Venue(**fields)  # type: ignore[arg-type]
