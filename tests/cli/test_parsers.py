"""Reading the colon separated options the command tree takes."""

from __future__ import annotations

import click
import pytest

from legvise.cli.parsers import (
    decimal_map,
    pair_map,
    split_on_colons,
    triple,
    triple_map,
    venue_map,
)
from legvise.ids import asset_code
from legvise.money import dec


def test_a_two_part_value_splits_into_two() -> None:
    assert split_on_colons("BTC:100", "ASSET:PRICE") == ("BTC", "100")


def test_a_three_part_value_splits_into_three() -> None:
    assert split_on_colons("kraken:BTC:5", "VENUE:ASSET:AMOUNT") == ("kraken", "BTC", "5")


def test_the_surrounding_space_is_trimmed() -> None:
    assert split_on_colons(" BTC : 100 ", "ASSET:PRICE") == ("BTC", "100")


def test_a_value_with_too_few_parts_quotes_the_shape() -> None:
    with pytest.raises(click.BadParameter) as caught:
        split_on_colons("BTC", "ASSET:PRICE")
    assert "ASSET:PRICE" in str(caught.value)


def test_a_value_with_too_many_parts_is_refused() -> None:
    with pytest.raises(click.BadParameter):
        split_on_colons("BTC:100:5", "ASSET:PRICE")


def test_an_empty_part_is_refused() -> None:
    with pytest.raises(click.BadParameter):
        split_on_colons("BTC:", "ASSET:PRICE")


def test_a_three_part_value_comes_back_typed_as_three() -> None:
    left, middle, right = triple("0:10:16", "VOLUME:MAKER:TAKER")
    assert (left, middle, right) == ("0", "10", "16")


def test_a_map_reads_every_entry() -> None:
    found = pair_map(("BTC:100000", "USD:1"), shape="ASSET:PRICE", field="mark")
    assert found == {"BTC": dec("100000"), "USD": dec("1")}


def test_a_map_normalises_the_key() -> None:
    found = pair_map(("btc:100000",), shape="ASSET:PRICE", field="mark")
    assert "BTC" in found


def test_a_venue_map_normalises_the_venue_code() -> None:
    found = venue_map((" Kraken :0.5",), shape="VENUE:WEIGHT", field="weight")
    assert found == {"kraken": dec("0.5")}


def test_a_key_that_is_not_a_code_is_a_usage_error() -> None:
    with pytest.raises(click.BadParameter):
        pair_map(("B:1",), shape="ASSET:PRICE", field="mark")


def test_an_amount_that_is_not_a_number_is_a_usage_error() -> None:
    with pytest.raises(click.BadParameter) as caught:
        pair_map(("BTC:lots",), shape="ASSET:PRICE", field="mark")
    assert "not a decimal literal" in str(caught.value)


def test_a_later_entry_wins_over_an_earlier_one() -> None:
    found = pair_map(("BTC:1", "BTC:2"), shape="ASSET:PRICE", field="mark")
    assert found == {"BTC": dec("2")}


def test_no_entries_read_into_an_empty_map() -> None:
    assert pair_map((), shape="ASSET:PRICE", field="mark") == {}


def test_a_triple_map_keys_on_both_codes() -> None:
    found = triple_map(("kraken:btc:5",), shape="VENUE:ASSET:AMOUNT", field="amount")
    assert found == {("kraken", "BTC"): dec("5")}


def test_a_triple_map_refuses_a_two_part_entry() -> None:
    with pytest.raises(click.BadParameter):
        triple_map(("kraken:BTC",), shape="VENUE:ASSET:AMOUNT", field="amount")


def test_a_custom_key_function_is_used() -> None:
    found = decimal_map(("btc:1",), shape="ASSET:AMOUNT", key=asset_code, field="amount")
    assert found == {"BTC": dec("1")}
