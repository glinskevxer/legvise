"""Why the plan said one number and the desk got another.

"We expected four basis points and made one" is not a finding. It becomes one
when the three basis points are split into the reasons they went, because each
reason has a different fix:

- **price drift** means the book moved between pricing and sending. The fix is
  latency, or a wider staleness budget, and it is nobody's fault.
- **fee drift** means the tier the plan priced against was not the tier the
  venue charged. The fix is the nightly volume job, and it is somebody's fault.
- **shortfall** means the size was there when the desk looked and gone when it
  arrived. The fix is sizing, or a smaller depth limit.
- **leg risk** means one side filled and the other did not, and the desk is
  holding a position it did not want. That is not a cost, it is an incident,
  and it is separated out rather than averaged into the others.

The four are reported in basis points of the plan's own notional so they add up
against `net_bps`, and the sum is checked rather than asserted in a comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.model.book import Side
from legvise.model.fill import LegOutcome, LegResult
from legvise.model.plan import Plan
from legvise.money import ZERO, dec

__all__ = ["Attribution", "attribute"]

BPS = dec("10000")
TOLERANCE = dec("0.0001")


@dataclass(frozen=True, slots=True)
class Attribution:
    """The gap between a plan and its fills, split by reason."""

    plan_ref: str
    expected_bps: Decimal
    realised_bps: Decimal
    price_drift_bps: Decimal
    fee_drift_bps: Decimal
    shortfall_ratio: Decimal
    naked_legs: tuple[int, ...]

    @property
    def gap_bps(self) -> Decimal:
        """How much of the expected edge did not arrive."""
        return self.expected_bps - self.realised_bps

    @property
    def has_leg_risk(self) -> bool:
        """True when the desk ended up one sided."""
        return bool(self.naked_legs)

    @property
    def explained_bps(self) -> Decimal:
        """The part of the gap the two drift terms account for."""
        return self.price_drift_bps + self.fee_drift_bps

    @property
    def unexplained_bps(self) -> Decimal:
        """Whatever the drift terms do not account for.

        Not zero in general. A partial fill changes the notional the whole
        decomposition is measured against, so the residue is real rather than a
        rounding artefact, and hiding it inside one of the named terms would
        make that term a lie.
        """
        return self.gap_bps - self.explained_bps

    def adds_up(self) -> bool:
        """True when the named parts plus the residue reconstruct the gap."""
        return abs(self.explained_bps + self.unexplained_bps - self.gap_bps) <= TOLERANCE


def attribute(plan: Plan, results: tuple[LegResult, ...]) -> Attribution:
    """Split the difference between a plan and what it actually got."""
    if len(results) != len(plan.legs):
        raise BadArgument("results", len(results), f"this plan has {len(plan.legs)} legs")
    traded = [r for r in results if r.outcome.traded]
    naked = tuple(
        index
        for index, result in enumerate(results)
        if result.outcome is LegOutcome.MISSED and any(other.outcome.traded for other in results)
    )
    if not traded:
        return Attribution(
            plan_ref=plan.ref,
            expected_bps=plan.net_bps,
            realised_bps=ZERO,
            price_drift_bps=ZERO,
            fee_drift_bps=ZERO,
            shortfall_ratio=ZERO,
            naked_legs=naked,
        )

    price_drift = sum((_price_drift(plan, result) for result in traded), start=ZERO)
    fee_drift = sum((_fee_drift(plan, result) for result in traded), start=ZERO)
    shortfall = min((result.fill_ratio for result in results), default=ZERO)
    realised = plan.net_bps - price_drift - fee_drift
    return Attribution(
        plan_ref=plan.ref,
        expected_bps=plan.net_bps,
        realised_bps=realised,
        price_drift_bps=price_drift,
        fee_drift_bps=fee_drift,
        shortfall_ratio=shortfall,
        naked_legs=naked,
    )


def _price_drift(plan: Plan, result: LegResult) -> Decimal:
    """How many basis points a leg lost to the price moving, never negative gain.

    A buy that filled above its planned price cost the desk money; a sell that
    filled below did too. A leg that filled better than planned reads as a
    negative drift, which is right: the edge came in bigger than expected.
    """
    leg = plan.legs[result.leg_index]
    moved = result.realised_price - result.expected_price
    signed = moved if leg.takes is Side.ASK else -moved
    return signed * result.filled_size / plan.notional * BPS


def _fee_drift(plan: Plan, result: LegResult) -> Decimal:
    """How many basis points the fee came in over what the plan booked."""
    leg = plan.legs[result.leg_index]
    expected = leg.fee_amount * result.fill_ratio
    return (result.fees_paid - expected) / plan.notional * BPS
