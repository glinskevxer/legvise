"""The fee command group."""

from __future__ import annotations

import pytest

from tests.cli.conftest import Run

RUNGS = ("0:10:16", "1000000:6:10", "25000000:0:6")


def rung_lines(output: str) -> list[str]:
    """The table body, without the header, the rule or the stderr note."""
    lines = output.strip().splitlines()
    return [line for line in lines[2:] if "no trailing volume" not in line]


@pytest.fixture()
def laddered(seeded: Run) -> Run:
    seeded("fee", "set-ladder", "kraken", *RUNGS)
    return seeded


def test_setting_a_ladder_reports_how_many_rungs_it_has(seeded: Run) -> None:
    result = seeded("fee", "set-ladder", "kraken", *RUNGS)
    assert "3 rungs" in result.output


def test_a_rung_that_is_not_three_parts_is_a_usage_error(seeded: Run) -> None:
    result = seeded("fee", "set-ladder", "kraken", "0:10", expect=2)
    assert "VOLUME:MAKER:TAKER" in result.output


def test_a_ladder_that_does_not_start_at_zero_is_refused(seeded: Run) -> None:
    seeded("fee", "set-ladder", "kraken", "1000:10:16", expect=1)


def test_showing_a_ladder_prints_every_rung(laddered: Run) -> None:
    assert len(rung_lines(laddered("fee", "show-ladder", "kraken").output)) == 3


def test_no_rung_is_marked_until_a_volume_is_recorded(laddered: Run) -> None:
    result = laddered("fee", "show-ladder", "kraken")
    assert "no trailing volume on file" in result.output


def test_recording_a_volume_marks_the_rung_it_reaches(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "2000000")
    output = laddered("fee", "show-ladder", "kraken").output
    marked = [line for line in output.splitlines() if line.startswith("*")]
    assert len(marked) == 1
    assert "1000000" in marked[0]


def test_the_rate_command_prints_the_taker_side_by_default(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "2000000")
    assert laddered("fee", "rate", "kraken").output.strip() == "10"


def test_the_rate_command_can_print_the_maker_side(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "2000000")
    assert laddered("fee", "rate", "kraken", "--resting").output.strip() == "6"


def test_the_rate_command_refuses_without_a_volume(laddered: Run) -> None:
    result = laddered("fee", "rate", "kraken", expect=1)
    assert "FEE.01" in result.output


def test_the_rate_command_refuses_without_a_ladder(seeded: Run) -> None:
    result = seeded("fee", "rate", "kraken", expect=1)
    assert "fee ladder" in result.output


def test_clearing_a_volume_puts_the_rate_command_back_to_refusing(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "2000000")
    laddered("fee", "clear-volume", "kraken")
    laddered("fee", "rate", "kraken", expect=1)


def test_replacing_a_ladder_shortens_it(laddered: Run) -> None:
    laddered("fee", "set-ladder", "kraken", "0:8:12")
    assert len(rung_lines(laddered("fee", "show-ladder", "kraken").output)) == 1


def test_a_volume_that_is_not_a_number_is_refused(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "lots", expect=1)


def test_the_funding_command_reports_what_the_fee_needs(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "0")
    laddered("inventory", "set-balance", "kraken", "OKB", "100")
    output = laddered(
        "fee",
        "funding",
        "kraken",
        "10000",
        "--fee-asset",
        "OKB",
        "--fee-asset-price",
        "50",
    ).output
    assert "needed" in output
    assert "available  100" in output


def test_the_funding_command_counts_the_cycles_the_balance_covers(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "0")
    laddered("inventory", "set-balance", "kraken", "OKB", "100")
    line = next(
        row
        for row in laddered(
            "fee",
            "funding",
            "kraken",
            "10000",
            "--fee-asset",
            "OKB",
            "--fee-asset-price",
            "50",
        ).output.splitlines()
        if row.startswith("cycles")
    )
    assert int(line.split()[1]) > 1


def test_the_funding_command_says_the_discount_is_safe(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "0")
    laddered("inventory", "set-balance", "kraken", "OKB", "100")
    output = laddered(
        "fee",
        "funding",
        "kraken",
        "10000",
        "--fee-asset",
        "OKB",
        "--fee-asset-price",
        "50",
        "--discount-bps",
        "2500",
    ).output
    assert "the discount is safe to price" in output


def test_the_funding_command_refuses_when_the_desk_holds_none(laddered: Run) -> None:
    laddered("fee", "record-volume", "kraken", "0")
    result = laddered(
        "fee",
        "funding",
        "kraken",
        "10000",
        "--fee-asset",
        "OKB",
        "--fee-asset-price",
        "50",
        expect=1,
    )
    assert "FEE.01" in result.output


def test_the_funding_command_needs_a_recorded_volume(laddered: Run) -> None:
    laddered(
        "fee",
        "funding",
        "kraken",
        "10000",
        "--fee-asset",
        "OKB",
        "--fee-asset-price",
        "50",
        expect=1,
    )
