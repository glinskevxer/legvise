"""Decimal handling, the rounding directions and basis point arithmetic."""

from __future__ import annotations

from decimal import Decimal

import pytest

from legvise.errors import BadArgument
from legvise.money import (
    apply_bps,
    bps_between,
    dec,
    is_zero,
    quantize_down,
    quantize_nearest,
    quantize_up,
    step_multiple,
)


def test_a_string_literal_survives_intact() -> None:
    assert dec("0.1") == Decimal("0.1")
    assert str(dec("1.00000000")) == "1.00000000"


def test_an_int_becomes_an_exact_decimal() -> None:
    assert dec(7) == Decimal("7")


def test_a_decimal_passes_straight_through() -> None:
    given = Decimal("3.5")
    assert dec(given) is given


def test_a_float_is_refused_rather_than_silently_rounded() -> None:
    with pytest.raises(BadArgument) as caught:
        dec(0.1)  # type: ignore[arg-type]
    assert "str, int or Decimal" in caught.value.why


def test_a_bool_is_not_a_quantity() -> None:
    with pytest.raises(BadArgument):
        dec(True)


@pytest.mark.parametrize("text", ["", "abc", "1.2.3", "--4"])
def test_text_that_is_not_a_number_is_refused(text: str) -> None:
    with pytest.raises(BadArgument):
        dec(text)


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_literals_are_refused(text: str) -> None:
    with pytest.raises(BadArgument) as caught:
        dec(text)
    assert caught.value.why == "must be finite"


def test_zero_is_zero_however_it_is_written() -> None:
    assert is_zero(dec("0.000"))
    assert not is_zero(dec("0.0001"))


def test_rounding_down_never_exceeds_the_value() -> None:
    assert quantize_down(dec("0.123456"), dec("0.0001")) == dec("0.1234")
    assert quantize_down(dec("-0.12345"), dec("0.001")) == dec("-0.124")


def test_rounding_up_never_falls_short_of_the_value() -> None:
    assert quantize_up(dec("0.123456"), dec("0.0001")) == dec("0.1235")
    assert quantize_up(dec("2"), dec("0.5")) == dec("2")


def test_rounding_to_nearest_breaks_ties_toward_the_even_multiple() -> None:
    assert quantize_nearest(dec("0.25"), dec("0.5")) == dec("0.0")
    assert quantize_nearest(dec("0.75"), dec("0.5")) == dec("1.0")


@pytest.mark.parametrize("fn", [quantize_down, quantize_up, quantize_nearest])
def test_a_step_of_zero_is_refused_by_every_rounder(fn: object) -> None:
    with pytest.raises(BadArgument):
        fn(dec("1"), dec("0"))  # type: ignore[operator]


def test_step_multiple_answers_whether_a_value_is_on_the_grid() -> None:
    assert step_multiple(dec("0.5"), dec("0.1"))
    assert not step_multiple(dec("0.55"), dec("0.1"))


def test_basis_points_are_a_ten_thousandth_each() -> None:
    assert apply_bps(dec("10000"), dec("1")) == dec("1")
    assert apply_bps(dec("250"), dec("8")) == dec("0.2")


def test_the_spread_between_two_prices_reads_in_basis_points() -> None:
    assert bps_between(dec("100"), dec("101")) == dec("100")
    assert bps_between(dec("100"), dec("99")) == dec("-100")


def test_a_spread_off_a_zero_base_is_refused() -> None:
    with pytest.raises(BadArgument):
        bps_between(dec("0"), dec("1"))
