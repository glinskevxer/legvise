"""Exporting reports, and the decimal handling that keeps them reconcilable."""

from __future__ import annotations

import io
import json

import pytest

from legvise.errors import BadArgument
from legvise.ids import parse_symbol
from legvise.model.book import Side
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.money import dec
from legvise.report.desk_report import DeskStatus, VenueStatus
from legvise.report.edge_report import EdgeReport
from legvise.report.export import (
    LEG_FIELDS,
    PLAN_FIELDS,
    desk_payload,
    edge_payload,
    leg_rows,
    plan_rows,
    session_payload,
    write_csv,
    write_edge_json,
    write_session_json,
)
from legvise.report.session_report import ClauseLine, SessionSummary

SYMBOL = parse_symbol("BTC-USD")


def a_leg(venue: str, takes: Side) -> Leg:
    return Leg(
        venue=venue,
        symbol=SYMBOL,
        takes=takes,
        price=dec("100"),
        size=dec("0.00000001"),
        fee_bps=dec("10"),
        fee_amount=dec("0"),
        levels_swept=1,
        slippage_bps=dec("0"),
    )


def a_plan(**changes: object) -> Plan:
    fields: dict[str, object] = {
        "ref": "S20251020.0001/P000",
        "kind": PlanKind.CROSS_VENUE,
        "symbol": SYMBOL,
        "legs": (a_leg("kraken", Side.ASK), a_leg("okx", Side.BID)),
        "notional": dec("0.00000001"),
        "gross_bps": dec("100"),
        "fee_bps": dec("20"),
        "slippage_bps": dec("0"),
        "rebalance_bps": dec("0"),
        "net_bps": dec("80"),
        "status": PlanStatus.PRICED,
    }
    fields.update(changes)
    return Plan(**fields)  # type: ignore[arg-type]


def a_summary(**changes: object) -> SessionSummary:
    fields: dict[str, object] = {
        "session": "S20251020.0001",
        "started_at": "2025-10-20T09:00:00+00:00",
        "min_edge_bps": dec("2"),
        "plans": 3,
        "actionable": 1,
        "refused": 2,
        "trimmed": 0,
        "symbols": (SYMBOL,),
        "venues": ("kraken", "okx"),
        "best_net_bps": dec("80"),
        "total_notional": dec("200"),
        "clauses": (ClauseLine("EDGE.01", 2, "a plan has to clear the desk minimum edge"),),
    }
    fields.update(changes)
    return SessionSummary(**fields)  # type: ignore[arg-type]


def test_a_plan_row_carries_every_field() -> None:
    row = plan_rows([a_plan()])[0]
    assert set(row) == set(PLAN_FIELDS)


def test_a_tiny_decimal_writes_in_plain_notation() -> None:
    row = plan_rows([a_plan()])[0]
    assert row["notional"] == "0.00000001"


def test_a_plan_with_no_clause_writes_an_empty_cell() -> None:
    assert plan_rows([a_plan()])[0]["clause"] == ""


def test_a_refused_plan_writes_its_clause() -> None:
    plan = a_plan(status=PlanStatus.REFUSED, clause="EDGE.01")
    assert plan_rows([plan])[0]["clause"] == "EDGE.01"


def test_the_venues_are_joined_into_one_cell() -> None:
    assert plan_rows([a_plan()])[0]["venues"] == "kraken/okx"


def test_csv_writes_a_header_and_a_row_each() -> None:
    handle = io.StringIO()
    written = write_csv(handle, plan_rows([a_plan()]), PLAN_FIELDS)
    lines = handle.getvalue().strip().splitlines()
    assert written == 1
    assert lines[0] == ",".join(PLAN_FIELDS)
    assert len(lines) == 2


def test_csv_uses_newlines_rather_than_carriage_returns() -> None:
    handle = io.StringIO()
    write_csv(handle, plan_rows([a_plan()]), PLAN_FIELDS)
    assert "\r" not in handle.getvalue()


def test_csv_refuses_a_row_missing_a_field() -> None:
    handle = io.StringIO()
    with pytest.raises(BadArgument):
        write_csv(handle, [{"ref": "x"}], PLAN_FIELDS)


def test_csv_with_no_rows_still_writes_the_header() -> None:
    handle = io.StringIO()
    assert write_csv(handle, [], PLAN_FIELDS) == 0
    assert handle.getvalue().strip() == ",".join(PLAN_FIELDS)


def test_the_session_json_reads_back_as_it_was_written() -> None:
    handle = io.StringIO()
    payload = write_session_json(handle, a_summary())
    assert json.loads(handle.getvalue()) == payload


def test_session_json_writes_decimals_as_text() -> None:
    handle = io.StringIO()
    write_session_json(handle, a_summary())
    read = json.loads(handle.getvalue())
    assert read["min_edge_bps"] == "2"
    assert isinstance(read["plans"], int)


def test_session_json_carries_the_clause_wording() -> None:
    handle = io.StringIO()
    write_session_json(handle, a_summary())
    read = json.loads(handle.getvalue())
    assert read["clauses"][0]["code"] == "EDGE.01"
    assert read["clauses"][0]["hits"] == 2


def test_a_session_with_no_best_edge_writes_an_empty_string() -> None:
    handle = io.StringIO()
    write_session_json(handle, a_summary(best_net_bps=None))
    assert json.loads(handle.getvalue())["best_net_bps"] == ""


