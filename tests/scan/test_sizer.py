"""Four constraints, and which one binds."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.errors import BadArgument, Refused
from legvise.model.book import Book, Side
from legvise.model.instrument import Instrument
from legvise.model.inventory import Band, Position
from legvise.money import dec
from legvise.risk.caps import CapSet
from legvise.scan.sizer import size_leg

AT = dt.datetime(2025, 7, 1, 10, 0, tzinfo=dt.UTC)
AS_OF = "2025-07-01T10:00:00+00:00"

BOOK = Book.build(
    "kraken",
    "BTC-USD",
    observed_at=AT,
    bids=(("99.00", "10"), ("98.00", "50")),
    asks=(("100.00", "10"), ("101.00", "50")),
)
MARKET = Instrument.build(
    "kraken",
    "BTC-USD",
    tick_size="0.01",
    lot_step="0.0001",
    min_notional="10",
    max_notional="10000000",
)


def caps(**changes: object) -> CapSet:
    fields: dict[str, object] = {
        "venue_cap": dec("10000000"),
        "venue_used": dec("0"),
        "asset_cap": dec("10000000"),
        "asset_used": dec("0"),
        "gross_cap": dec("100000000"),
        "gross_used": dec("0"),
    }
    fields.update(changes)
    return CapSet(**fields)  # type: ignore[arg-type]


def size(**changes: object) -> object:
    fields: dict[str, object] = {
        "side": Side.ASK,
        "depth_limit_bps": dec("500"),
        "spending": Position.build("kraken", "USD", free="1000000", as_of=AS_OF),
        "spending_band": Band.build("kraken", "USD", floor="0", target="500000", ceiling="2000000"),
        "receiving": Position.build("kraken", "BTC", free="0", as_of=AS_OF),
        "receiving_band": Band.build("kraken", "BTC", floor="0", target="50", ceiling="1000"),
        "caps": caps(),
        "wanted": dec("5"),
    }
    fields.update(changes)
    return size_leg(BOOK, MARKET, **fields)  # type: ignore[arg-type]


def test_a_leg_inside_every_limit_gets_what_it_asked_for() -> None:
    sized = size()
    assert sized.size == dec("5")  # type: ignore[attr-defined]
    assert sized.bound_by == "wanted"  # type: ignore[attr-defined]


def test_the_priced_notional_comes_from_the_sweep() -> None:
    assert size().notional == dec("500.00")  # type: ignore[attr-defined]


def test_depth_binds_when_the_reachable_book_is_thinner_than_the_ask() -> None:
    sized = size(depth_limit_bps=dec("50"), wanted=dec("40"))
    assert sized.size == dec("10")  # type: ignore[attr-defined]
    assert sized.bound_by == "depth"  # type: ignore[attr-defined]


def test_the_floor_binds_when_the_quote_balance_runs_out() -> None:
    sized = size(
        spending=Position.build("kraken", "USD", free="300", as_of=AS_OF),
        spending_band=Band.build("kraken", "USD", floor="100", target="500", ceiling="2000"),
        wanted=dec("5"),
    )
    assert sized.bound_by == "floor"  # type: ignore[attr-defined]
    assert sized.size == dec("2")  # type: ignore[attr-defined]


def test_the_ceiling_binds_when_the_base_balance_is_nearly_full() -> None:
    sized = size(
        receiving=Position.build("kraken", "BTC", free="998", as_of=AS_OF),
        wanted=dec("5"),
    )
    assert sized.bound_by == "ceiling"  # type: ignore[attr-defined]
    assert sized.size == dec("2")  # type: ignore[attr-defined]


def test_a_cap_trims_the_size_after_the_book_has_priced_it() -> None:
    sized = size(caps=caps(venue_cap=dec("300"), venue_used=dec("0")), wanted=dec("5"))
    assert sized.bound_by == "CAP.01"  # type: ignore[attr-defined]
    assert sized.size == dec("3")  # type: ignore[attr-defined]


def test_the_asset_cap_trims_when_it_is_tighter() -> None:
    sized = size(
        caps=caps(venue_cap=dec("400"), asset_cap=dec("200")),
        wanted=dec("5"),
    )
    assert sized.bound_by == "CAP.02"  # type: ignore[attr-defined]


def test_the_gross_cap_stops_rather_than_trimming() -> None:
    with pytest.raises(Refused) as caught:
        size(caps=caps(gross_cap=dec("100"), gross_used=dec("99")), wanted=dec("5"))
    assert caught.value.why.startswith("CAP.03")


def test_the_result_is_rounded_onto_the_lot_grid() -> None:
    sized = size(caps=caps(venue_cap=dec("333.333"), venue_used=dec("0")), wanted=dec("5"))
    assert sized.size % dec("0.0001") == dec("0")  # type: ignore[attr-defined]


def test_a_leg_that_rounds_below_the_venue_minimum_is_refused() -> None:
    with pytest.raises(Refused) as caught:
        size(caps=caps(venue_cap=dec("5"), venue_used=dec("0")), wanted=dec("5"))
    assert caught.value.why.startswith("TICK.03")


def test_selling_reads_the_bid_side_and_spends_the_base() -> None:
    sized = size(
        side=Side.BID,
        spending=Position.build("kraken", "BTC", free="3", as_of=AS_OF),
        spending_band=Band.build("kraken", "BTC", floor="0", target="50", ceiling="1000"),
        receiving=Position.build("kraken", "USD", free="0", as_of=AS_OF),
        receiving_band=Band.build("kraken", "USD", floor="0", target="500000", ceiling="2000000"),
        wanted=dec("5"),
    )
    assert sized.size == dec("3")  # type: ignore[attr-defined]
    assert sized.bound_by == "floor"  # type: ignore[attr-defined]


def test_every_limit_is_reported_even_when_it_did_not_bind() -> None:
    names = {limit.name for limit in size().limits}  # type: ignore[attr-defined]
    assert names == {"wanted", "depth", "floor", "ceiling"}


def test_sizing_nothing_is_refused() -> None:
    with pytest.raises(BadArgument):
        size(wanted=dec("0"))


def test_a_book_with_nothing_reachable_is_refused() -> None:
    empty = Book.build("kraken", "BTC-USD", observed_at=AT, bids=(("99", "1"),))
    with pytest.raises(Refused) as caught:
        size_leg(
            empty,
            MARKET,
            side=Side.ASK,
            depth_limit_bps=dec("500"),
            spending=Position.build("kraken", "USD", free="1000000", as_of=AS_OF),
            spending_band=Band.build(
                "kraken", "USD", floor="0", target="500000", ceiling="2000000"
            ),
            receiving=Position.build("kraken", "BTC", free="0", as_of=AS_OF),
            receiving_band=Band.build("kraken", "BTC", floor="0", target="50", ceiling="1000"),
            caps=caps(),
            wanted=dec("1"),
        )
    assert caught.value.why.startswith("DEPTH.01")


def test_a_position_already_under_its_floor_sizes_to_nothing() -> None:
    with pytest.raises(Refused) as caught:
        size(
            spending=Position.build("kraken", "USD", free="50", as_of=AS_OF),
            spending_band=Band.build("kraken", "USD", floor="100", target="500", ceiling="2000"),
        )
    assert caught.value.why.startswith("BAND.01")
