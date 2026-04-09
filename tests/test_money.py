"""Decimal handling, the rounding directions and basis point arithmetic."""

from __future__ import annotations

from decimal import Decimal

import pytest

from legvise.errors import BadArgument
from legvise.money import (
    BPS,
    ONE,
    apply_bps,
    bps_between,
    dec,
    is_zero,
    quantize_down,
    quantize_nearest,
    quantize_up,
    step_multiple,
    to_bps,
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


def test_a_whole_is_ten_thousand_basis_points() -> None:
    assert Decimal("10000") == BPS
    assert Decimal("1") == ONE


def test_a_part_of_a_whole_reads_in_basis_points() -> None:
    assert to_bps(dec("1"), dec("10000")) == dec("1")
    assert to_bps(dec("32"), dec("200")) == dec("1600")


def test_the_whole_of_a_whole_is_ten_thousand_basis_points() -> None:
    assert to_bps(dec("250"), dec("250")) == BPS


def test_a_share_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        to_bps(dec("1"), dec("0"))
    assert "positive base" in caught.value.why


def test_a_share_of_a_negative_base_is_refused() -> None:
    with pytest.raises(BadArgument):
        to_bps(dec("1"), dec("-5"))


def test_the_share_names_the_field_it_was_given() -> None:
    with pytest.raises(BadArgument) as caught:
        to_bps(dec("1"), dec("0"), field="notional")
    assert caught.value.field == "notional"


def test_applying_and_measuring_basis_points_are_inverses() -> None:
    whole = dec("12345.67")
    part = apply_bps(whole, dec("37"))
    assert to_bps(part, whole) == dec("37")


# Relationships that have to hold for every value, swept over a fixed sample.
#
# Not random. A property test whose inputs change between runs is one that
# passes on the machine that wrote it and fails on the machine that did not,
# with no way to reproduce it. These sweep a written down sample instead, which
# is a smaller net and a net that catches the same fish twice.

SAMPLE = (
    "0.00000001",
    "0.1",
    "0.5",
    "1",
    "1.00000001",
    "7.5",
    "99.999",
    "100",
    "1234.5678",
    "1000000",
)

STEPS = ("0.00000001", "0.001", "0.01", "0.1", "0.5", "1", "5")


@pytest.mark.parametrize("value", SAMPLE)
@pytest.mark.parametrize("step", STEPS)
def test_rounding_down_never_goes_above_the_value(value: str, step: str) -> None:
    assert quantize_down(dec(value), dec(step)) <= dec(value)


@pytest.mark.parametrize("value", SAMPLE)
@pytest.mark.parametrize("step", STEPS)
def test_rounding_up_never_goes_below_the_value(value: str, step: str) -> None:
    assert quantize_up(dec(value), dec(step)) >= dec(value)


@pytest.mark.parametrize("value", SAMPLE)
@pytest.mark.parametrize("step", STEPS)
def test_rounding_up_and_down_are_at_most_one_step_apart(value: str, step: str) -> None:
    low = quantize_down(dec(value), dec(step))
    high = quantize_up(dec(value), dec(step))
    assert high - low <= dec(step)


@pytest.mark.parametrize("value", SAMPLE)
@pytest.mark.parametrize("step", STEPS)
def test_every_rounded_value_lands_on_the_grid(value: str, step: str) -> None:
    for rounded in (
        quantize_down(dec(value), dec(step)),
        quantize_up(dec(value), dec(step)),
        quantize_nearest(dec(value), dec(step)),
    ):
        assert step_multiple(rounded, dec(step))


@pytest.mark.parametrize("value", SAMPLE)
@pytest.mark.parametrize("step", STEPS)
def test_rounding_to_nearest_sits_between_the_other_two(value: str, step: str) -> None:
    low = quantize_down(dec(value), dec(step))
    near = quantize_nearest(dec(value), dec(step))
    high = quantize_up(dec(value), dec(step))
    assert low <= near <= high


@pytest.mark.parametrize("value", SAMPLE)
@pytest.mark.parametrize("step", STEPS)
def test_a_value_already_on_the_grid_does_not_move(value: str, step: str) -> None:
    on_grid = quantize_down(dec(value), dec(step))
    assert quantize_down(on_grid, dec(step)) == on_grid
    assert quantize_up(on_grid, dec(step)) == on_grid


@pytest.mark.parametrize("value", SAMPLE)
@pytest.mark.parametrize("rate", ["1", "10", "16", "250", "10000"])
def test_applying_a_rate_and_measuring_it_back_agree(value: str, rate: str) -> None:
    whole = dec(value)
    assert to_bps(apply_bps(whole, dec(rate)), whole) == dec(rate)


@pytest.mark.parametrize("low", SAMPLE)
@pytest.mark.parametrize("rate", ["1", "50", "1000"])
def test_a_spread_measured_and_reapplied_returns_the_high_price(low: str, rate: str) -> None:
    base = dec(low)
    high = base + apply_bps(base, dec(rate))
    assert bps_between(base, high) == dec(rate)


@pytest.mark.parametrize("value", SAMPLE)
def test_a_spread_against_itself_is_nothing(value: str) -> None:
    assert bps_between(dec(value), dec(value)) == dec("0")


@pytest.mark.parametrize("value", SAMPLE)
def test_every_sample_survives_a_text_round_trip(value: str) -> None:
    assert dec(format(dec(value), "f")) == dec(value)
