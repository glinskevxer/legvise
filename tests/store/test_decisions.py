"""Decision storage, append only and cheap."""

from __future__ import annotations

import pytest

from legvise.errors import NotFound
from legvise.model.audit import Decision, Stage
from legvise.money import dec
from legvise.store.db import Database
from legvise.store.decisions import DecisionStore
from legvise.store.plans import PlanStore

SESSION = "S20260224.0001"
AT = "2026-02-24T09:00:00+00:00"


def a_decision(sequence: int, stage: Stage = Stage.SCREENED, **changes: object) -> Decision:
    fields: dict[str, object] = {
        "session_ref": SESSION,
        "sequence": sequence,
        "at": AT,
        "stage": stage,
        "subject": f"kraken/okx BTC-USD {sequence}",
        "detail": "the touch does not cross",
    }
    fields.update(changes)
    return Decision(**fields)  # type: ignore[arg-type]


@pytest.fixture()
def store(db: Database) -> DecisionStore:
    PlanStore(db).open_session(
        SESSION,
        started_at=AT,
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("1"),
    )
    return DecisionStore(db)


def test_a_decision_survives_a_round_trip(store: DecisionStore) -> None:
    given = a_decision(0)
    store.add(given)
    assert store.for_session(SESSION) == (given,)


def test_decisions_come_back_in_the_order_they_were_taken(store: DecisionStore) -> None:
    store.add(a_decision(2))
    store.add(a_decision(0))
    store.add(a_decision(1))
    assert [d.sequence for d in store.for_session(SESSION)] == [0, 1, 2]


def test_the_same_sequence_twice_in_one_session_is_refused(store: DecisionStore) -> None:
    store.add(a_decision(0))
    with pytest.raises(Exception):  # noqa: B017 - sqlite reports the key generically
        store.add(a_decision(0))


def test_a_decision_needs_a_session_that_exists(store: DecisionStore) -> None:
    stray = a_decision(0, session_ref="S19990101.0001")
    with pytest.raises(Exception):  # noqa: B017 - sqlite reports the key generically
        store.add(stray)


def test_a_batch_goes_in_together(store: DecisionStore) -> None:
    assert store.add_all((a_decision(0), a_decision(1), a_decision(2))) == 3
    assert len(store.for_session(SESSION)) == 3


def test_a_batch_that_breaks_leaves_nothing_behind(store: DecisionStore) -> None:
    with pytest.raises(Exception):  # noqa: B017 - sqlite reports the key generically
        store.add_all((a_decision(0), a_decision(0)))
    assert store.count() == 0


def test_one_stage_can_be_read_on_its_own(store: DecisionStore) -> None:
    store.add(a_decision(0, Stage.SCREENED))
    store.add(a_decision(1, Stage.SKIPPED))
    assert len(store.at_stage(SESSION, Stage.SKIPPED)) == 1


def test_the_stage_counts_come_back_busiest_first(store: DecisionStore) -> None:
    store.add(a_decision(0, Stage.SCREENED))
    store.add(a_decision(1, Stage.SCREENED))
    store.add(a_decision(2, Stage.SKIPPED))
    assert list(store.stage_counts(SESSION)) == ["screened", "skipped"]


def test_a_session_with_no_decisions_counts_nothing(store: DecisionStore) -> None:
    assert store.stage_counts(SESSION) == {}


def test_requiring_decisions_on_an_empty_session_is_a_not_found(
    store: DecisionStore,
) -> None:
    with pytest.raises(NotFound):
        store.require_any(SESSION)


def test_the_next_sequence_starts_at_zero(store: DecisionStore) -> None:
    assert store.next_sequence(SESSION) == 0


def test_the_next_sequence_follows_the_highest_written(store: DecisionStore) -> None:
    store.add(a_decision(0))
    store.add(a_decision(4))
    assert store.next_sequence(SESSION) == 5


def test_a_refusal_keeps_its_clause_through_the_round_trip(store: DecisionStore) -> None:
    store.add(a_decision(0, Stage.REFUSED, clause="EDGE.01"))
    assert store.for_session(SESSION)[0].clause == "EDGE.01"


def test_dropping_a_session_takes_its_decisions(db: Database, store: DecisionStore) -> None:
    store.add(a_decision(0))
    db.execute("DELETE FROM scan_session WHERE ref = ?", (SESSION,))
    assert store.count() == 0
