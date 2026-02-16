"""The value a walk comes back with, on its own."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.market.sweep import Sweep, consume, empty_sweep
from legvise.model.book import Level, Side
from legvise.money import dec


def levels(*pairs: tuple[str, str]) -> tuple[Level, ...]:
    return tuple(Level.build(price, size) for price, size in pairs)


def test_an_empty_sweep_got_nothing_and_is_not_complete() -> None:
    found = empty_sweep(Side.ASK)
    assert found.is_empty
    assert not found.complete
    assert found.levels == 0


def test_an_empty_sweep_has_no_average_price() -> None:
    found = empty_sweep(Side.ASK)
    with pytest.raises(BadArgument) as caught:
        assert found.vwap
    assert "no average price" in caught.value.why


def test_an_empty_sweep_remembers_which_side_it_walked() -> None:
    assert empty_sweep(Side.BID).side is Side.BID


def test_consuming_less_than_one_level_pays_that_level() -> None:
    got = consume(levels(("100", "5")), Side.ASK, dec("2"))
    assert got.size == dec("2")
    assert got.notional == dec("200")
    assert got.vwap == dec("100")
    assert got.levels == 1
    assert got.complete


def test_consuming_across_levels_averages_them() -> None:
    got = consume(levels(("100", "1"), ("110", "1")), Side.ASK, dec("2"))
    assert got.vwap == dec("105")
    assert got.levels == 2
    assert got.worst_price == dec("110")


def test_consuming_more_than_there_is_comes_back_incomplete() -> None:
    got = consume(levels(("100", "1")), Side.ASK, dec("5"))
    assert not got.complete
    assert got.size == dec("1")


def test_consuming_nothing_from_nothing_is_empty() -> None:
    got = consume((), Side.ASK, dec("5"))
    assert got.is_empty
    assert not got.complete


def test_consuming_exactly_what_is_there_is_complete() -> None:
    got = consume(levels(("100", "2")), Side.ASK, dec("2"))
    assert got.complete
    assert got.levels == 1


def test_a_sweep_is_a_tuple_of_its_parts() -> None:
    got = consume(levels(("100", "2")), Side.BID, dec("1"))
    assert isinstance(got, Sweep)
    assert got.side is Side.BID


def test_the_worst_price_is_the_last_level_touched() -> None:
    got = consume(levels(("100", "1"), ("110", "1"), ("120", "1")), Side.ASK, dec("2"))
    assert got.worst_price == dec("110")
