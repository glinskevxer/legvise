"""The desk's rule book, and the only way to refuse a plan.

A scanner that says "rejected" and nothing else is useless at four in the
morning. Every refusal in the pricing path quotes a clause, the clause text is
written once here, and the plan record keeps the clause code so a week later
somebody can ask how often clause DEPTH.02 fired and get a number.

Clauses are grouped by the stage that enforces them. The prefix is the stage.
"""

from __future__ import annotations

from typing import Final, NamedTuple

from legvise.errors import BadArgument, Refused

__all__ = [
    "Clause",
    "clause",
    "clause_codes",
    "clauses_for_stage",
    "refuse",
    "stages",
]


class Clause(NamedTuple):
    """One numbered rule, its stage, and what it says in words."""

    code: str
    stage: str
    text: str


def _book(*rows: tuple[str, str]) -> dict[str, Clause]:
    out: dict[str, Clause] = {}
    for code, text in rows:
        stage = code.split(".", 1)[0]
        out[code] = Clause(code=code, stage=stage, text=text)
    return out


_CLAUSES: Final[dict[str, Clause]] = _book(
    ("BOOK.01", "a side of a book has to be sorted away from the touch"),
    ("BOOK.02", "a book with no level on one side cannot be crossed"),
    ("BOOK.03", "a level has to carry a positive price and a positive size"),
    ("BOOK.04", "the bid may not sit at or above the ask on the same venue"),
    ("STALE.01", "a book older than the venue staleness budget is not tradable"),
    ("STALE.02", "the two legs of a plan have to be observed within the pairing window"),
    ("TICK.01", "a price has to sit on the venue tick grid"),
    ("TICK.02", "a size has to sit on the venue lot grid"),
    ("TICK.03", "an order has to clear the venue minimum notional"),
    ("TICK.04", "an order may not exceed the venue maximum notional"),
    ("DEPTH.01", "a leg may only take size the visible book can fill"),
    ("DEPTH.02", "a leg may not sweep past the depth limit set for the venue"),
    ("FEE.01", "a fee tier has to be resolved before a leg can be priced"),
    ("FEE.02", "a maker rebate is only credited where the venue pays one"),
    ("BAND.01", "a leg may not take an asset below its inventory floor"),
    ("BAND.02", "a leg that lifts an asset over its ceiling is charged to rebalance"),
    ("CAP.01", "a plan may not push a venue over its notional cap"),
    ("CAP.02", "a plan may not push an asset over its net exposure cap"),
    ("CAP.03", "the desk gross cap is a hard stop, not a downsize"),
    ("EDGE.01", "a plan has to clear the desk minimum edge after every cost"),
    ("EDGE.02", "a plan priced on a crossed or locked book is discarded"),
)


def clause(code: str) -> Clause:
    """Look a clause up, or say plainly that there is no such clause."""
    try:
        return _CLAUSES[code]
    except KeyError:
        raise BadArgument("clause", code, "not in the rule book") from None


def clause_codes() -> tuple[str, ...]:
    """Every clause code, in the order the book lists them."""
    return tuple(_CLAUSES)


def stages() -> tuple[str, ...]:
    """Every stage that owns at least one clause, in book order."""
    seen: list[str] = []
    for item in _CLAUSES.values():
        if item.stage not in seen:
            seen.append(item.stage)
    return tuple(seen)


def clauses_for_stage(stage: str) -> tuple[Clause, ...]:
    """Every clause one stage owns."""
    found = tuple(c for c in _CLAUSES.values() if c.stage == stage)
    if not found:
        raise BadArgument("stage", stage, "no clause in the book belongs to it")
    return found


def refuse(code: str, subject: str) -> Refused:
    """Build the refusal for a clause. The caller raises it.

    Returning rather than raising keeps `raise refuse(...)` at the call site,
    which is where a reader looks to see what the function does.
    """
    found = clause(code)
    return Refused(subject, f"{found.code}: {found.text}")
