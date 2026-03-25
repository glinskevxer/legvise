"""How much a book is still worth believing, part way through its budget.

The staleness budget is a cliff: inside it a book is tradable, outside it is not.
That is the right rule for a gate and the wrong model for a price. A book two
hundred milliseconds into a seven hundred and fifty millisecond budget is not as
good as one stamped this instant, and a scanner that treats them identically
sizes the same on both.

So there is a confidence, running from one at zero age to zero at the budget.
It is linear, which is a choice and not a law: the honest exponential needs a
half life the desk has not measured, and inventing one would give the number a
precision it has not earned. Linear is legible and it is monotone, which is what
the sizer needs.

Nothing here refuses anything. `market.staleness` owns the cliff; this owns the
slope, and a caller uses both.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import NamedTuple

from legvise.clock import age_ms
from legvise.errors import BadArgument
from legvise.market.staleness import freshness
from legvise.model.book import Book
from legvise.model.venue import Venue
from legvise.money import ONE, ZERO, dec

__all__ = ["Confidence", "confidence_in", "scaled_size", "worst_of"]


class Confidence(NamedTuple):
    """How much of a book's quoted size the desk still believes in."""

    age_ms: int
    budget_ms: int
    factor: Decimal

    @property
    def is_spent(self) -> bool:
        """True when the book has used its whole budget."""
        return self.factor <= ZERO

    @property
    def is_fresh(self) -> bool:
        """True when the book is new enough that nothing is taken off."""
        return self.factor >= ONE


def _factor(age: int, budget: int) -> Decimal:
    if budget <= 0:
        raise BadArgument("budget_ms", budget, "a budget of zero leaves nothing to decay")
    if age <= 0:
        return ONE
    if age >= budget:
        return ZERO
    return ONE - Decimal(age) / Decimal(budget)


def confidence_in(book: Book, venue: Venue, now: dt.datetime) -> Confidence:
    """How much of `book` the desk still believes, given the venue's budget."""
    measured = freshness(book, venue, now)
    return Confidence(
        age_ms=measured.age_ms,
        budget_ms=measured.budget_ms,
        factor=_factor(measured.age_ms, measured.budget_ms),
    )


def confidence_at(age: int, budget: int) -> Confidence:
    """The same slope, for a caller that already has the two numbers."""
    return Confidence(age_ms=age, budget_ms=budget, factor=_factor(age, budget))


def scaled_size(size: Decimal, found: Confidence) -> Decimal:
    """Take a size down in proportion to how far the book has decayed."""
    if size < ZERO:
        raise BadArgument("size", str(size), "a size is not negative")
    return size * found.factor


def worst_of(first: Confidence, second: Confidence) -> Confidence:
    """The less believable of two books, which is what a pair is worth.

    A cross-venue plan is only as good as its worse leg, and taking the average
    of the two would let a very fresh book carry a nearly spent one.
    """
    return first if first.factor <= second.factor else second


def skew_penalty(first: Book, second: Book, window_ms: int) -> Decimal:
    """How much of a pair to give up for the gap between when they were seen.

    Zero when the two books share a stamp, one when they are a whole window
    apart. Separate from the confidence because it is a property of the pair
    rather than of either book.
    """
    if window_ms <= 0:
        raise BadArgument("window_ms", window_ms, "a pairing window leaves room to decay")
    apart = max(
        age_ms(first.observed_at, second.observed_at),
        age_ms(second.observed_at, first.observed_at),
    )
    if apart >= window_ms:
        return ONE
    return dec(str(apart)) / dec(str(window_ms))
