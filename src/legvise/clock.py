"""One clock, handed in everywhere, never read from the module level.

Arbitrage is a stopwatch problem. A book that was true four hundred milliseconds
ago may not be true now, and the difference between a plan that prints money and
one that eats the spread is often the age of the quote it was priced against.

So time is a dependency here, not an ambient fact. Production passes
`SystemClock`; tests pass `FixedClock` and step it by hand. Nothing in the
package calls `datetime.now` directly, and there is a check that keeps it that
way.
"""

from __future__ import annotations

import datetime as dt
from typing import Final, Protocol

from legvise.errors import BadArgument

__all__ = [
    "Clock",
    "FixedClock",
    "SystemClock",
    "age_ms",
    "parse_instant",
    "to_millis",
    "to_text",
]

_UTC: Final = dt.UTC
_MS: Final = 1000


class Clock(Protocol):
    """Anything that can say what time it is, in UTC."""

    def now(self) -> dt.datetime:
        """The current instant, timezone aware and in UTC."""
        ...


class SystemClock:
    """The wall clock, pinned to UTC."""

    def now(self) -> dt.datetime:
        """The current instant from the operating system."""
        return dt.datetime.now(tz=_UTC)


class FixedClock:
    """A clock that only moves when a test moves it."""

    def __init__(self, start: dt.datetime) -> None:
        self._at = _require_aware(start, "start")

    def now(self) -> dt.datetime:
        """Whatever instant the clock was last set to."""
        return self._at

    def advance_ms(self, millis: int) -> dt.datetime:
        """Push the clock forward and return where it landed."""
        if millis < 0:
            raise BadArgument("millis", millis, "a fixed clock does not run backwards")
        self._at = self._at + dt.timedelta(milliseconds=millis)
        return self._at

    def set_to(self, at: dt.datetime) -> None:
        """Jump the clock to an instant, forwards or backwards."""
        self._at = _require_aware(at, "at")


def _require_aware(value: dt.datetime, field: str) -> dt.datetime:
    if value.tzinfo is None:
        raise BadArgument(field, value.isoformat(), "an instant needs a timezone")
    return value.astimezone(_UTC)


def parse_instant(text: str, *, field: str = "instant") -> dt.datetime:
    """Read an ISO 8601 instant, refusing one with no offset."""
    try:
        parsed = dt.datetime.fromisoformat(text.strip())
    except ValueError:
        raise BadArgument(field, text, "not an ISO 8601 instant") from None
    return _require_aware(parsed, field)


def to_text(value: dt.datetime) -> str:
    """The canonical string form, always UTC and always with the offset."""
    return _require_aware(value, "value").isoformat()


def to_millis(value: dt.datetime) -> int:
    """Milliseconds since the epoch, truncated rather than rounded."""
    return int(_require_aware(value, "value").timestamp() * _MS)


def age_ms(observed_at: dt.datetime, now: dt.datetime) -> int:
    """How old `observed_at` is at `now`, in milliseconds.

    A quote stamped in the future is a clock skew problem on the feed side, not
    a negative age, so it reads as zero and the caller sees fresh data.
    """
    delta = to_millis(now) - to_millis(observed_at)
    return max(delta, 0)
