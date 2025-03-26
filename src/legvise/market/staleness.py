"""How old a book is allowed to be, and how far apart two of them may sit.

There are two separate questions here and conflating them is a classic way to
lose money. The first is absolute: is this book old enough that the venue has
almost certainly moved? That is the venue's staleness budget, and it is a
property of the feed.

The second is relative: were these two books true at the same time? Two books
that are each 200ms old are both fresh, but if one was stamped at 09:00:00.000
and the other at 09:00:00.400 then the desk is pricing a spread that never
existed. That is the pairing window, and it is a property of the plan.

A desk that only checks the first one prints plans off a 400ms skew all day and
wonders why the realised edge is half the expected edge.
"""

from __future__ import annotations

import datetime as dt
from typing import NamedTuple

from legvise.clock import age_ms
from legvise.errors import BadArgument
from legvise.model.book import Book
from legvise.model.venue import Venue
from legvise.rules import refuse

__all__ = [
    "Freshness",
    "check_pairing",
    "freshness",
    "is_fresh",
    "require_fresh",
    "skew_ms",
]


class Freshness(NamedTuple):
    """How old one book is against the budget it has to meet."""

    age_ms: int
    budget_ms: int

    @property
    def within_budget(self) -> bool:
        """True when the book is young enough to price against."""
        return self.age_ms <= self.budget_ms

    @property
    def headroom_ms(self) -> int:
        """Milliseconds left before the book goes stale. Negative once it has."""
        return self.budget_ms - self.age_ms


def freshness(book: Book, venue: Venue, now: dt.datetime) -> Freshness:
    """Measure one book against its venue's budget."""
    if venue.code != book.venue:
        raise BadArgument("venue", venue.code, f"this book came from {book.venue}")
    return Freshness(age_ms=age_ms(book.observed_at, now), budget_ms=venue.staleness_budget_ms)


def is_fresh(book: Book, venue: Venue, now: dt.datetime) -> bool:
    """True when the book is inside its budget."""
    return freshness(book, venue, now).within_budget


def require_fresh(book: Book, venue: Venue, now: dt.datetime) -> Freshness:
    """Measure the book and refuse it if it has gone stale."""
    measured = freshness(book, venue, now)
    if not measured.within_budget:
        raise refuse(
            "STALE.01",
            f"{book.venue} {book.symbol} at {measured.age_ms}ms against {measured.budget_ms}ms",
        )
    return measured


def skew_ms(first: Book, second: Book) -> int:
    """How far apart in time two books were observed, always non-negative."""
    left = age_ms(first.observed_at, second.observed_at)
    right = age_ms(second.observed_at, first.observed_at)
    return max(left, right)


def check_pairing(first: Book, second: Book, window_ms: int) -> int:
    """Refuse two books that were not observed close enough together."""
    if window_ms < 0:
        raise BadArgument("window_ms", window_ms, "a pairing window cannot be negative")
    skew = skew_ms(first, second)
    if skew > window_ms:
        raise refuse(
            "STALE.02",
            f"{first.venue} and {second.venue} are {skew}ms apart against {window_ms}ms",
        )
    return skew
