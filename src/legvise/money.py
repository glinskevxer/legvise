"""Exact decimal arithmetic, because a satoshi lost to binary rounding is real.

Every quantity in the package is a `Decimal` built through `dec`. Floats are
refused at the door rather than tolerated and rounded later: an eighth of a
basis point on a six figure notional is money, and a float that looks like
`0.1` is not `0.1`.

Rounding direction is never left to a default. A size going to a venue rounds
down so the order is fillable; a fee owed rounds up so the desk never
under-books what it will pay.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Final

from legvise.errors import BadArgument

__all__ = [
    "ZERO",
    "apply_bps",
    "bps_between",
    "dec",
    "is_zero",
    "quantize_down",
    "quantize_nearest",
    "quantize_up",
    "step_multiple",
]

ZERO: Final = Decimal("0")
_BPS: Final = Decimal("10000")


def dec(value: str | int | Decimal, *, field: str = "value") -> Decimal:
    """Build a Decimal from an exact literal.

    A float is refused outright. Callers holding one have already lost precision
    and the honest fix is upstream, not a silent `Decimal(repr(x))` here.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise BadArgument(field, value, "a bool is not a quantity")
    if isinstance(value, int):
        return Decimal(value)
    if not isinstance(value, str):
        raise BadArgument(field, value, "quantities are built from str, int or Decimal")
    try:
        out = Decimal(value.strip())
    except InvalidOperation:
        raise BadArgument(field, value, "not a decimal literal") from None
    if not out.is_finite():
        raise BadArgument(field, value, "must be finite")
    return out


def is_zero(value: Decimal) -> bool:
    """True when the value is zero regardless of how many trailing zeros it wears."""
    return value == ZERO


def _positive_step(step: Decimal, field: str) -> Decimal:
    if step <= ZERO:
        raise BadArgument(field, str(step), "a step has to be positive")
    return step


def quantize_down(value: Decimal, step: Decimal, *, field: str = "step") -> Decimal:
    """Largest multiple of `step` at or below `value`."""
    _positive_step(step, field)
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def quantize_up(value: Decimal, step: Decimal, *, field: str = "step") -> Decimal:
    """Smallest multiple of `step` at or above `value`."""
    _positive_step(step, field)
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def quantize_nearest(value: Decimal, step: Decimal, *, field: str = "step") -> Decimal:
    """Nearest multiple of `step`, ties to the even multiple."""
    _positive_step(step, field)
    return (value / step).to_integral_value(rounding=ROUND_HALF_EVEN) * step


def step_multiple(value: Decimal, step: Decimal, *, field: str = "step") -> bool:
    """True when `value` sits exactly on the grid `step` defines."""
    _positive_step(step, field)
    return (value % step) == ZERO


def apply_bps(value: Decimal, bps: Decimal) -> Decimal:
    """The part of `value` that `bps` basis points comes to.

    Returned unrounded. Whoever owes it decides the direction to round.
    """
    return value * bps / _BPS


def bps_between(low: Decimal, high: Decimal) -> Decimal:
    """How many basis points `high` sits above `low`.

    Undefined at a zero or negative base, and that is a refusal rather than an
    infinity, because every caller here is comparing two prices.
    """
    if low <= ZERO:
        raise BadArgument("low", str(low), "a basis point spread needs a positive base")
    return (high - low) / low * _BPS
