"""Reading and writing fills, and collapsing them back onto their legs.

A fill row is append only. Nothing here updates or deletes one, because a fill
is a statement about something that happened on a venue and the desk does not
get to change its mind about that. A correction is a new row, and the venue's
own trade id keeps the two apart.
"""

from __future__ import annotations

import sqlite3

from legvise.errors import NotFound
from legvise.model.book import Side
from legvise.model.fill import Fill, LegResult
from legvise.model.plan import Plan
from legvise.rows import as_decimal, as_int, as_text
from legvise.store.db import Database

__all__ = ["FillStore"]

_COLUMNS = (
    "plan_ref, leg_index, venue_code, takes, price, size, fee_amount, filled_at, venue_trade_id"
)


def _read(row: sqlite3.Row) -> Fill:
    return Fill(
        plan_ref=as_text(row, "plan_ref"),
        leg_index=as_int(row, "leg_index"),
        venue=as_text(row, "venue_code"),
        takes=Side(as_text(row, "takes")),
        price=as_decimal(row, "price"),
        size=as_decimal(row, "size"),
        fee_amount=as_decimal(row, "fee_amount"),
        filled_at=as_text(row, "filled_at"),
    )


class FillStore:
    """The fill table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, fill: Fill, *, venue_trade_id: str) -> Fill:
        """Append one fill. The venue's own trade id keeps duplicates out."""
        self._db.execute(
            f"INSERT INTO fill ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fill.plan_ref,
                fill.leg_index,
                fill.venue,
                fill.takes.value,
                fill.price,
                fill.size,
                fill.fee_amount,
                fill.filled_at,
                venue_trade_id,
            ),
        )
        return fill

    def for_plan(self, plan_ref: str) -> tuple[Fill, ...]:
        """Every fill against a plan, in leg then time order."""
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM fill WHERE plan_ref = ?"
            " ORDER BY leg_index, filled_at, venue_trade_id",
            (plan_ref,),
        )
        return tuple(_read(r) for r in rows)

    def for_leg(self, plan_ref: str, leg_index: int) -> tuple[Fill, ...]:
        """Every fill against one leg, in time order."""
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM fill WHERE plan_ref = ? AND leg_index = ?"
            " ORDER BY filled_at, venue_trade_id",
            (plan_ref, leg_index),
        )
        return tuple(_read(r) for r in rows)

    def results_for(self, plan: Plan) -> tuple[LegResult, ...]:
        """Each leg of a plan against the fills it got."""
        by_leg: dict[int, list[Fill]] = {index: [] for index in range(len(plan.legs))}
        for fill in self.for_plan(plan.ref):
            if fill.leg_index in by_leg:
                by_leg[fill.leg_index].append(fill)
        return tuple(
            LegResult(
                plan_ref=plan.ref,
                leg_index=index,
                expected_price=leg.price,
                expected_size=leg.size,
                fills=tuple(by_leg[index]),
            )
            for index, leg in enumerate(plan.legs)
        )

    def plans_with_fills(self, *, limit: int = 50) -> tuple[str, ...]:
        """Plan references that have at least one fill, newest first."""
        rows = self._db.query(
            "SELECT plan_ref, max(filled_at) AS last_fill FROM fill"
            " GROUP BY plan_ref ORDER BY last_fill DESC, plan_ref DESC LIMIT ?",
            (limit,),
        )
        return tuple(as_text(r, "plan_ref") for r in rows)

    def require_any(self, plan_ref: str) -> tuple[Fill, ...]:
        """Every fill against a plan, refusing when there are none."""
        found = self.for_plan(plan_ref)
        if not found:
            raise NotFound("fill", plan_ref)
        return found

    def count(self) -> int:
        """How many fills are on file."""
        return int(self._db.scalar("SELECT count(*) FROM fill") or 0)
