"""Reading the whole book back and asking whether it still adds up.

Every write path checks itself. A plan refuses to be built if its components do
not reach its net edge, a fill refuses a leg index its plan does not have, and
the schema declares its own foreign keys. So in principle none of this can go
wrong, and in practice a book of record is a file: it gets copied off a laptop,
restored from a backup taken mid-write, edited by hand at two in the morning by
somebody chasing a settlement break, and migrated by a version of the tool that
has since been fixed.

None of those leave an error behind. They leave a file that opens, reads and
prices, and disagrees with itself somewhere nobody looks.

So this reads the whole thing back and re-derives what it can:

- **Foreign keys.** SQLite only enforces them when asked, and a file written by
  something that did not ask can hold a plan whose session is gone.
- **Plan arithmetic.** `net = gross - fees - slippage - rebalance`, re-derived
  from the stored numbers rather than trusted. A plan that fails this was
  written by a build that is no longer running.
- **Leg notional.** A plan's notional is what its entry leg moves. A plan that
  disagrees with its own first leg will size the next rebalance wrong, and the
  attribution will divide by the wrong number.
- **Orphan fills.** A fill against a leg index its plan does not have cannot be
  reconciled and cannot be attributed.
- **Decimal spelling.** Numbers are stored in plain notation, never as `1E-8`.
  Exponent notation compares wrong under the text collation the indexes use, so
  a single `E` in a price column makes range queries quietly skip rows.

Every finding names the row. A report that says the book is broken and not
where is a report that costs an afternoon.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from legvise.money import dec
from legvise.rows import as_int, as_text
from legvise.store.db import Database
from legvise.store.plans import PlanStore

__all__ = ["Finding", "check_book", "findings_by_kind"]

_ORPHAN_FILLS: Final = """
SELECT fill.plan_ref AS plan_ref, fill.leg_index AS leg_index
FROM fill
LEFT JOIN plan_leg ON plan_leg.plan_ref = fill.plan_ref
    AND plan_leg.leg_index = fill.leg_index
WHERE plan_leg.plan_ref IS NULL
ORDER BY fill.plan_ref, fill.leg_index
"""

_EXPONENTS: Final = """
SELECT ref AS ref, notional AS value FROM plan WHERE notional LIKE '%E%'
UNION ALL
SELECT ref AS ref, net_bps AS value FROM plan WHERE net_bps LIKE '%E%'
ORDER BY ref
"""

_LEG_TOTALS: Final = """
SELECT plan_ref AS plan_ref, count(*) AS legs FROM plan_leg
GROUP BY plan_ref ORDER BY plan_ref
"""


@dataclass(frozen=True, slots=True)
class Finding:
    """One row that does not hold up, and what is wrong with it."""

    kind: str
    subject: str
    detail: str

    def __str__(self) -> str:
        """The line a command prints."""
        return f"{self.kind}  {self.subject}  {self.detail}"


def foreign_keys(db: Database) -> list[Finding]:
    """Rows pointing at a parent that is not there."""
    rows = db.query("PRAGMA foreign_key_check")
    return [
        Finding(
            kind="foreign_key",
            subject=f"{as_text(row, 'table')} rowid {row['rowid']}",
            detail=f"points at a missing {as_text(row, 'parent')}",
        )
        for row in rows
    ]


def plan_arithmetic(db: Database) -> list[Finding]:
    """Plans whose stored components do not reach their stored net edge."""
    store = PlanStore(db)
    found: list[Finding] = []
    for ref in _plan_refs(db):
        plan = store.get(ref)
        if plan.arithmetic_holds():
            continue
        expected = plan.gross_bps - plan.total_cost_bps
        found.append(
            Finding(
                kind="arithmetic",
                subject=ref,
                detail=f"net is {plan.net_bps}, components reach {expected}",
            )
        )
    return found


def leg_notionals(db: Database) -> list[Finding]:
    """Plans whose notional is not what their entry leg moves."""
    store = PlanStore(db)
    found: list[Finding] = []
    for ref in _plan_refs(db):
        plan = store.get(ref)
        entry = plan.legs[0].notional
        if abs(entry - plan.notional) <= _tolerance(plan.notional):
            continue
        found.append(
            Finding(
                kind="notional",
                subject=ref,
                detail=f"plan says {plan.notional}, its entry leg moves {entry}",
            )
        )
    return found


def orphan_fills(db: Database) -> list[Finding]:
    """Fills recorded against a leg index the plan does not have."""
    return [
        Finding(
            kind="orphan_fill",
            subject=as_text(row, "plan_ref"),
            detail=f"has a fill on leg {as_int(row, 'leg_index')}, which is not on the plan",
        )
        for row in db.query(_ORPHAN_FILLS)
    ]


def leg_counts(db: Database) -> list[Finding]:
    """Plans stored with fewer than the two legs a plan has to have."""
    return [
        Finding(
            kind="legs",
            subject=as_text(row, "plan_ref"),
            detail=f"has {as_int(row, 'legs')} legs on file, wanted at least two",
        )
        for row in db.query(_LEG_TOTALS)
        if as_int(row, "legs") < 2
    ]


def decimal_spelling(db: Database) -> list[Finding]:
    """Numbers written in exponent notation, which sorts wrong as text."""
    return [
        Finding(
            kind="notation",
            subject=as_text(row, "ref"),
            detail=f"stores {as_text(row, 'value')} in exponent notation",
        )
        for row in db.query(_EXPONENTS)
    ]


def check_book(db: Database) -> tuple[Finding, ...]:
    """Every finding across the whole book, in the order the checks run."""
    found: list[Finding] = []
    for check in (
        foreign_keys,
        plan_arithmetic,
        leg_notionals,
        orphan_fills,
        leg_counts,
        decimal_spelling,
    ):
        found.extend(check(db))
    return tuple(found)


def findings_by_kind(found: tuple[Finding, ...]) -> dict[str, int]:
    """How many findings of each kind, worst first."""
    counts: dict[str, int] = {}
    for finding in found:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _plan_refs(db: Database) -> tuple[str, ...]:
    rows = db.query("SELECT ref FROM plan ORDER BY ref")
    return tuple(as_text(row, "ref") for row in rows)


def _tolerance(notional: Decimal) -> Decimal:
    """How far the entry leg may sit from the plan's notional.

    One basis point, relative. The leg carries a volume weighted price rounded
    to the venue's tick and the plan carries the swept total, so the two agree
    to rounding and not to the cent. Demanding the cent would report every plan
    the desk ever wrote, and a check that fires on everything is off.

    A corrupt notional is not off by a basis point. It is off by a factor.
    """
    return abs(notional) / dec("10000")
