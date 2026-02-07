"""Storing the scanner's decisions, including the ones that stopped early.

Append only and never updated. A decision is a statement about what the scanner
did at an instant, and the row exists so that instant can be reconstructed; a
row that gets edited afterwards is a row nobody can reason from.

The table is deliberately narrow. It gets one row per venue per symbol per scan
in the worst case, which on a busy desk is more rows than the plan table by an
order of magnitude, so it carries no decimals and no joins.
"""

from __future__ import annotations

import sqlite3

from legvise.errors import NotFound
from legvise.model.audit import Decision, Stage
from legvise.rows import as_int, as_optional_text, as_text
from legvise.store.db import Database

__all__ = ["DecisionStore"]

_COLUMNS = "session_ref, sequence, taken_at, stage, subject, detail, clause"


def _read(row: sqlite3.Row) -> Decision:
    return Decision(
        session_ref=as_text(row, "session_ref"),
        sequence=as_int(row, "sequence"),
        at=as_text(row, "taken_at"),
        stage=Stage(as_text(row, "stage")),
        subject=as_text(row, "subject"),
        detail=as_text(row, "detail"),
        clause=as_optional_text(row, "clause"),
    )


class DecisionStore:
    """The decision table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, decision: Decision) -> Decision:
        """Append one decision."""
        self._db.execute(
            f"INSERT INTO decision ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                decision.session_ref,
                decision.sequence,
                decision.at,
                decision.stage.value,
                decision.subject,
                decision.detail,
                decision.clause,
            ),
        )
        return decision

    def add_all(self, decisions: tuple[Decision, ...]) -> int:
        """Append a batch in one transaction and say how many went in."""
        with self._db.tx():
            for decision in decisions:
                self.add(decision)
        return len(decisions)

    def for_session(self, session_ref: str) -> tuple[Decision, ...]:
        """Every decision in a session, in the order they were taken."""
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM decision WHERE session_ref = ? ORDER BY sequence",
            (session_ref,),
        )
        return tuple(_read(r) for r in rows)

    def at_stage(self, session_ref: str, stage: Stage) -> tuple[Decision, ...]:
        """Every decision taken at one stage of a session."""
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM decision WHERE session_ref = ? AND stage = ?"
            " ORDER BY sequence",
            (session_ref, stage.value),
        )
        return tuple(_read(r) for r in rows)

    def stage_counts(self, session_ref: str) -> dict[str, int]:
        """How many decisions each stage took, busiest first."""
        rows = self._db.query(
            "SELECT stage, count(*) AS hits FROM decision WHERE session_ref = ?"
            " GROUP BY stage ORDER BY hits DESC, stage",
            (session_ref,),
        )
        return {as_text(r, "stage"): as_int(r, "hits") for r in rows}

    def require_any(self, session_ref: str) -> tuple[Decision, ...]:
        """Every decision in a session, refusing an empty one."""
        found = self.for_session(session_ref)
        if not found:
            raise NotFound("decision", session_ref)
        return found

    def next_sequence(self, session_ref: str) -> int:
        """The sequence number the next decision in a session should carry."""
        highest = self._db.scalar(
            "SELECT max(sequence) FROM decision WHERE session_ref = ?", (session_ref,)
        )
        return 0 if highest is None else int(highest) + 1

    def count(self) -> int:
        """How many decisions are on file."""
        return int(self._db.scalar("SELECT count(*) FROM decision") or 0)
