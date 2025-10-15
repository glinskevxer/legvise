"""Expected against realised, across every plan that got a fill.

One plan's attribution is an anecdote. This is the same arithmetic aggregated,
which is where it starts being management information: if price drift is two
basis points on every plan across a month, that is a latency budget nobody has
funded, and it is invisible one plan at a time.

Aggregation is notional weighted, not plan weighted. A hundred plans of two
thousand dollars and one of four hundred thousand are not one hundred and one
equal opinions, and averaging their basis points as if they were is the most
common way a report like this ends up saying nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ledger.attribution import Attribution, attribute
from legvise.model.plan import Plan
from legvise.money import ZERO
from legvise.store.fills import FillStore
from legvise.store.plans import PlanStore

__all__ = ["EdgeReport", "PlanLine", "build_edge_report"]


@dataclass(frozen=True, slots=True)
class PlanLine:
    """One plan and what it turned into."""

    plan: Plan
    attribution: Attribution

    @property
    def weight(self) -> Decimal:
        """The notional this line carries into the aggregate."""
        return self.plan.notional


@dataclass(frozen=True, slots=True)
class EdgeReport:
    """Every plan with a fill, and the weighted picture across them."""

    lines: tuple[PlanLine, ...]

    @property
    def plans(self) -> int:
        """How many plans the report covers."""
        return len(self.lines)

    @property
    def total_notional(self) -> Decimal:
        """The notional behind the whole report."""
        return sum((line.weight for line in self.lines), start=ZERO)

    @property
    def expected_bps(self) -> Decimal:
        """Notional weighted expected edge."""
        return self._weighted(lambda line: line.attribution.expected_bps)

    @property
    def realised_bps(self) -> Decimal:
        """Notional weighted realised edge."""
        return self._weighted(lambda line: line.attribution.realised_bps)

    @property
    def price_drift_bps(self) -> Decimal:
        """Notional weighted price drift."""
        return self._weighted(lambda line: line.attribution.price_drift_bps)

    @property
    def fee_drift_bps(self) -> Decimal:
        """Notional weighted fee drift."""
        return self._weighted(lambda line: line.attribution.fee_drift_bps)

    @property
    def gap_bps(self) -> Decimal:
        """How much of the expected edge did not arrive, weighted."""
        return self.expected_bps - self.realised_bps

    @property
    def leg_risk_plans(self) -> tuple[str, ...]:
        """Every plan that ended up one sided."""
        return tuple(line.plan.ref for line in self.lines if line.attribution.has_leg_risk)

    @property
    def realised_amount(self) -> Decimal:
        """What the realised edge comes to in the quote asset."""
        return sum(
            (line.attribution.realised_bps * line.weight / Decimal(10000) for line in self.lines),
            start=ZERO,
        )

    def _weighted(self, pick: Callable[[PlanLine], Decimal]) -> Decimal:
        total = self.total_notional
        if total == ZERO:
            return ZERO
        weighted = sum((pick(line) * line.weight for line in self.lines), start=ZERO)
        return weighted / total


def build_edge_report(
    plans: PlanStore, fills: FillStore, *, session_ref: str | None = None, limit: int = 200
) -> EdgeReport:
    """Build the report over one session, or over every plan that has a fill."""
    if limit <= 0:
        raise BadArgument("limit", limit, "a report covers at least one plan")
    refs = (
        [p.ref for p in plans.for_session(session_ref)]
        if session_ref is not None
        else list(fills.plans_with_fills(limit=limit))
    )
    lines: list[PlanLine] = []
    for ref in refs:
        plan = plans.get(ref)
        results = fills.results_for(plan)
        if not any(result.outcome.traded for result in results):
            continue
        lines.append(PlanLine(plan=plan, attribution=attribute(plan, results)))
    return EdgeReport(lines=tuple(lines))
