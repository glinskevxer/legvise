"""A priced opportunity, its legs, and the arithmetic that has to add up.

A plan is the unit the desk looks at, argues about and later grades itself
against. It carries every number that went into the decision, not just the
answer, because "net edge 3.1 bps" tells nobody anything six weeks later when
the fill came back at 0.4.

The legs themselves live in `model.leg`. Everything downstream handles legs and
only the scanner handles whole plans.

The edge decomposition is fixed and it is checked, not assumed:

    net = gross - fees - slippage - rebalance

`net_bps` is stored rather than derived so a plan read back from the store is
exactly the number the desk acted on, even if the arithmetic here changes. The
consistency check is a method, run when a plan is built and again by the
verifier, rather than a property that silently recomputes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from legvise.errors import BadArgument
from legvise.ids import Symbol
from legvise.model.leg import Leg
from legvise.money import ZERO

__all__ = ["Plan", "PlanKind", "PlanStatus"]

TOLERANCE_BPS = Decimal("0.0001")


class PlanKind(str, Enum):
    """What shape of opportunity this is."""

    CROSS_VENUE = "cross_venue"
    TRIANGULAR = "triangular"


class PlanStatus(str, Enum):
    """Where a plan got to."""

    PRICED = "priced"
    TRIMMED = "trimmed"
    REFUSED = "refused"

    @property
    def is_actionable(self) -> bool:
        """True when the desk could send this."""
        return self in (PlanStatus.PRICED, PlanStatus.TRIMMED)


@dataclass(frozen=True, slots=True)
class Plan:
    """A whole opportunity, priced end to end."""

    ref: str
    kind: PlanKind
    symbol: Symbol
    legs: tuple[Leg, ...]
    notional: Decimal
    gross_bps: Decimal
    fee_bps: Decimal
    slippage_bps: Decimal
    rebalance_bps: Decimal
    net_bps: Decimal
    status: PlanStatus
    clause: str | None = None

    def __post_init__(self) -> None:
        if len(self.legs) < 2:
            raise BadArgument("legs", len(self.legs), "a plan has at least two legs")
        if self.notional <= ZERO:
            raise BadArgument("notional", str(self.notional), "a plan has a positive notional")
        if self.status is PlanStatus.REFUSED and self.clause is None:
            raise BadArgument("clause", None, "a refused plan names the clause that refused it")
        if self.status is not PlanStatus.REFUSED and self.clause is not None:
            raise BadArgument("clause", self.clause, "only a refused plan carries a clause")

    @property
    def venues(self) -> tuple[str, ...]:
        """Every venue the plan touches, in leg order and without repeats."""
        seen: list[str] = []
        for leg in self.legs:
            if leg.venue not in seen:
                seen.append(leg.venue)
        return tuple(seen)

    @property
    def total_cost_bps(self) -> Decimal:
        """Everything taken off the gross edge."""
        return self.fee_bps + self.slippage_bps + self.rebalance_bps

    def arithmetic_holds(self) -> bool:
        """True when the stored net edge matches the stored components."""
        expected = self.gross_bps - self.total_cost_bps
        difference = expected - self.net_bps
        return abs(difference) <= TOLERANCE_BPS

    def require_arithmetic(self) -> Plan:
        """Refuse a plan whose components do not add up to its net edge."""
        if not self.arithmetic_holds():
            raise BadArgument(
                "net_bps",
                str(self.net_bps),
                f"does not match {self.gross_bps} less {self.total_cost_bps}",
            )
        return self

    def leg_on(self, venue: str) -> Leg:
        """The leg that runs on a venue, refusing when there is not exactly one."""
        found = [leg for leg in self.legs if leg.venue == venue]
        if len(found) != 1:
            raise BadArgument("venue", venue, f"this plan has {len(found)} legs there")
        return found[0]