def test_an_empty_edge_report_writes_zeroes() -> None:
    handle = io.StringIO()
    payload = write_edge_json(handle, EdgeReport(lines=()))
    assert payload["plans"] == 0
    assert payload["lines"] == []
    assert json.loads(handle.getvalue()) == payload


def test_the_json_ends_with_a_newline() -> None:
    handle = io.StringIO()
    write_edge_json(handle, EdgeReport(lines=()))
    assert handle.getvalue().endswith("\n")


def test_a_leg_row_carries_every_field() -> None:
    row = leg_rows([a_plan()])[0]
    assert set(row) == set(LEG_FIELDS)


def test_a_plan_contributes_one_row_per_leg() -> None:
    assert len(leg_rows([a_plan()])) == 2


def test_a_leg_row_names_the_side_in_words() -> None:
    rows = leg_rows([a_plan()])
    assert rows[0]["side"] == "buy"
    assert rows[1]["side"] == "sell"


def test_a_leg_row_numbers_the_legs_from_zero() -> None:
    rows = leg_rows([a_plan()])
    assert [row["leg_index"] for row in rows] == ["0", "1"]


def test_a_leg_row_carries_the_plan_it_belongs_to() -> None:
    assert all(row["plan_ref"] == a_plan().ref for row in leg_rows([a_plan()]))


def test_a_leg_row_writes_its_notional_in_plain_notation() -> None:
    assert leg_rows([a_plan()])[0]["notional"] == "0.00000100"


def test_the_leg_export_writes_a_header_and_a_row_each() -> None:
    handle = io.StringIO()
    written = write_csv(handle, leg_rows([a_plan()]), LEG_FIELDS)
    assert written == 2
    assert handle.getvalue().splitlines()[0] == ",".join(LEG_FIELDS)


def test_the_leg_export_with_no_plans_still_writes_the_header() -> None:
    handle = io.StringIO()
    assert write_csv(handle, leg_rows([]), LEG_FIELDS) == 0
    assert handle.getvalue().strip() == ",".join(LEG_FIELDS)


# The payload builders. Each one is the single shape its report goes out in,
# whether it is printed, piped or written to a file.


def test_a_session_payload_writes_every_decimal_as_text() -> None:
    payload = session_payload(a_summary())
    assert payload["min_edge_bps"] == "2"
    assert payload["total_notional"] == "200"
    assert payload["best_net_bps"] == "80"


def test_a_session_payload_spells_its_symbols_out() -> None:
    assert session_payload(a_summary())["symbols"] == ["BTC-USD"]


def test_a_session_payload_lists_a_clause_as_an_object() -> None:
    clauses = session_payload(a_summary())["clauses"]
    assert clauses == [
        {"code": "EDGE.01", "hits": 2, "text": "a plan has to clear the desk minimum edge"}
    ]


def test_a_session_payload_keeps_its_counts_as_numbers() -> None:
    payload = session_payload(a_summary())
    assert payload["plans"] == 3
    assert payload["actionable"] == 1


def test_a_session_payload_is_what_the_writer_writes() -> None:
    handle = io.StringIO()
    written = write_session_json(handle, a_summary())
    assert written == session_payload(a_summary())
    assert json.loads(handle.getvalue()) == written


def test_an_edge_payload_is_what_the_writer_writes() -> None:
    report = EdgeReport(lines=())
    handle = io.StringIO()
    assert write_edge_json(handle, report) == edge_payload(report)


def test_an_empty_edge_payload_still_carries_every_key() -> None:
    payload = edge_payload(EdgeReport(lines=()))
    assert payload["plans"] == 0
    assert payload["lines"] == []
    assert payload["leg_risk_plans"] == []


def test_a_desk_payload_carries_the_verdict_as_a_field() -> None:
    status = DeskStatus(venues=(), shared_symbols=(), last_session=None, sessions=0)
    payload = desk_payload(status)
    assert payload["can_scan"] is False
    assert payload["last_session"] is None


def test_a_desk_payload_names_what_each_venue_is_missing() -> None:
    venue = VenueStatus(code="kraken", active=True, markets=0, books=0, gaps=("no fee ladder",))
    status = DeskStatus(venues=(venue,), shared_symbols=(), last_session=None, sessions=0)
    payload = desk_payload(status)
    assert payload["venues"] == [
        {
            "venue": "kraken",
            "active": True,
            "markets": 0,
            "books": 0,
            "ready": False,
            "gaps": ["no fee ladder"],
        }
    ]
    assert payload["gaps"] == ["kraken: no fee ladder"]


def test_a_desk_payload_spells_the_shared_markets_out() -> None:
    status = DeskStatus(venues=(), shared_symbols=(SYMBOL,), last_session="S1", sessions=2)
    assert desk_payload(status)["shared_markets"] == ["BTC-USD"]


def test_every_payload_survives_a_round_trip_through_json() -> None:
    status = DeskStatus(venues=(), shared_symbols=(SYMBOL,), last_session=None, sessions=0)
    for payload in (
        session_payload(a_summary()),
        edge_payload(EdgeReport(lines=())),
        desk_payload(status),
    ):
        assert json.loads(json.dumps(payload)) == payload
