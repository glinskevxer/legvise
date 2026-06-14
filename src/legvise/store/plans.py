"""Scan sessions and the plans they produce.

Every plan is written, including the refused ones. That costs disk and it is
worth it: the question an operator asks after a quiet week is not "what did we
trade" but "what did we nearly trade, and what stopped it", and a store that
only keeps the winners cannot answer it.

A refused plan carries the clause that refused it, which is what makes the
question answerable as a `GROUP BY` rather than a grep through logs.
"""

from __future__ import annotations

import sqlite3

from legvise.errors import NotFound
from legvise.ids import Symbol, symbol_text
from legvise.model.book import Side
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.rows import as_decimal, as_int, as_optional_text, as_symbol, as_text
from legvise.store.db import Database

__all__ = ["PlanStore", "SessionRow"]

_SESSION_COLUMNS = "ref, started_at, min_edge_bps, pairing_window_ms, wanted_size"
_PLAN_COLUMNS = (
    "ref, session_ref, kind, symbol, notional, gross_bps, fee_bps,"
    " slippage_bps, rebalance_bps, net_bps, status, clause"
)
_LEG_COLUMNS = (
    "plan_ref, leg_index, venue_code, symbol, takes, price, size,"
    " fee_bps, fee_amount, levels_swept, slippage_bps"
)


class SessionRow:
    """One scan session, as it was recorded."""

    __slots__ = ("min_edge_bps", "pairing_window_ms", "ref", "started_at", "wanted_size")

    def __init__(self, row: sqlite3.Row) -> None:
        self.ref = as_text(row, "ref")
        self.started_at = as_text(row, "started_at")
        self.min_edge_bps = as_decimal(row, "min_edge_bps")
        self.pairing_window_ms = as_int(row, "pairing_window_ms")
        self.wanted_size = as_decimal(row, "wanted_size")


def _read_leg(row: sqlite3.Row) -> Leg:
    return Leg(
        venue=as_text(row, "venue_code"),
        symbol=as_symbol(row, "symbol"),
        takes=Side(as_text(row, "takes")),
        price=as_decimal(row, "price"),
        size=as_decimal(row, "size"),
        fee_bps=as_decimal(row, "fee_bps"),
        fee_amount=as_decimal(row, "fee_amount"),
        levels_swept=as_int(row, "levels_swept"),
        slippage_bps=as_decimal(row, "slippage_bps"),
    )


def _plan_row(plan: Plan, session_ref: str) -> tuple[object, ...]:
    """One plan as the parameter set its INSERT takes."""
    return (
        plan.ref,
        session_ref,
        plan.kind.value,
        symbol_text(plan.symbol),
        plan.notional,
        plan.gross_bps,
        plan.fee_bps,
        plan.slippage_bps,
        plan.rebalance_bps,
        plan.net_bps,
        plan.status.value,
        plan.clause,
    )


def _leg_rows(plan: Plan) -> list[tuple[object, ...]]:
    """Every leg of a plan as one parameter set each, in leg order."""
    return [
        (
            plan.ref,
            index,
            leg.venue,
            symbol_text(leg.symbol),
            leg.takes.value,
            leg.price,
            leg.size,
            leg.fee_bps,
            leg.fee_amount,
            leg.levels_swept,
            leg.slippage_bps,
        )
        for index, leg in enumerate(plan.legs)
    ]


