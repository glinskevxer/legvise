"""The fill command group, against a plan a real scan produced."""

from __future__ import annotations

import pytest

from tests.cli.conftest import Run
from tests.cli.test_scan_cli import wire


@pytest.fixture()
def planned(run: Run) -> tuple[Run, str]:
    desk = wire(run)
    desk("book", "load", "kraken", "BTC-USD", "--bid", "99.00:50", "--ask", "100.00:50")
    desk("book", "load", "okx", "BTC-USD", "--bid", "101.00:50", "--ask", "102.00:50")
    output = desk("scan", "run", "--window-ms", "600000", "--size", "2").output
    session = next(line.split()[1] for line in output.splitlines() if line.startswith("session"))
    ref = desk("plan", "best", session).output.split()[0]
    return (desk, ref)


def test_recording_a_fill_reports_it(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    result = desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    assert "leg 0" in result.output


def test_a_leg_index_past_the_end_is_a_usage_error(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    result = desk("fill", "record", ref, "5", "t1", "--price", "100", "--size", "2", expect=2)
    assert "legs" in result.output


def test_a_plan_that_is_not_there_fails(planned: tuple[Run, str]) -> None:
    desk, _ = planned
    desk(
        "fill",
        "record",
        "S19990101.0001/P000",
        "0",
        "t1",
        "--price",
        "100",
        "--size",
        "2",
        expect=1,
    )


def test_the_same_trade_id_twice_is_refused(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "1")
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "1", expect=1)


def test_listing_fills_shows_the_side(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    output = desk("fill", "list", ref).output
    assert "buy" in output
    assert "sell" in output


def test_an_unfilled_plan_reads_as_two_misses(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    output = desk("fill", "outcome", ref).output
    assert output.count("missed") == 2


def test_a_filled_plan_reads_as_two_fills(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    body = desk("fill", "outcome", ref).output.splitlines()[2:]
    assert sum(1 for line in body if " filled " in line) == 2


def test_a_partial_fill_reads_as_partial(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "1")
    assert "partial" in desk("fill", "outcome", ref).output


def test_an_unfilled_leg_shows_a_dash_for_its_realised_price(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    assert "-" in desk("fill", "outcome", ref).output


def test_attribution_on_an_unfilled_plan_realises_nothing(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    output = desk("fill", "attribution", ref).output
    assert "realised     0.00 bps" in output


def test_attribution_reports_the_price_drift_it_measured(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100.5", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    output = desk("fill", "attribution", ref).output
    drift = next(line for line in output.splitlines() if line.startswith("price drift"))
    assert drift.split()[2] == "50.00"


def test_attribution_shouts_about_leg_risk(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    assert "LEG RISK" in desk("fill", "attribution", ref).output


def test_attribution_stays_quiet_when_both_legs_filled(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk("fill", "record", ref, "0", "t1", "--price", "100", "--size", "2")
    desk("fill", "record", ref, "1", "t2", "--price", "101", "--size", "2")
    assert "LEG RISK" not in desk("fill", "attribution", ref).output


def test_a_fill_stamped_by_hand_keeps_its_time(planned: tuple[Run, str]) -> None:
    desk, ref = planned
    desk(
        "fill",
        "record",
        ref,
        "0",
        "t1",
        "--price",
        "100",
        "--size",
        "2",
        "--at",
        "2025-09-24T09:00:01+00:00",
    )
    assert "2025-09-24T09:00:01+00:00" in desk("fill", "list", ref).output
