"""Reading a book back and finding what nothing on the write path could write.

Every defect here is planted with raw SQL on purpose. The point of the module
is to catch a file that something other than this tool has been at, so a test
that plants a defect through the stores would be testing that the stores refuse
it, which they already do somewhere else.
"""

from __future__ import annotations

import pytest

from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.fill import Fill
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.store.db import Database
from legvise.store.fills import FillStore
from legvise.store.integrity import (
    Finding,
    check_book,
    decimal_spelling,
    findings_by_kind,
    leg_counts,
    leg_notionals,
    orphan_fills,
    plan_arithmetic,
)
from legvise.store.plans import PlanStore
from legvise.store.venues import VenueStore
from tests.conftest import make_venue

SESSION = "S20250811.0001"
REF = f"{SESSION}/P000"
SYMBOL = parse_symbol("BTC-USD")


def a_leg(venue: str, takes: Side, price: str) -> Leg:
    """One side of the plan, two units at a flat price."""
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec(price),
        size=dec("2"),
        fee_bps=dec("10"),
        fee_amount=dec("0.2"),
        levels_swept=1,
        slippage_bps=dec("0"),
    )


def a_plan(ref: str = REF, **changes: object) -> Plan:
    """A plan whose components reach its net edge."""
    fields: dict[str, object] = {
        "ref": ref,
        "kind": PlanKind.CROSS_VENUE,
        "symbol": SYMBOL,
        "legs": (a_leg("kraken", Side.ASK, "100"), a_leg("okx", Side.BID, "101")),
        "notional": dec("200"),
        "gross_bps": dec("100"),
        "fee_bps": dec("20"),
        "slippage_bps": dec("0"),
        "rebalance_bps": dec("0"),
        "net_bps": dec("80"),
        "status": PlanStatus.PRICED,
    }
    fields.update(changes)
    return Plan(**fields)  # type: ignore[arg-type]


@pytest.fixture()
def booked(db: Database) -> Database:
    """A book with two venues, one session and one sound plan on it."""
    venues = VenueStore(db)
    for code in ("kraken", "okx"):
        venues.add(make_venue(code))
    store = PlanStore(db)
    store.open_session(
        SESSION,
        started_at="2025-08-11T09:00:00+00:00",
        min_edge_bps=dec("2"),
        pairing_window_ms=250,
        wanted_size=dec("1"),
    )
    store.add(a_plan(), session_ref=SESSION)
    return db


def test_a_book_this_tool_wrote_adds_up(booked: Database) -> None:
    assert check_book(booked) == ()


def test_an_empty_book_adds_up(db: Database) -> None:
    assert check_book(db) == ()


def test_a_tampered_net_edge_is_found(booked: Database) -> None:
    booked.execute("UPDATE plan SET net_bps = '95' WHERE ref = ?", (REF,))
    found = plan_arithmetic(booked)
    assert len(found) == 1
    assert found[0].kind == "arithmetic"
    assert found[0].subject == REF


def test_a_tampered_net_edge_says_what_the_components_reach(booked: Database) -> None:
    booked.execute("UPDATE plan SET net_bps = '95' WHERE ref = ?", (REF,))
    assert "components reach 80" in plan_arithmetic(booked)[0].detail


def test_a_tampered_fee_is_found_by_the_same_check(booked: Database) -> None:
    booked.execute("UPDATE plan SET fee_bps = '5' WHERE ref = ?", (REF,))
    assert [f.kind for f in plan_arithmetic(booked)] == ["arithmetic"]


def test_a_notional_that_lost_a_digit_is_found(booked: Database) -> None:
    booked.execute("UPDATE plan SET notional = '20' WHERE ref = ?", (REF,))
    found = leg_notionals(booked)
    assert len(found) == 1
    assert "its entry leg moves 200" in found[0].detail


def test_a_notional_off_by_rounding_is_left_alone(booked: Database) -> None:
    booked.execute("UPDATE plan SET notional = '200.00000001' WHERE ref = ?", (REF,))
    assert leg_notionals(booked) == []


