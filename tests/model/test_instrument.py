"""What an instrument record refuses to be built as."""

from __future__ import annotations

from decimal import Decimal

import pytest

from legvise.errors import BadArgument
from legvise.ids import Symbol
from legvise.model.instrument import Instrument


def an_instrument(**changes: object) -> Instrument:
    fields: dict[str, object] = {
        "venue": "kraken",
        "symbol": "BTC-USD",
        "tick_size": "0.1",
        "lot_step": "0.00001",
        "min_notional": "10",
        "max_notional": "500000",
    }
    fields.update(changes)
    return Instrument.build(**fields)  # type: ignore[arg-type]


def test_an_instrument_splits_its_symbol_into_sides() -> None:
    made = an_instrument()
    assert made.symbol == Symbol("BTC", "USD")
    assert made.base == "BTC"
    assert made.quote == "USD"


def test_the_store_key_is_the_venue_and_the_canonical_symbol() -> None:
    assert an_instrument().key == ("kraken", "BTC-USD")


def test_the_venue_spelling_defaults_to_the_desks_own() -> None:
    assert an_instrument().venue_symbol == "BTC-USD"


def test_a_venue_that_spells_it_differently_says_so() -> None:
    made = an_instrument(venue_symbol="XBTUSD")
    assert made.venue_symbol == "XBTUSD"
    assert str(made.symbol) == "BTC-USD"


def test_an_empty_venue_spelling_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        an_instrument(venue_symbol="   ")
    assert caught.value.field == "venue_symbol"


def test_filters_arrive_as_decimals() -> None:
    made = an_instrument()
    assert made.tick_size == Decimal("0.1")
    assert made.lot_step == Decimal("0.00001")


@pytest.mark.parametrize("field", ["tick_size", "lot_step", "min_notional"])
def test_a_filter_of_zero_is_refused(field: str) -> None:
    with pytest.raises(BadArgument) as caught:
        an_instrument(**{field: "0"})
    assert caught.value.field == field


@pytest.mark.parametrize("field", ["tick_size", "lot_step", "min_notional"])
def test_a_negative_filter_is_refused(field: str) -> None:
    with pytest.raises(BadArgument):
        an_instrument(**{field: "-1"})


def test_the_maximum_notional_has_to_sit_above_the_minimum() -> None:
    with pytest.raises(BadArgument) as caught:
        an_instrument(min_notional="100", max_notional="100")
    assert caught.value.field == "max_notional"


def test_an_instrument_is_immutable() -> None:
    made = an_instrument()
    with pytest.raises(AttributeError):
        made.tick_size = Decimal("1")  # type: ignore[misc]


def test_an_instrument_is_active_unless_told_otherwise() -> None:
    assert an_instrument().active is True
    assert an_instrument(active=False).active is False


def test_a_venue_code_is_normalised_on_the_way_in() -> None:
    assert an_instrument(venue=" Kraken ").venue == "kraken"


def test_a_symbol_the_venue_spells_without_a_separator_is_refused_as_the_desk_symbol() -> None:
    with pytest.raises(BadArgument):
        an_instrument(symbol="BTCUSD")


def test_two_instruments_with_the_same_fields_compare_equal() -> None:
    assert an_instrument() == an_instrument()
