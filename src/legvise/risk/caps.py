"""Exposure caps, and the difference between a cap that trims and one that stops.

Three caps, and they do not behave the same way:

- **per venue** (CAP.01) is a trim. A venue with 40,000 of room left takes a
  40,000 plan instead of the 60,000 that was priced.
- **per asset** (CAP.02) is also a trim, on the desk's net position in one
  asset across every venue. Two legs of a cross-venue plan mostly offset, so
  this usually binds on the residue rather than the gross.
- **desk gross** (CAP.03) is a stop. It exists so a bad afternoon cannot be
  arbitraged into a very bad one, and a cap that quietly halves everything
  instead of stopping is a cap nobody notices they have hit.

Trimming rather than refusing matters more than it sounds. A scanner that drops
every plan it cannot do in full does nothing at all on the days the desk is
closest to its limits, which are exactly the days the limits were set for.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.money import ZERO
from legvise.rules import refuse

__all__ = ["CapSet", "Trim", "trim_to_caps"]


@dataclass(frozen=True, slots=True)
class CapSet:
    """The three limits, and what is already used against each."""

    venue_cap: Decimal
    venue_used: Decimal
    asset_cap: Decimal
    asset_used: Decimal
    gross_cap: Decimal
    gross_used: Decimal

    def __post_init__(self) -> None:
        for name, value in (
            ("venue_cap", self.venue_cap),
            ("asset_cap", self.asset_cap),
            ("gross_cap", self.gross_cap),
        ):
            if value <= ZERO:
                raise BadArgument(name, str(value), "a cap of zero switches the desk off")
        for name, value in (
            ("venue_used", self.venue_used),
            ("asset_used", self.asset_used),
            ("gross_used", self.gross_used),
        ):
            if value < ZERO:
                raise BadArgument(name, str(value), "used exposure is not negative")

    @property
    def venue_room(self) -> Decimal:
        """Notional left under the venue cap, floored at zero."""
        return max(self.venue_cap - self.venue_used, ZERO)

    @property
    def asset_room(self) -> Decimal:
        """Notional left under the asset cap, floored at zero."""
        return max(self.asset_cap - self.asset_used, ZERO)

    @property
    def gross_room(self) -> Decimal:
        """Notional left under the desk gross cap, floored at zero."""
        return max(self.gross_cap - self.gross_used, ZERO)


@dataclass(frozen=True, slots=True)
class Trim:
    """A notional after the caps have had their say, and which one bound."""

    requested: Decimal
    allowed: Decimal
    bound_by: str | None

    @property
    def was_trimmed(self) -> bool:
        """True when a cap took something off."""
        return self.allowed < self.requested

    @property
    def cut(self) -> Decimal:
        """How much notional the caps removed."""
        return self.requested - self.allowed


def trim_to_caps(caps: CapSet, requested: Decimal, *, subject: str) -> Trim:
    """Cut a requested notional down to what the caps leave room for.

    The gross cap is checked first and refuses rather than trims. Anything that
    survives it is then trimmed by whichever of the other two is tighter.
    """
    if requested <= ZERO:
        raise BadArgument("requested", str(requested), "a plan needs a positive notional")
    if caps.gross_room <= ZERO:
        raise refuse("CAP.03", f"{subject} against a desk gross cap of {caps.gross_cap}")
    if requested > caps.gross_room:
        raise refuse(
            "CAP.03",
            f"{subject} wants {requested} with {caps.gross_room} left under the gross cap",
        )
    allowed = requested
    bound: str | None = None
    if caps.venue_room < allowed:
        allowed = caps.venue_room
        bound = "CAP.01"
    if caps.asset_room < allowed:
        allowed = caps.asset_room
        bound = "CAP.02"
    return Trim(requested=requested, allowed=allowed, bound_by=bound)


def require_trim(caps: CapSet, requested: Decimal, *, subject: str, floor: Decimal) -> Decimal:
    """Trim, then refuse if what is left is too small to be worth sending."""
    trimmed = trim_to_caps(caps, requested, subject=subject)
    if trimmed.allowed < floor:
        raise refuse(
            trimmed.bound_by or "CAP.01",
            f"{subject} trims to {trimmed.allowed} against a floor of {floor}",
        )
    return trimmed.allowed
