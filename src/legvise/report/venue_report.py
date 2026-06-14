"""Which venues are earning their place, measured over the sessions on file.

A desk connects a venue because somebody thought it would be useful and then
never asks again. The connection costs a fee ladder somebody has to keep current,
a balance somebody has to fund, and a share of the depth limit; and if the venue
turns up on one plan a month it is costing more than it makes.

So this counts, per venue: how often it appeared on an actionable plan, how much
notional went through it, and which clause refused it most. The last one is the
useful column. A venue refused twenty times on STALE.01 has a feed problem, and
one refused twenty times on DEPTH.02 is simply too thin for the size the desk
trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.model.plan import Plan, PlanStatus
from legvise.money import ZERO
from legvise.store.plans import PlanStore

__all__ = ["VenueLine", "VenueReport", "build_venue_report"]


@dataclass(frozen=True, slots=True)
class VenueLine:
    """One venue across every session the report covers."""

    venue: str
    plans: int
    actionable: int
    refused: int
    notional: Decimal
    clauses: dict[str, int]

    @property
    def hit_rate(self) -> Decimal:
        """Share of the plans this venue appeared on that were sendable."""
        if self.plans == 0:
            return ZERO
        return Decimal(self.actionable) / Decimal(self.plans)

    @property
    def worst_clause(self) -> str | None:
        """The clause that refused this venue most often, or nothing."""
        if not self.clauses:
            return None
        return max(self.clauses, key=lambda code: (self.clauses[code], code))

    @property
    def is_pulling_its_weight(self) -> bool:
        """True when the venue reached an actionable plan at all."""
        return self.actionable > 0


@dataclass(frozen=True, slots=True)
class VenueReport:
    """Every venue that appeared on a plan, busiest first."""

    lines: tuple[VenueLine, ...]

    @property
    def idle(self) -> tuple[str, ...]:
        """Venues that never reached an actionable plan."""
        return tuple(line.venue for line in self.lines if not line.is_pulling_its_weight)

    @property
    def busiest(self) -> VenueLine | None:
        """The venue that carried the most notional."""
        return self.lines[0] if self.lines else None

    def line_for(self, venue: str) -> VenueLine | None:
        """One venue's line, or nothing when it never appeared."""
        for line in self.lines:
            if line.venue == venue:
                return line
        return None


def _fold(plans: tuple[Plan, ...]) -> dict[str, VenueLine]:
    found: dict[str, VenueLine] = {}
    for plan in plans:
        for venue in plan.venues:
            line = found.get(
                venue,
                VenueLine(
                    venue=venue,
                    plans=0,
                    actionable=0,
                    refused=0,
                    notional=ZERO,
                    clauses={},
                ),
            )
            clauses = dict(line.clauses)
            if plan.clause is not None:
                clauses[plan.clause] = clauses.get(plan.clause, 0) + 1
            found[venue] = VenueLine(
                venue=venue,
                plans=line.plans + 1,
                actionable=line.actionable + (1 if plan.status.is_actionable else 0),
                refused=line.refused + (1 if plan.status is PlanStatus.REFUSED else 0),
                notional=line.notional + (plan.notional if plan.status.is_actionable else ZERO),
                clauses=clauses,
            )
    return found


def build_venue_report(store: PlanStore, *, sessions: int = 20) -> VenueReport:
    """Fold the last `sessions` sessions into one line per venue."""
    plans: list[Plan] = []
    for row in store.sessions(limit=sessions):
        plans.extend(store.for_session(row.ref))
    folded = _fold(tuple(plans))
    return VenueReport(
        lines=tuple(
            sorted(folded.values(), key=lambda line: (-line.notional, -line.plans, line.venue))
        )
    )
