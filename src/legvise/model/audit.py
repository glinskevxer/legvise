"""What the scanner decided, including the decisions that never became plans.

A plan row exists only where a pair got as far as being priced. Most of what a
scan does never gets that far: a venue skipped because nobody recorded its
trailing volume, a pair discarded because the touch did not cross, a symbol
dropped because only one venue lists it. None of that leaves a trace in the plan
table, and all of it is the answer to "why did the scanner do nothing today".

So there is a second, cheaper record. One row per decision, with the stage it
was taken at and enough detail to find it again. It is written during the scan
and read afterwards, and it is the difference between a quiet afternoon that was
correct and one that was a configuration error.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from legvise.errors import BadArgument

__all__ = ["Decision", "Stage"]

MOST_DETAIL = 400


class Stage(str, Enum):
    """Where in the scan a decision was taken."""

    LOADED = "loaded"
    SKIPPED = "skipped"
    SCREENED = "screened"
    PRICED = "priced"
    REFUSED = "refused"

    @property
    def is_negative(self) -> bool:
        """True when the decision stopped something from happening."""
        return self in (Stage.SKIPPED, Stage.SCREENED, Stage.REFUSED)

    @property
    def costs_nothing(self) -> bool:
        """True when the decision was taken before any depth walk.

        The cheap stages are the ones a scan takes thousands of; a scan whose
        expensive stages outnumber them is one whose screen is not screening.
        """
        return self in (Stage.LOADED, Stage.SKIPPED, Stage.SCREENED)


@dataclass(frozen=True, slots=True)
class Decision:
    """One thing the scanner decided, and why."""

    session_ref: str
    sequence: int
    at: str
    stage: Stage
    subject: str
    detail: str
    clause: str | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise BadArgument("sequence", self.sequence, "a decision sequence starts at zero")
        if not self.subject.strip():
            raise BadArgument("subject", self.subject, "a decision is about something")
        if len(self.detail) > MOST_DETAIL:
            raise BadArgument(
                "detail",
                f"{len(self.detail)} characters",
                f"a decision detail is at most {MOST_DETAIL}",
            )
        if self.clause is not None and self.stage is not Stage.REFUSED:
            raise BadArgument("clause", self.clause, "only a refusal carries a clause")

    @property
    def is_negative(self) -> bool:
        """True when this decision stopped something."""
        return self.stage.is_negative

    @classmethod
    def build(
        cls,
        session_ref: str,
        sequence: int,
        *,
        at: str,
        stage: Stage,
        subject: str,
        detail: str = "",
        clause: str | None = None,
    ) -> Decision:
        """Build a decision, trimming a detail that ran long."""
        return cls(
            session_ref=session_ref,
            sequence=sequence,
            at=at,
            stage=stage,
            subject=subject.strip(),
            detail=detail.strip()[:MOST_DETAIL],
            clause=clause,
        )