class PlanStore:
    """The session, plan and leg tables."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def open_session(
        self,
        ref: str,
        *,
        started_at: str,
        min_edge_bps: object,
        pairing_window_ms: int,
        wanted_size: object,
    ) -> str:
        """Record a scan session before any plan hangs off it."""
        self._db.execute(
            f"INSERT INTO scan_session ({_SESSION_COLUMNS}) VALUES (?, ?, ?, ?, ?)",
            (ref, started_at, min_edge_bps, pairing_window_ms, wanted_size),
        )
        return ref

    def session(self, ref: str) -> SessionRow:
        """One session by reference."""
        row = self._db.query_one(
            f"SELECT {_SESSION_COLUMNS} FROM scan_session WHERE ref = ?", (ref,)
        )
        if row is None:
            raise NotFound("scan session", ref)
        return SessionRow(row)

    def sessions(self, *, limit: int = 20) -> tuple[SessionRow, ...]:
        """The most recent sessions, newest first."""
        rows = self._db.query(
            f"SELECT {_SESSION_COLUMNS} FROM scan_session ORDER BY started_at DESC, ref DESC"
            " LIMIT ?",
            (limit,),
        )
        return tuple(SessionRow(r) for r in rows)

    def add(self, plan: Plan, *, session_ref: str) -> Plan:
        """Write one plan and its legs."""
        self.add_all((plan,), session_ref=session_ref)
        return plan

    def add_all(self, plans: tuple[Plan, ...], *, session_ref: str) -> int:
        """Write a batch of plans and their legs in one transaction.

        A scan over ten markets on four venues writes a hundred and twenty
        plans. One transaction each is a hundred and twenty fsyncs on a desk
        that has not turned synchronous off, which is most of them.
        """
        if not plans:
            return 0
        with self._db.tx():
            self._db.execute_many(
                f"INSERT INTO plan ({_PLAN_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [_plan_row(plan, session_ref) for plan in plans],
            )
            self._db.execute_many(
                f"INSERT INTO plan_leg ({_LEG_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [row for plan in plans for row in _leg_rows(plan)],
            )
        return len(plans)

    def get(self, ref: str) -> Plan:
        """One plan by reference, legs and all."""
        row = self._db.query_one(f"SELECT {_PLAN_COLUMNS} FROM plan WHERE ref = ?", (ref,))
        if row is None:
            raise NotFound("plan", ref)
        return self._build(row)

    def for_session(self, session_ref: str) -> tuple[Plan, ...]:
        """Every plan in a session, best net edge first."""
        rows = self._db.query(
            f"SELECT {_PLAN_COLUMNS} FROM plan WHERE session_ref = ?"
            " ORDER BY CAST(net_bps AS REAL) DESC, ref",
            (session_ref,),
        )
        return tuple(self._build(r) for r in rows)

    def actionable(self, session_ref: str) -> tuple[Plan, ...]:
        """The plans in a session the desk could have sent."""
        return tuple(p for p in self.for_session(session_ref) if p.status.is_actionable)

    def refusal_counts(self, session_ref: str | None = None) -> dict[str, int]:
        """How often each clause refused a plan, across one session or all of them."""
        where = "" if session_ref is None else " AND session_ref = ?"
        params = () if session_ref is None else (session_ref,)
        rows = self._db.query(
            "SELECT clause, count(*) AS hits FROM plan WHERE clause IS NOT NULL"
            f"{where} GROUP BY clause ORDER BY hits DESC, clause",
            params,
        )
        return {as_text(r, "clause"): as_int(r, "hits") for r in rows}

    def symbols_seen(self, session_ref: str) -> tuple[Symbol, ...]:
        """Every market a session looked at."""
        rows = self._db.query(
            "SELECT DISTINCT symbol FROM plan WHERE session_ref = ? ORDER BY symbol",
            (session_ref,),
        )
        return tuple(as_symbol(r, "symbol") for r in rows)

    def _build(self, row: sqlite3.Row) -> Plan:
        ref = as_text(row, "ref")
        legs = self._db.query(
            f"SELECT {_LEG_COLUMNS} FROM plan_leg WHERE plan_ref = ? ORDER BY leg_index",
            (ref,),
        )
        return Plan(
            ref=ref,
            kind=PlanKind(as_text(row, "kind")),
            symbol=as_symbol(row, "symbol"),
            legs=tuple(_read_leg(r) for r in legs),
            notional=as_decimal(row, "notional"),
            gross_bps=as_decimal(row, "gross_bps"),
            fee_bps=as_decimal(row, "fee_bps"),
            slippage_bps=as_decimal(row, "slippage_bps"),
            rebalance_bps=as_decimal(row, "rebalance_bps"),
            net_bps=as_decimal(row, "net_bps"),
            status=PlanStatus(as_text(row, "status")),
            clause=as_optional_text(row, "clause"),
        )