def test_a_notional_off_by_a_factor_is_found(booked: Database) -> None:
    booked.execute("UPDATE plan SET notional = '2000' WHERE ref = ?", (REF,))
    assert len(leg_notionals(booked)) == 1


def test_a_plan_that_lost_a_leg_is_found(booked: Database) -> None:
    booked.execute("DELETE FROM plan_leg WHERE plan_ref = ? AND leg_index = 1", (REF,))
    found = leg_counts(booked)
    assert len(found) == 1
    assert "has 1 legs on file" in found[0].detail


def test_a_plan_with_both_legs_is_left_alone(booked: Database) -> None:
    assert leg_counts(booked) == []


def test_a_fill_on_a_leg_that_is_gone_is_found(booked: Database) -> None:
    FillStore(booked).add(
        Fill.build(
            REF, 1, "okx", Side.BID, price="101", size="2", filled_at="2025-08-11T09:01:00+00:00"
        ),
        venue_trade_id="t1",
    )
    booked.execute("DELETE FROM plan_leg WHERE plan_ref = ? AND leg_index = 1", (REF,))
    found = orphan_fills(booked)
    assert len(found) == 1
    assert "leg 1" in found[0].detail


def test_a_fill_on_a_leg_that_exists_is_left_alone(booked: Database) -> None:
    FillStore(booked).add(
        Fill.build(
            REF, 0, "kraken", Side.ASK, price="100", size="2", filled_at="2025-08-11T09:01:00+00:00"
        ),
        venue_trade_id="t1",
    )
    assert orphan_fills(booked) == []


def test_a_number_in_exponent_notation_is_found(booked: Database) -> None:
    booked.execute("UPDATE plan SET notional = '2E+2' WHERE ref = ?", (REF,))
    found = decimal_spelling(booked)
    assert len(found) == 1
    assert "2E+2" in found[0].detail


def test_both_number_columns_are_read_for_notation(booked: Database) -> None:
    booked.execute("UPDATE plan SET notional = '2E+2', net_bps = '8E+1' WHERE ref = ?", (REF,))
    assert len(decimal_spelling(booked)) == 2


def test_a_plain_number_is_left_alone(booked: Database) -> None:
    assert decimal_spelling(booked) == []


def test_every_check_runs_even_when_an_earlier_one_found_something(booked: Database) -> None:
    booked.execute("UPDATE plan SET net_bps = '2E+1' WHERE ref = ?", (REF,))
    kinds = {finding.kind for finding in check_book(booked)}
    assert kinds == {"arithmetic", "notation"}


def test_the_findings_are_counted_by_kind(booked: Database) -> None:
    booked.execute("UPDATE plan SET net_bps = '95', notional = '20' WHERE ref = ?", (REF,))
    counts = findings_by_kind(check_book(booked))
    assert counts == {"arithmetic": 1, "notional": 1}


def test_the_busiest_kind_is_counted_first(booked: Database) -> None:
    store = PlanStore(booked)
    for index in (1, 2):
        store.add(a_plan(f"{SESSION}/P{index:03d}"), session_ref=SESSION)
    booked.execute("UPDATE plan SET net_bps = '95'")
    booked.execute("UPDATE plan SET notional = '20' WHERE ref = ?", (REF,))
    assert list(findings_by_kind(check_book(booked))) == ["arithmetic", "notional"]


def test_counting_an_empty_book_gives_nothing(db: Database) -> None:
    assert findings_by_kind(check_book(db)) == {}


def test_a_finding_prints_its_kind_and_its_row() -> None:
    line = str(Finding(kind="notional", subject=REF, detail="says 20"))
    assert line == f"notional  {REF}  says 20"


def test_every_finding_names_the_row_it_is_about(booked: Database) -> None:
    booked.execute("UPDATE plan SET net_bps = '95', notional = '2E+1' WHERE ref = ?", (REF,))
    for finding in check_book(booked):
        assert finding.subject
        assert finding.detail
