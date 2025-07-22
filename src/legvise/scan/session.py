"""Running a whole scan: load, pair, price, record.

The pricing functions know nothing about the store and the store knows nothing
about pricing. This module is the seam, and it is the only place in the package
that reads a clock, opens a transaction and calls a pricer in the same breath.

The order it works in is chosen to spend the least on the pairs that are going
nowhere:

1. take only the symbols listed on two or more venues at all
2. take only the venues that have a two sided book on file for that symbol
3. throw away any ordered pair whose touch does not cross, which is nearly all
   of them, before any depth walk happens
4. price what is left, and write down what happened to each one

Step three is the whole reason a scan finishes inside a pairing window.

A venue whose reference data is incomplete -- no fee ladder, no trailing volume,
no band on one side of the market -- is skipped rather than crashing the scan.
It is recorded as skipped, because silently scanning four venues when the
operator configured five is worse than either failing or being told.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import permutations

from legvise.clock import Clock, to_text
from legvise.errors import LegviseError, Refused
from legvise.fees.ladder import resolve
from legvise.fees.quote import FeeContext
from legvise.ids import Symbol, plan_ref, session_ref
from legvise.market.spread import raw_cross_bps
from legvise.model.book import Book, Side
from legvise.model.instrument import Instrument
from legvise.model.plan import Leg, Plan, PlanKind, PlanStatus
from legvise.model.venue import Venue
from legvise.money import ZERO
from legvise.risk.caps import CapSet
from legvise.scan.direct import RebalancePricer, ScanTerms, VenueView, price_cross_venue
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.fees import FeeStore
from legvise.store.instruments import InstrumentStore
from legvise.store.inventory import InventoryStore
from legvise.store.plans import PlanStore
from legvise.store.venues import VenueStore

__all__ = ["ScanReport", "Scanner"]


@dataclass(frozen=True, slots=True)
class ScanReport:
    """What one scan did."""

    session: str
    symbols_considered: int
    pairs_priced: int
    actionable: int
    refusals: dict[str, int]
    skipped: tuple[str, ...] = field(default_factory=tuple)

    @property
    def hit_rate(self) -> Decimal:
        """Share of priced pairs that turned into something sendable."""
        if self.pairs_priced == 0:
            return ZERO
        return Decimal(self.actionable) / Decimal(self.pairs_priced)


@dataclass(frozen=True, slots=True)
class Scanner:
    """Everything one scan needs, wired to a database and a clock."""

    db: Database
    clock: Clock
    terms: ScanTerms
    caps: CapSet
    pricer: RebalancePricer | None = None

    def run(self, *, counter: int = 0) -> ScanReport:
        """Scan every shared symbol once and record what happened."""
        now = self.clock.now()
        ref = session_ref(to_text(now), counter)
        plans = PlanStore(self.db)
        with self.db.tx():
            plans.open_session(
                ref,
                started_at=to_text(now),
                min_edge_bps=self.terms.min_edge_bps,
                pairing_window_ms=self.terms.pairing_window_ms,
                wanted_size=self.terms.wanted_size,
            )
        symbols = InstrumentStore(self.db).shared_symbols()
        skipped: list[str] = []
        written = 0
        for symbol in symbols:
            views = self._views_for(symbol, skipped)
            for plan in self._pairs(symbol, views, ref, now, start_index=written):
                with self.db.tx():
                    plans.add(plan, session_ref=ref)
                written += 1
        return ScanReport(
            session=ref,
            symbols_considered=len(symbols),
            pairs_priced=written,
            actionable=len(plans.actionable(ref)),
            refusals=plans.refusal_counts(ref),
            skipped=tuple(sorted(set(skipped))),
        )

    def _pairs(
        self,
        symbol: Symbol,
        views: list[VenueView],
        ref: str,
        now: dt.datetime,
        *,
        start_index: int,
    ) -> list[Plan]:
        out: list[Plan] = []
        index = start_index
        for buy, sell in permutations(views, 2):
            if raw_cross_bps(buy.book, sell.book) <= ZERO:
                continue
            out.append(self._price_one(buy, sell, plan_ref(ref, index), now, symbol))
            index += 1
        return out

    def _price_one(
        self, buy: VenueView, sell: VenueView, ref: str, now: dt.datetime, symbol: Symbol
    ) -> Plan:
        try:
            return price_cross_venue(buy, sell, self.terms, ref=ref, now=now, pricer=self.pricer)
        except Refused as refusal:
            return _refused(ref, symbol, refusal, buy, sell)

    def _views_for(self, symbol: Symbol, skipped: list[str]) -> list[VenueView]:
        venues = VenueStore(self.db)
        instruments = InstrumentStore(self.db)
        books = BookStore(self.db)
        out: list[VenueView] = []
        for listing in instruments.for_symbol(symbol):
            venue = venues.get(listing.venue)
            if not venue.active:
                continue
            book = books.latest(listing.venue, symbol)
            if book is None or not book.is_two_sided():
                skipped.append(f"{listing.venue}:{symbol} has no two sided book")
                continue
            try:
                out.append(self._build_view(venue, listing, book))
            except LegviseError as gap:
                skipped.append(f"{listing.venue}:{symbol} {gap.message}")
        return out

    def _build_view(self, venue: Venue, listing: Instrument, book: Book) -> VenueView:
        fees = FeeStore(self.db)
        inventory = InventoryStore(self.db)
        tier = resolve(fees.ladder(venue.code), fees.volume(venue.code))
        return VenueView(
            venue=venue,
            instrument=listing,
            book=book,
            fees=FeeContext(
                venue=venue.code,
                tier=tier,
                pays_maker_rebate=venue.pays_maker_rebate,
            ),
            base_position=inventory.require_position(venue.code, listing.base),
            base_band=inventory.require_band(venue.code, listing.base),
            quote_position=inventory.require_position(venue.code, listing.quote),
            quote_band=inventory.require_band(venue.code, listing.quote),
            caps=self.caps,
        )


def _stub_leg(view: VenueView, takes: Side) -> Leg:
    """The leg the desk would have sent, at the touch and one lot deep.

    A refused plan still records both sides so a reader can see which two venues
    were being compared. The size is nominal and the plan's status says so.
    """
    touch = view.book.touch(takes)
    return Leg(
        venue=view.venue.code,
        symbol=view.instrument.symbol,
        takes=takes,
        price=touch.price,
        size=view.instrument.lot_step,
        fee_bps=ZERO,
        fee_amount=ZERO,
        levels_swept=1,
        slippage_bps=ZERO,
    )


def _refused(ref: str, symbol: Symbol, refusal: Refused, buy: VenueView, sell: VenueView) -> Plan:
    """Turn a refusal into a plan record that names the clause."""
    clause = refusal.why.split(":", 1)[0]
    return Plan(
        ref=ref,
        kind=PlanKind.CROSS_VENUE,
        symbol=symbol,
        legs=(_stub_leg(buy, Side.ASK), _stub_leg(sell, Side.BID)),
        notional=buy.instrument.min_notional,
        gross_bps=ZERO,
        fee_bps=ZERO,
        slippage_bps=ZERO,
        rebalance_bps=ZERO,
        net_bps=ZERO,
        status=PlanStatus.REFUSED,
        clause=clause,
    )
