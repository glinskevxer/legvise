"""Fills, and what a leg made of them."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.model.book import Side
from legvise.model.fill import Fill, LegOutcome, LegResult
from legvise.money import dec

REF = "S20250910.0001/P000"
AT = "2025-09-10T09:00:01+00:00"


def a_fill(price: str = "100", size: str = "1", fee: str = "0.1") -> Fill:
    return Fill.build(
        REF, 0, "kraken", Side.ASK, price=price, size=size, fee_amount=fee, filled_at=AT
    )


def a_result(*fills: Fill, expected_size: str = "2") -> LegResult:
    return LegResult(
        plan_ref=REF,
        leg_index=0,
        expected_price=dec("100"),
        expected_size=dec(expected_size),
        fills=fills,
    )


def test_a_fill_knows_its_notional() -> None:
    assert a_fill("100", "2").notional == dec("200")


def test_a_venue_code_is_normalised_on_the_way_in() -> None:
    fill = Fill.build(REF, 0, " Kraken ", Side.BID, price="100", size="1", filled_at=AT)
    assert fill.venue == "kraken"


def test_a_fill_of_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_fill(size="0")


def test_a_fill_at_no_price_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_fill(price="0")


def test_a_negative_fee_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_fill(fee="-1")
    assert caught.value.field == "fee_amount"


def test_a_negative_leg_index_is_refused() -> None:
    with pytest.raises(BadArgument):
        Fill.build(REF, -1, "kraken", Side.ASK, price="100", size="1", filled_at=AT)


def test_a_leg_with_no_fills_is_a_miss() -> None:
    result = a_result()
    assert result.outcome is LegOutcome.MISSED
    assert result.filled_size == dec("0")
    assert not result.outcome.traded


def test_a_leg_that_never_traded_has_no_realised_price() -> None:
    result = a_result()
    with pytest.raises(BadArgument):
        assert result.realised_price


def test_a_leg_filled_in_full_says_so() -> None:
    result = a_result(a_fill("100", "2"))
    assert result.outcome is LegOutcome.FILLED
    assert result.fill_ratio == dec("1")
    assert result.outcome.traded


def test_a_leg_filled_in_part_says_so() -> None:
    result = a_result(a_fill("100", "1"))
    assert result.outcome is LegOutcome.PARTIAL
    assert result.fill_ratio == dec("0.5")
    assert result.outcome.traded


def test_a_leg_overfilled_still_reads_as_filled() -> None:
    assert a_result(a_fill("100", "3")).outcome is LegOutcome.FILLED


def test_several_fills_on_a_leg_add_up() -> None:
    result = a_result(a_fill("100", "1"), a_fill("102", "1"))
    assert result.filled_size == dec("2")
    assert result.filled_notional == dec("202")


def test_the_realised_price_is_size_weighted() -> None:
    result = a_result(a_fill("100", "1"), a_fill("110", "3"), expected_size="4")
    assert result.realised_price == dec("107.5")


def test_fees_add_up_across_the_fills() -> None:
    result = a_result(a_fill("100", "1", "0.1"), a_fill("100", "1", "0.2"))
    assert result.fees_paid == dec("0.3")


def test_a_leg_that_wanted_nothing_has_no_fill_ratio() -> None:
    result = a_result(expected_size="0")
    with pytest.raises(BadArgument):
        assert result.fill_ratio


def test_a_cancelled_leg_did_not_trade() -> None:
    assert not LegOutcome.CANCELLED.traded
    assert not LegOutcome.MISSED.traded
