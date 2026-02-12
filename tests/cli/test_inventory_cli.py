"""The inventory command group."""

from __future__ import annotations

import pytest

from tests.cli.conftest import Run


@pytest.fixture()
def held(seeded: Run) -> Run:
    seeded("inventory", "set-balance", "kraken", "BTC", "5")
    seeded("inventory", "set-balance", "okx", "BTC", "2")
    seeded("inventory", "set-balance", "kraken", "USD", "400000")
    seeded(
        "inventory", "set-band", "kraken", "BTC", "--floor", "1", "--target", "5", "--ceiling", "9"
    )
    return seeded


def test_recording_a_balance_reports_the_total(seeded: Run) -> None:
    result = seeded("inventory", "set-balance", "kraken", "BTC", "4.5", "--locked", "0.5")
    assert "kraken holds 5.0 BTC" in result.output


def test_a_negative_balance_is_refused(seeded: Run) -> None:
    # The double dash is click's, not ours: a bare -1 reads as an option.
    seeded("inventory", "set-balance", "--", "kraken", "BTC", "-1", expect=1)


def test_setting_a_band_reports_all_three_numbers(seeded: Run) -> None:
    result = seeded(
        "inventory", "set-band", "kraken", "BTC", "--floor", "1", "--target", "5", "--ceiling", "9"
    )
    assert "band is 1/5/9" in result.output


def test_a_target_outside_the_band_is_refused(seeded: Run) -> None:
    seeded(
        "inventory",
        "set-band",
        "kraken",
        "BTC",
        "--floor",
        "5",
        "--target",
        "1",
        "--ceiling",
        "9",
        expect=1,
    )


def test_showing_everything_lists_every_holding(held: Run) -> None:
    lines = held("inventory", "show").output.strip().splitlines()
    assert len(lines) == 5


def test_a_holding_with_no_band_says_so(held: Run) -> None:
    output = held("inventory", "show", "--asset", "USD").output
    assert "no band" in output


def test_a_holding_inside_its_band_says_so(held: Run) -> None:
    output = held("inventory", "show", "--venue", "kraken").output
    assert "in band" in output


def test_a_holding_under_its_floor_says_so(held: Run) -> None:
    held("inventory", "set-balance", "kraken", "BTC", "0.5")
    assert "under floor" in held("inventory", "show", "--venue", "kraken").output


def test_a_holding_over_its_ceiling_says_so(held: Run) -> None:
    held("inventory", "set-balance", "kraken", "BTC", "12")
    assert "over ceiling" in held("inventory", "show", "--venue", "kraken").output


def test_showing_by_venue_and_asset_at_once_is_a_usage_error(held: Run) -> None:
    result = held("inventory", "show", "--venue", "kraken", "--asset", "BTC", expect=2)
    assert "not both" in result.output


def test_room_prints_both_directions_of_the_band(held: Run) -> None:
    output = held("inventory", "room", "kraken", "BTC").output
    assert "spendable   4" in output
    assert "receivable  4" in output


def test_room_without_a_band_refuses(held: Run) -> None:
    result = held("inventory", "room", "kraken", "USD", expect=1)
    assert "inventory band" in result.output


def test_room_without_a_balance_refuses(held: Run) -> None:
    result = held("inventory", "room", "okx", "USD", expect=1)
    assert "position" in result.output


def test_clearing_a_band_takes_it_off_the_listing(held: Run) -> None:
    held("inventory", "clear-band", "kraken", "BTC")
    assert "in band" not in held("inventory", "show", "--venue", "kraken").output


def test_clearing_a_band_that_is_not_there_fails(held: Run) -> None:
    held("inventory", "clear-band", "okx", "BTC", expect=1)


def loose(run: Run, *extra: str) -> str:
    """The concentration command with limits the fixture does not trip.

    The venue share is one because the fixture holds all its cash on kraken,
    which is a real hundred percent rather than a rounding artefact.
    """
    return run(
        "inventory",
        "concentration",
        "--mark",
        "BTC:100000",
        "--mark",
        "USD:1",
        "--max-asset-share",
        "0.9",
        "--max-venue-share",
        "1",
        *extra,
    ).output


def test_the_concentration_command_values_the_desk(held: Run) -> None:
    assert "desk value  1100000" in loose(held)


def test_the_concentration_command_reports_a_share_per_asset(held: Run) -> None:
    output = loose(held)
    assert "BTC" in output
    assert "USD" in output


def test_the_concentration_command_names_the_venues_holding_an_asset(held: Run) -> None:
    output = loose(held)
    assert "kraken=" in output
    assert "okx=" in output


def test_a_desk_inside_both_limits_says_so(held: Run) -> None:
    assert "inside both concentration limits" in loose(held)


def test_a_desk_too_heavy_in_one_asset_fails_the_command(held: Run) -> None:
    result = held(
        "inventory",
        "concentration",
        "--mark",
        "BTC:100000",
        "--mark",
        "USD:1",
        "--max-asset-share",
        "0.3",
        expect=1,
    )
    assert "CAP.02" in result.output


def test_a_desk_with_all_of_one_asset_in_one_place_fails_the_command(held: Run) -> None:
    result = held(
        "inventory",
        "concentration",
        "--mark",
        "BTC:100000",
        "--mark",
        "USD:1",
        "--max-asset-share",
        "0.9",
        "--max-venue-share",
        "0.8",
        expect=1,
    )
    assert "on kraken" in result.output


def test_a_mark_that_is_not_a_pair_is_a_usage_error(held: Run) -> None:
    result = held("inventory", "concentration", "--mark", "BTC", expect=2)
    assert "ASSET:PRICE" in result.output


def test_a_held_asset_with_no_mark_fails_the_command(held: Run) -> None:
    result = held("inventory", "concentration", "--mark", "BTC:100000", expect=1)
    assert "USD" in result.output
