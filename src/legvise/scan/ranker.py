"""Which of several plans to send first.

Sorting by net edge is the obvious answer and it is wrong twice over.

A plan at nine basis points on two thousand dollars is worth less than one at
four on eighty thousand, and a desk that works the list in edge order spends its
morning on the small ones. So the ranking is by **expected amount**, not by rate.

And a plan that swept eleven levels to get its size is a plan whose price is
mostly not the touch. It will fill worse than one that took two, at the same
quoted edge, because the levels behind the touch are the ones that vanish while
the order is in flight. So depth is a penalty, and it is a penalty on the edge
rather than a filter, because a wide enough edge is still worth having.

Both weights are settings rather than constants. A desk that has measured its
own fill quality should be able to say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.model.plan import Plan
from legvise.money import BPS, ONE, ZERO

__all__ = ["RankTerms", "Ranked", "rank"]


@dataclass(frozen=True, slots=True)
class RankTerms:
    """How the desk weighs one plan against another."""

    depth_penalty_bps: Decimal = ZERO
    venue_weights: dict[str, Decimal] | None = None

    def __post_init__(self) -> None:
        if self.depth_penalty_bps < ZERO:
            raise BadArgument(
                "depth_penalty_bps", str(self.depth_penalty_bps), "a penalty is not negative"
            )
        for code, weight in (self.venue_weights or {}).items():
            if weight <= ZERO:
                raise BadArgument("venue_weights", code, "a venue weight has to be positive")

    def weight_for(self, venue: str) -> Decimal:
        """How much the desk trusts a venue to fill, one being neutral."""
        return (self.venue_weights or {}).get(venue, ONE)


@dataclass(frozen=True, slots=True)
class Ranked:
    """One plan with the numbers the ranking used."""

    plan: Plan
    adjusted_bps: Decimal
    expected_amount: Decimal
    levels_swept: int

    @property
    def penalty_bps(self) -> Decimal:
        """How much the ranking took off this plan's quoted edge."""
        return self.plan.net_bps - self.adjusted_bps


def _levels(plan: Plan) -> int:
    return sum(leg.levels_swept for leg in plan.legs)


def _venue_factor(plan: Plan, terms: RankTerms) -> Decimal:
    factor = ONE
    for venue in plan.venues:
        factor = factor * terms.weight_for(venue)
    return factor


def adjusted_edge(plan: Plan, terms: RankTerms) -> Decimal:
    """The plan's net edge after the depth penalty and the venue weights.

    The penalty is charged per level **beyond the first on each leg**, because
    taking the touch is not sweeping. A two leg plan that took one level each
    pays nothing.
    """
    beyond_touch = max(_levels(plan) - len(plan.legs), 0)
    penalised = plan.net_bps - terms.depth_penalty_bps * Decimal(beyond_touch)
    return penalised * _venue_factor(plan, terms)


def rank(plans: tuple[Plan, ...], terms: RankTerms | None = None) -> tuple[Ranked, ...]:
    """Order plans by what they are actually expected to make, best first.

    Ties break on fewer levels swept, then on reference, so two runs over the
    same session produce the same list.
    """
    settings = terms or RankTerms()
    scored = [
        Ranked(
            plan=plan,
            adjusted_bps=adjusted_edge(plan, settings),
            expected_amount=adjusted_edge(plan, settings) * plan.notional / BPS,
            levels_swept=_levels(plan),
        )
        for plan in plans
        if plan.status.is_actionable
    ]
    return tuple(
        sorted(scored, key=lambda item: (-item.expected_amount, item.levels_swept, item.plan.ref))
    )


def best(plans: tuple[Plan, ...], terms: RankTerms | None = None) -> Ranked | None:
    """The plan the desk should send first, or nothing when none is sendable."""
    ordered = rank(plans, terms)
    return ordered[0] if ordered else None
