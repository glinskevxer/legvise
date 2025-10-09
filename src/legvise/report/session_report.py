"""What one scan session came to, in the shape a desk actually reads it.

The useful summary of a session is not "twelve plans". It is which clauses did
the refusing, because that is the only number that tells an operator what to
change. Three EDGE.01 refusals means the market was quiet. Three CAP.01
refusals means the desk is at its own limit and the market had nothing to do
with it, and those two look identical in a plan count.

Nothing here computes an edge. It reads what the scanner already wrote down,
which is the point: a report that recomputes is a second implementation, and a
second implementation drifts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.ids import Symbol
from legvise.model.plan import Plan, PlanStatus
from legvise.money import ZERO
from legvise.rules import clause
from legvise.store.plans import PlanStore

__all__ = ["ClauseLine", "SessionSummary", "summarise"]


@dataclass(frozen=True, slots=True)
class ClauseLine:
    """One clause and how often it fired, with the words spelled out."""

    code: str
    hits: int
    text: str


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """One session, collapsed."""

    session: str
    started_at: str
    min_edge_bps: Decimal
    plans: int
    actionable: int
    refused: int
    trimmed: int
    symbols: tuple[Symbol, ...]
    venues: tuple[str, ...]
    best_net_bps: Decimal | None
    total_notional: Decimal
    clauses: tuple[ClauseLine, ...]

    @property
    def hit_rate(self) -> Decimal:
        """Share of plans that came out actionable."""
        if self.plans == 0:
            return ZERO
        return Decimal(self.actionable) / Decimal(self.plans)

    @property
    def busiest_clause(self) -> ClauseLine | None:
        """The clause that did the most refusing, or nothing."""
        return self.clauses[0] if self.clauses else None


def summarise(store: PlanStore, session_ref: str) -> SessionSummary:
    """Read one session out of the store and collapse it."""
    row = store.session(session_ref)
    plans = store.for_session(session_ref)
    actionable = [p for p in plans if p.status.is_actionable]
    counts = store.refusal_counts(session_ref)
    return SessionSummary(
        session=session_ref,
        started_at=row.started_at,
        min_edge_bps=row.min_edge_bps,
        plans=len(plans),
        actionable=len(actionable),
        refused=sum(1 for p in plans if p.status is PlanStatus.REFUSED),
        trimmed=sum(1 for p in plans if p.status is PlanStatus.TRIMMED),
        symbols=store.symbols_seen(session_ref),
        venues=_venues(plans),
        best_net_bps=max((p.net_bps for p in actionable), default=None),
        total_notional=sum((p.notional for p in actionable), start=ZERO),
        clauses=tuple(
            ClauseLine(code=code, hits=hits, text=clause(code).text)
            for code, hits in counts.items()
        ),
    )


def _venues(plans: tuple[Plan, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    for plan in plans:
        seen.update(plan.venues)
    return tuple(sorted(seen))


def compare(first: SessionSummary, second: SessionSummary) -> dict[str, Decimal]:
    """How two sessions differ on the numbers worth watching.

    Positive means the second session did more of it. Used to answer "did the
    change help", which is a question that gets asked far more often than it
    gets answered with a number.
    """
    return {
        "plans": Decimal(second.plans - first.plans),
        "actionable": Decimal(second.actionable - first.actionable),
        "refused": Decimal(second.refused - first.refused),
        "hit_rate": second.hit_rate - first.hit_rate,
        "notional": second.total_notional - first.total_notional,
    }
