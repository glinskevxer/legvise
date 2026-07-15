"""One whole day of the desk, end to end."""

from __future__ import annotations

import pytest

from legvise.money import dec
from legvise.tools.smoke import main, run


def test_the_whole_run_comes_back_clean() -> None:
    assert main(("--quiet",)) == 0


def test_the_run_finds_exactly_one_plan() -> None:
    outcome = run(quiet=True)
    assert outcome["plans"] == 1
    assert outcome["actionable"] == 1


def test_the_session_reference_carries_the_day_it_ran() -> None:
    assert str(run(quiet=True)["session"]).startswith("S20260203.")


def test_a_clean_fill_realises_what_the_plan_expected() -> None:
    outcome = run(quiet=True)
    assert outcome["realised_bps"] == outcome["net_bps"]


def test_the_edge_survives_two_sets_of_taker_fees() -> None:
    outcome = run(quiet=True)
    assert dec("80") < outcome["net_bps"] < dec("100")  # type: ignore[operator]


def test_the_notional_is_the_buy_leg_notional() -> None:
    assert run(quiet=True)["notional"] == dec("200.00")


def test_the_run_prints_its_numbers_when_it_is_not_quiet(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run()
    printed = capsys.readouterr().out
    assert "smoke: session" in printed
    assert "smoke: net_bps" in printed


def test_a_quiet_run_prints_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    run(quiet=True)
    assert capsys.readouterr().out == ""


def test_the_run_gives_the_same_answer_twice() -> None:
    assert run(quiet=True) == run(quiet=True)


def test_the_command_reports_clean_on_success(capsys: pytest.CaptureFixture[str]) -> None:
    main(("--quiet",))
    assert "smoke: clean" in capsys.readouterr().out


def test_the_triangular_pass_searches_the_one_venue_that_closes_a_loop() -> None:
    outcome = run(quiet=True)
    assert outcome["loops_written"] == 1


def test_the_two_passes_get_different_sessions() -> None:
    outcome = run(quiet=True)
    assert outcome["session"] != outcome["loop_session"]


def test_both_venues_come_out_ready_to_scan() -> None:
    assert run(quiet=True)["venues_ready"] == 2


def test_the_loop_session_reference_carries_the_same_day() -> None:
    outcome = run(quiet=True)
    assert str(outcome["loop_session"])[:9] == str(outcome["session"])[:9]


def test_the_run_prints_the_loop_numbers_too(capsys: pytest.CaptureFixture[str]) -> None:
    run()
    printed = capsys.readouterr().out
    assert "smoke: loops_written" in printed
    assert "smoke: venues_ready" in printed
