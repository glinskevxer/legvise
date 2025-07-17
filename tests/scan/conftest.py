"""Building the two venue views a cross-venue plan needs."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from legvise.fees.quote import FeeContext
from legvise.model.book import Book
from legvise.model.fee import FeeTier
from legvise.model.instrument import Instrument
from legvise.model.inventory import Band, Position
from legvise.model.venue import Venue
from legvise.money import dec
from legvise.risk.caps import CapSet
from legvise.scan.direct import ScanTerms, VenueView

AT = dt.datetime(2025, 7, 8, 9, 0, tzinfo=dt.UTC)
AS_OF = "2025-07-08T09:00:00+00:00"

WIDE_CAPS = CapSet(
    venue_cap=dec("10000000"),
    venue_used=dec("0"),
    asset_cap=dec("10000000"),
    asset_used=dec("0"),
    gross_cap=dec("100000000"),
    gross_used=dec("0"),
)


def a_venue(code: str, **changes: object) -> Venue:
    fields: dict[str, object] = {
        "display_name": code.title(),
        "staleness_budget_ms": 1000,
        "depth_limit_bps": "500",
        "notional_cap": "10000000",
    }
    fields.update(changes)
    return Venue.build(code, **fields)  # type: ignore[arg-type]


def a_market(code: str) -> Instrument:
    return Instrument.build(
        code,
        "BTC-USD",
        tick_size="0.01",
        lot_step="0.0001",
        min_notional="10",
        max_notional="10000000",
    )


def a_book(code: str, bid: str, ask: str, *, depth: str = "50", offset_ms: int = 0) -> Book:
    return Book.build(
        code,
        "BTC-USD",
        observed_at=AT + dt.timedelta(milliseconds=offset_ms),
        bids=((bid, depth),),
        asks=((ask, depth),),
    )


def a_view(
    code: str,
    bid: str,
    ask: str,
    *,
    taker_bps: str = "10",
    base_free: str = "50",
    quote_free: str = "5000000",
    base_ceiling: str = "1000",
    caps: CapSet | None = None,
    offset_ms: int = 0,
    depth: str = "50",
    venue: Venue | None = None,
) -> VenueView:
    """One venue, ready to price a leg on."""
    return VenueView(
        venue=venue or a_venue(code),
        instrument=a_market(code),
        book=a_book(code, bid, ask, depth=depth, offset_ms=offset_ms),
        fees=FeeContext(
            venue=code,
            tier=FeeTier.build("0", "0", taker_bps),
            pays_maker_rebate=False,
        ),
        base_position=Position.build(code, "BTC", free=base_free, as_of=AS_OF),
        base_band=Band.build(code, "BTC", floor="0", target="25", ceiling=base_ceiling),
        quote_position=Position.build(code, "USD", free=quote_free, as_of=AS_OF),
        quote_band=Band.build(code, "USD", floor="0", target="1000000", ceiling="50000000"),
        caps=caps or WIDE_CAPS,
    )


def terms(*, min_edge_bps: str = "1", pairing_window_ms: int = 250, wanted: str = "1") -> ScanTerms:
    """Scan settings with a loose default so a test can tighten one at a time."""
    return ScanTerms(
        min_edge_bps=dec(min_edge_bps),
        pairing_window_ms=pairing_window_ms,
        wanted_size=dec(wanted),
    )


def bps(value: str) -> Decimal:
    """A basis point figure, spelled exactly."""
    return dec(value)
