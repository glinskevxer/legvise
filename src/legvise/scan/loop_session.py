"""Running the triangular pass over every venue.

Separate from the cross-venue scanner because the two answer different
questions and are worth running at different rates. A cross-venue scan is
bounded by the pairing window and wants to run as often as the feed allows; the
loop pass is bounded by nothing but the venue's own book, so it can run on a
slower clock and search deeper.

What they share is the reference data, and that is loaded through the same
lookups here rather than through a common base class. There is not enough in
common to be worth the indirection, and a shared `_load` that both passes bend
out of shape is how a scanner becomes unreadable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.clock import Clock, to_text
from legvise.errors import LegviseError, Refused
from legvise.fees.ladder import resolve
from legvise.fees.quote import FeeContext
from legvise.ids import Symbol, plan_ref, session_ref
from legvise.model.book import Book
from legvise.model.cycle import Cycle
from legvise.model.plan import Plan
from legvise.money import ZERO
from legvise.scan.loop import as_plan, price_cycle
from legvise.scan.triangular import profitable_cycles
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.fees import FeeStore
from legvise.store.instruments import InstrumentStore
from legvise.store.plans import PlanStore
from legvise.store.venues import VenueStore

__all__ = ["LoopReport", "LoopScanner"]


@dataclass(frozen=True, slots=True)
class LoopReport:
    """What one triangular pass did."""

    session: str
    venues_searched: int
    cycles_screened: int
    plans_written: int
    refusals: dict[str, int]
    skipped: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LoopScanner:
    """The triangular pass, wired to a database and a clock."""

    db: Database
    clock: Clock
    start_asset: str
    start_amount: Decimal
    min_edge_bps: Decimal
    screen_bps: Decimal = ZERO
    max_length: int = 3

    def run(self, *, counter: int = 0) -> LoopReport:
        """Search every venue for loops and record what came back."""
        now = self.clock.now()
        ref = session_ref(to_text(now), counter)
        plans = PlanStore(self.db)
        with self.db.tx():
            plans.open_session(
                ref,
                started_at=to_text(now),
                min_edge_bps=self.min_edge_bps,
                pairing_window_ms=0,
                wanted_size=self.start_amount,
            )
        skipped: list[str] = []
        screened = 0
        written = 0
        searched = 0
        for code in VenueStore(self.db).codes():
            books = self._books_on(code)
            if len(books) < 3:
                continue
            searched += 1
            fees = self._fees_for(code, skipped)
            if fees is None:
                continue
            cycles = profitable_cycles(
                code,
                tuple(books.values()),
                start=self.start_asset,
                min_bps=self.screen_bps,
                max_length=self.max_length,
            )
            screened += len(cycles)
            for cycle in cycles:
                plan = self._price(cycle, books, fees, plan_ref(ref, written))
                if plan is None:
                    continue
                with self.db.tx():
                    plans.add(plan, session_ref=ref)
                written += 1
        return LoopReport(
            session=ref,
            venues_searched=searched,
            cycles_screened=screened,
            plans_written=written,
            refusals=plans.refusal_counts(ref),
            skipped=tuple(sorted(set(skipped))),
        )

    def _books_on(self, venue: str) -> dict[Symbol, Book]:
        instruments = InstrumentStore(self.db)
        books = BookStore(self.db)
        out: dict[Symbol, Book] = {}
        for symbol in instruments.symbols_on(venue):
            found = books.latest(venue, symbol)
            if found is not None and found.is_two_sided():
                out[symbol] = found
        return out

    def _fees_for(self, venue: str, skipped: list[str]) -> FeeContext | None:
        store = FeeStore(self.db)
        try:
            tier = resolve(store.ladder(venue), store.volume(venue))
        except LegviseError as gap:
            skipped.append(f"{venue} {gap.message}")
            return None
        record = VenueStore(self.db).get(venue)
        return FeeContext(
            venue=venue,
            tier=tier,
            pays_maker_rebate=record.pays_maker_rebate,
        )

    def _price(
        self, cycle: Cycle, books: dict[Symbol, Book], fees: FeeContext, ref: str
    ) -> Plan | None:
        """Price one loop, or nothing when a clause turns it down.

        A refused loop is dropped rather than written. Unlike a cross-venue
        pair, which is one plan per ordered venue pair and therefore a fixed
        number, the loop search produces a combinatorial number of candidates,
        and writing every refusal would bury the interesting rows.
        """
        try:
            quote = price_cycle(cycle, books, fees, start_amount=self.start_amount)
            return as_plan(quote, ref=ref, min_edge_bps=self.min_edge_bps)
        except Refused:
            return None
