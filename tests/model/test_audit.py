"""Decisions, including the ones that never became plans."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.model.audit import MOST_DETAIL, Decision, Stage

SESSION = "S20260217.0001"
AT = "2026-02-17T09:00:00+00:00"


def a_decision(**changes: object) -> Decision:
    fields: dict[str, object] = {
        "session_ref": SESSION,
        "sequence": 0,
        "at": AT,
        "stage": Stage.SCREENED,
        "subject": "kraken/okx BTC-USD",
        "detail": "the touch does not cross",
    }
    fields.update(changes)
    return Decision(**fields)  # type: ignore[arg-type]


def test_a_screened_decision_stopped_something() -> None:
    assert a_decision().is_negative
    assert Stage.SCREENED.is_negative


def test_a_priced_decision_did_not_stop_anything() -> None:
    assert not a_decision(stage=Stage.PRICED).is_negative
    assert not Stage.LOADED.is_negative


def test_the_cheap_stages_are_the_ones_before_a_depth_walk() -> None:
    assert Stage.LOADED.costs_nothing
    assert Stage.SKIPPED.costs_nothing
    assert Stage.SCREENED.costs_nothing
    assert not Stage.PRICED.costs_nothing
    assert not Stage.REFUSED.costs_nothing


def test_a_negative_sequence_number_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_decision(sequence=-1)


def test_a_decision_about_nothing_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_decision(subject="   ")
    assert caught.value.field == "subject"


def test_a_detail_longer_than_the_cap_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_decision(detail="x" * (MOST_DETAIL + 1))
    assert caught.value.field == "detail"


def test_a_detail_exactly_at_the_cap_is_accepted() -> None:
    assert len(a_decision(detail="x" * MOST_DETAIL).detail) == MOST_DETAIL


def test_only_a_refusal_may_carry_a_clause() -> None:
    with pytest.raises(BadArgument) as caught:
        a_decision(clause="EDGE.01")
    assert caught.value.field == "clause"


def test_a_refusal_with_a_clause_is_accepted() -> None:
    made = a_decision(stage=Stage.REFUSED, clause="EDGE.01")
    assert made.clause == "EDGE.01"


def test_building_trims_the_subject_and_the_detail() -> None:
    made = Decision.build(
        SESSION,
        0,
        at=AT,
        stage=Stage.SKIPPED,
        subject="  okx  ",
        detail="  no trailing volume  ",
    )
    assert made.subject == "okx"
    assert made.detail == "no trailing volume"


def test_building_cuts_a_detail_that_ran_long() -> None:
    made = Decision.build(SESSION, 0, at=AT, stage=Stage.SKIPPED, subject="okx", detail="y" * 1000)
    assert len(made.detail) == MOST_DETAIL


def test_a_decision_is_immutable_once_it_is_built() -> None:
    made = a_decision()
    with pytest.raises(AttributeError):
        made.sequence = 4  # type: ignore[misc]
