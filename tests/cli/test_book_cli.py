"""The book command group."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from legvise.cli.main import cli
from tests.cli.conftest import Run


@pytest.fixture()
def loaded(seeded: Run) -> Run:
    seeded(
        "book",
        "load",
        "kraken",
        "BTC-USD",
        "--bid",
        "99.00:2",
        "--bid",
        "98.50:5",
        "--ask",
        "100.00:1",
        "--ask",
        "100.50:4",
        "--observed-at",
        "2025-08-01T09:00:00+00:00",
    )
    return seeded


def test_loading_a_snapshot_reports_the_level_counts(seeded: Run) -> None:
    result = seeded("book", "load", "kraken", "BTC-USD", "--bid", "99:1", "--ask", "100:1")
    assert "2x1 levels" not in result.output
    assert "1x1 levels" in result.output


def test_a_level_that_is_not_price_and_size_is_a_usage_error(seeded: Run) -> None:
    result = seeded("book", "load", "kraken", "BTC-USD", "--bid", "99", expect=2)
    assert "PRICE:SIZE" in result.output


def test_a_crossed_snapshot_is_refused(seeded: Run) -> None:
    seeded("book", "load", "kraken", "BTC-USD", "--bid", "101:1", "--ask", "100:1", expect=1)


def test_bids_in_the_wrong_order_are_refused(seeded: Run) -> None:
    seeded(
        "book",
        "load",
        "kraken",
        "BTC-USD",
        "--bid",
        "98:1",
        "--bid",
        "99:1",
        "--ask",
        "100:1",
        expect=1,
    )


def test_showing_a_book_prints_both_sides(loaded: Run) -> None:
    output = loaded("book", "show", "kraken", "BTC-USD").output
    assert "99.00" in output
    assert "100.00" in output


def test_showing_a_book_prints_the_mid_and_the_spread(loaded: Run) -> None:
    output = loaded("book", "show", "kraken", "BTC-USD").output
    assert "mid 99.50000000" in output
    assert "spread 100.50 bps" in output
    assert "bps" in output


def test_showing_a_book_reports_when_it_was_observed(loaded: Run) -> None:
    assert "2025-08-01T09:00:00" in loaded("book", "show", "kraken", "BTC-USD").output


def test_the_depth_printed_can_be_limited(loaded: Run) -> None:
    lines = loaded("book", "show", "kraken", "BTC-USD", "--depth", "1").output.splitlines()
    assert len(lines) == 5


def test_a_market_with_no_snapshot_is_a_not_found(seeded: Run) -> None:
    result = seeded("book", "show", "kraken", "BTC-USD", expect=1)
    assert "book snapshot" in result.output


def test_the_touch_command_crosses_the_venues(loaded: Run) -> None:
    loaded("book", "load", "okx", "BTC-USD", "--bid", "101:1", "--ask", "102:1")
    output = loaded("book", "touch", "BTC-USD").output
    assert "kraken" in output
    assert "okx" in output


def test_a_one_sided_book_shows_a_dash_at_the_touch(seeded: Run) -> None:
    seeded("book", "load", "kraken", "BTC-USD", "--bid", "99:1")
    assert "-" in seeded("book", "touch", "BTC-USD").output


def test_levels_prints_one_side_machine_readably(loaded: Run) -> None:
    output = loaded("book", "levels", "kraken", "BTC-USD", "bid").output
    assert output.strip().splitlines() == ["99.00:2", "98.50:5"]


def test_an_unknown_side_is_a_usage_error(loaded: Run) -> None:
    loaded("book", "levels", "kraken", "BTC-USD", "middle", expect=2)


def test_a_snapshot_can_be_read_from_standard_input(seeded: Run, book: object) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--db", str(book), "book", "load", "kraken", "BTC-USD", "--stdin"],
        input="bid:99:2\nask:100:1\n\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "1x1 levels" in result.output


def test_a_standard_input_line_that_is_not_three_parts_is_a_usage_error(
    seeded: Run, book: object
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--db", str(book), "book", "load", "kraken", "BTC-USD", "--stdin"],
        input="bid:99\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 2


def test_the_imbalance_command_prints_both_measures(loaded: Run) -> None:
    output = loaded("book", "imbalance", "kraken", "BTC-USD").output
    assert "touch" in output
    assert "depth" in output


def test_the_imbalance_command_says_which_way_the_book_leans(loaded: Run) -> None:
    output = loaded("book", "imbalance", "kraken", "BTC-USD", "--depth-bps", "500").output
    assert "leans   bid" in output or "leans   ask" in output


def test_the_imbalance_command_reports_how_far_apart_the_measures_are(loaded: Run) -> None:
    assert "apart" in loaded("book", "imbalance", "kraken", "BTC-USD").output


def test_the_imbalance_command_needs_a_book_on_file(seeded: Run) -> None:
    seeded("book", "imbalance", "kraken", "BTC-USD", expect=1)


def test_a_one_sided_book_has_no_imbalance_to_print(seeded: Run) -> None:
    seeded("book", "load", "kraken", "BTC-USD", "--bid", "99:1")
    result = seeded("book", "imbalance", "kraken", "BTC-USD", expect=1)
    assert "BOOK.02" in result.output


def test_the_confidence_command_reports_the_age_and_the_budget(seeded: Run) -> None:
    seeded("book", "load", "kraken", "BTC-USD", "--bid", "99:1", "--ask", "100:1")
    output = seeded("book", "confidence", "kraken", "BTC-USD").output
    assert "age" in output
    assert "budget   750 ms" in output


def test_a_book_loaded_just_now_is_still_nearly_believed_in_full(seeded: Run) -> None:
    # The load and the read are two invocations on a real clock, so time passes
    # between them. Against kraken's 750 ms budget that was 4% of the slope on
    # an idle machine and 18% on a loaded one, which made this test a coin toss
    # rather than a measurement. The venue it asks about has an hour instead,
    # so the gap has to be minutes before the number moves.
    seeded(
        "venue",
        "add",
        "patient",
        "Patient",
        "--staleness-ms",
        "3600000",
        "--depth-bps",
        "35",
        "--cap",
        "250000",
    )
    seeded("book", "load", "patient", "BTC-USD", "--bid", "99:1", "--ask", "100:1")
    output = seeded("book", "confidence", "patient", "BTC-USD").output
    believe = next(row for row in output.splitlines() if row.startswith("believe"))
    assert float(believe.split()[1]) > 0.99
    assert "state    spent" not in output


def test_an_old_book_reads_as_spent(seeded: Run) -> None:
    seeded(
        "book",
        "load",
        "kraken",
        "BTC-USD",
        "--bid",
        "99:1",
        "--ask",
        "100:1",
        "--observed-at",
        "2020-01-01T00:00:00+00:00",
    )
    assert "state    spent" in seeded("book", "confidence", "kraken", "BTC-USD").output


def test_the_confidence_command_needs_a_book_on_file(seeded: Run) -> None:
    seeded("book", "confidence", "kraken", "BTC-USD", expect=1)
