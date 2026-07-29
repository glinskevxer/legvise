"""How much of the book of record to keep, and what a sweep may never take.

A desk that scans every few seconds writes a snapshot per venue per market per
scan. The file grows without bound and almost none of it is worth keeping: a
book from last Tuesday priced nothing and nobody will ever read it.

Deleting by age alone is wrong twice over, and both ways are quiet:

- **The newest snapshot of a market is never old enough to drop.** Age it as
  you like; it is still the only picture the desk has of that market. Drop it
  and `report desk` says the venue has no books, `scan run` skips it, and the
  market silently leaves the rotation. The desk does not find out from an error.
  It finds out from a smaller list of opportunities.
- **A session with a fill against it is the record of a trade.** The plan says
  what the desk meant to do and the fill says what happened, and a reconciler
  needs both. Age is not a reason to delete either.

So a sweep surveys first, counts what it would take and what it is holding on
to, and only then deletes. `survey` and `sweep` run the same queries; the only
difference is whether the delete follows. That is deliberate, because a dry run
that answers a different question from the real one is worse than no dry run.

The newest snapshot is found with a window function rather than `max(id)`.
Snapshots arrive out of order often enough to matter -- a venue replays a feed,
or a backfill lands after a live tick -- and `BookStore.latest` reads by
`observed_at`, so a sweep that kept the highest id would keep a row that is not
the one anybody reads.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from legvise.clock import to_text
from legvise.errors import BadArgument
from legvise.rows import as_int
from legvise.store.db import Database

__all__ = ["Retention", "Sweep"]

_NEWEST = """
SELECT id FROM (
    SELECT id, row_number() OVER (
        PARTITION BY venue_code, symbol ORDER BY observed_at DESC, id DESC
    ) AS rank_in_market
    FROM book_snapshot
) WHERE rank_in_market = 1
"""

_TRADED = "SELECT DISTINCT plan.session_ref FROM plan JOIN fill ON fill.plan_ref = plan.ref"

_DROPPABLE_SNAPSHOTS = f"FROM book_snapshot WHERE observed_at < ? AND id NOT IN ({_NEWEST})"

_DROPPABLE_SESSIONS = f"FROM scan_session WHERE started_at < ? AND ref NOT IN ({_TRADED})"

# The counts of what goes with a dropped session read the same subquery rather
# than a list of references assembled in Python. A list would have to be built
# from a survey that ran a moment earlier, and the two could disagree.
_DOOMED_REFS = f"SELECT ref {_DROPPABLE_SESSIONS}"

_DOOMED_PLANS = f"SELECT count(*) FROM plan WHERE session_ref IN ({_DOOMED_REFS})"

_DOOMED_DECISIONS = f"SELECT count(*) FROM decision WHERE session_ref IN ({_DOOMED_REFS})"


@dataclass(frozen=True, slots=True)
class Sweep:
    """What a prune would take, and what it decided to keep.

    The held counts are the point. A sweep that reports it kept eleven markets
    and two traded sessions is telling an operator that the cutoff they chose
    is past the whole history of those markets, which is usually a sign the
    cutoff is wrong rather than a sign the sweep worked.
    """

    snapshots: int
    sessions: int
    plans: int
    decisions: int
    held_markets: int
    held_sessions: int

    @property
    def rows(self) -> int:
        """Every row the sweep would remove, across all four tables."""
        return self.snapshots + self.sessions + self.plans + self.decisions

    @property
    def is_empty(self) -> bool:
        """True when there is nothing old enough to drop."""
        return self.rows == 0

    def lines(self) -> tuple[str, ...]:
        """One line per table, for a command to print."""
        return (
            f"snapshots  {self.snapshots}",
            f"sessions   {self.sessions}",
            f"plans      {self.plans}",
            f"decisions  {self.decisions}",
            f"held       {self.held_markets} markets, {self.held_sessions} traded sessions",
        )


class Retention:
    """Surveys and applies a cutoff against the book of record."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def cutoff_from(self, now: dt.datetime, keep_days: int) -> dt.datetime:
        """The instant `keep_days` before now, refusing a cutoff in the future."""
        if keep_days < 1:
            raise BadArgument("keep_days", str(keep_days), "a sweep has to keep at least a day")
        return now - dt.timedelta(days=keep_days)

    def droppable_snapshots(self, before: dt.datetime) -> int:
        """Snapshots older than the cutoff that are not the newest of a market."""
        return self._count(f"SELECT count(*) {_DROPPABLE_SNAPSHOTS}", before)

    def droppable_sessions(self, before: dt.datetime) -> tuple[str, ...]:
        """Sessions older than the cutoff with nothing traded against them."""
        rows = self._db.query(f"{_DOOMED_REFS} ORDER BY ref", (to_text(before),))
        return tuple(str(row["ref"]) for row in rows)

    def droppable_plans(self, before: dt.datetime) -> int:
        """Plans that would go with the sessions the cutoff drops."""
        return self._count(_DOOMED_PLANS, before)

    def droppable_decisions(self, before: dt.datetime) -> int:
        """Ledger entries that would go with the sessions the cutoff drops."""
        return self._count(_DOOMED_DECISIONS, before)

    def held_markets(self, before: dt.datetime) -> int:
        """Markets whose newest snapshot is older than the cutoff and stays."""
        return self._count(
            f"SELECT count(*) FROM book_snapshot WHERE observed_at < ? AND id IN ({_NEWEST})",
            before,
        )

    def held_sessions(self, before: dt.datetime) -> int:
        """Sessions older than the cutoff that are kept because they traded."""
        return self._count(
            f"SELECT count(*) FROM scan_session WHERE started_at < ? AND ref IN ({_TRADED})",
            before,
        )

    def survey(self, before: dt.datetime) -> Sweep:
        """Count what a sweep at this cutoff would do, without doing it."""
        return Sweep(
            snapshots=self.droppable_snapshots(before),
            sessions=len(self.droppable_sessions(before)),
            plans=self.droppable_plans(before),
            decisions=self.droppable_decisions(before),
            held_markets=self.held_markets(before),
            held_sessions=self.held_sessions(before),
        )

    def sweep(self, before: dt.datetime) -> Sweep:
        """Apply the cutoff and return what went, counted before it went.

        One transaction, so a survey that says four hundred rows and a file
        that lost three hundred cannot happen. The plans, legs, fills and
        decisions go with their session through the schema's own cascades
        rather than through four more statements here.
        """
        found = self.survey(before)
        if found.is_empty:
            return found
        with self._db.tx():
            self._db.execute(f"DELETE {_DROPPABLE_SNAPSHOTS}", (to_text(before),))
            self._db.execute(f"DELETE {_DROPPABLE_SESSIONS}", (to_text(before),))
        return found

    def _count(self, sql: str, before: dt.datetime) -> int:
        row = self._db.query_one(sql, (to_text(before),))
        return 0 if row is None else as_int(row, "count(*)")
