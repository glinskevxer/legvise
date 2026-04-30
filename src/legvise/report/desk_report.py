"""One page that says whether the desk is ready to scan.

An operator arriving at a terminal wants one question answered: is anything
missing. Not "list the venues" and then "list the markets" and then "check the
fee ladders" — one command, and a list of what is not set up.

So this walks the reference data the scanner needs and reports the gaps. It is
the same walk `scan.session` does when it decides to skip a venue, except it
runs without a book and says so out loud instead of quietly scanning four venues
when five were configured.
"""

from __future__ import annotations

from dataclasses import dataclass

from legvise.fees.ladder import resolve
from legvise.ids import Symbol
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.fees import FeeStore
from legvise.store.instruments import InstrumentStore
from legvise.store.inventory import InventoryStore
from legvise.store.plans import PlanStore
from legvise.store.venues import VenueStore

__all__ = ["DeskStatus", "VenueStatus", "build_desk_status"]


@dataclass(frozen=True, slots=True)
class VenueStatus:
    """One venue and what it is missing."""

    code: str
    active: bool
    markets: int
    books: int
    gaps: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        """True when the scanner could use this venue right now."""
        return self.active and self.markets > 0 and not self.gaps


@dataclass(frozen=True, slots=True)
class DeskStatus:
    """Every venue, the shared markets, and the last session."""

    venues: tuple[VenueStatus, ...]
    shared_symbols: tuple[Symbol, ...]
    last_session: str | None
    sessions: int

    @property
    def ready_venues(self) -> tuple[VenueStatus, ...]:
        """The venues a scan could use."""
        return tuple(venue for venue in self.venues if venue.is_ready)

    @property
    def can_scan(self) -> bool:
        """True when two venues are ready and they share a market."""
        return len(self.ready_venues) >= 2 and bool(self.shared_symbols)

    @property
    def gaps(self) -> tuple[str, ...]:
        """Everything missing, one line each, in venue order."""
        return tuple(f"{venue.code}: {gap}" for venue in self.venues for gap in venue.gaps)


def _venue_gaps(db: Database, code: str) -> tuple[str, ...]:
    fees = FeeStore(db)
    inventory = InventoryStore(db)
    instruments = InstrumentStore(db)
    found: list[str] = []
    ladder = fees.find_ladder(code)
    if ladder is None:
        found.append("no fee ladder")
    elif fees.volume(code) is None:
        found.append("no trailing volume")
    else:
        resolve(ladder, fees.volume(code))
    for listing in instruments.for_venue(code, active_only=True):
        for asset in (listing.base, listing.quote):
            if inventory.position(code, asset) is None:
                found.append(f"no balance for {asset}")
            if inventory.band(code, asset) is None:
                found.append(f"no band for {asset}")
    return tuple(dict.fromkeys(found))


def build_desk_status(db: Database) -> DeskStatus:
    """Walk the reference data and report what a scan would find missing."""
    venues = VenueStore(db)
    instruments = InstrumentStore(db)
    books = BookStore(db)
    plans = PlanStore(db)
    statuses: list[VenueStatus] = []
    for code in venues.codes():
        record = venues.get(code)
        listings = instruments.for_venue(code, active_only=True)
        with_books = sum(
            1 for listing in listings if books.latest(code, listing.symbol) is not None
        )
        statuses.append(
            VenueStatus(
                code=code,
                active=record.active,
                markets=len(listings),
                books=with_books,
                gaps=_venue_gaps(db, code) if record.active else ("switched off",),
            )
        )
    recent = plans.sessions(limit=1)
    return DeskStatus(
        venues=tuple(statuses),
        shared_symbols=instruments.shared_symbols(),
        last_session=recent[0].ref if recent else None,
        sessions=len(plans.sessions(limit=1000)),
    )
