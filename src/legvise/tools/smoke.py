"""One whole day of the desk, start to finish, against a throwaway database.

The unit tests each prove one thing. This proves the thing they cannot: that a
desk set up from nothing, given books, scanned, filled and reported on, produces
numbers that hang together. It is the test that would have caught a repository
returning the right rows in the wrong order, or a scanner writing plans nobody
can read back.

It builds its own database in memory and asserts on the result, so it can run
anywhere and leaves nothing behind. CI runs it after the suite; a developer runs
it when something feels wrong and the tests all pass.
"""

from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal

from legvise.clock import FixedClock
from legvise.errors import LegviseError
from legvise.ledger.attribution import attribute
from legvise.model.book import Book
from legvise.model.fee import FeeLadder
from legvise.model.fill import Fill
from legvise.model.instrument import Instrument
from legvise.model.inventory import Band, Position
from legvise.model.network import TransferNetwork, VenueNetwork
from legvise.model.venue import Venue
from legvise.money import dec
from legvise.report.edge_report import build_edge_report
from legvise.report.session_report import summarise
from legvise.risk.caps import CapSet
from legvise.routing.pricer import StoreRebalancePricer
from legvise.routing.rebalance import CarryTerms
from legvise.scan.direct import ScanTerms
from legvise.scan.session import Scanner
from legvise.store.books import BookStore
from legvise.store.db import Database
from legvise.store.fees import FeeStore
from legvise.store.fills import FillStore
from legvise.store.instruments import InstrumentStore
from legvise.store.inventory import InventoryStore
from legvise.store.networks import NetworkStore
from legvise.store.plans import PlanStore
from legvise.store.schema import install
from legvise.store.venues import VenueStore

__all__ = ["main", "run"]

AT = dt.datetime(2026, 2, 3, 9, 0, tzinfo=dt.UTC)
AS_OF = AT.isoformat()
VENUES = ("kraken", "okx")


def _seed(db: Database) -> None:
    venues = VenueStore(db)
    instruments = InstrumentStore(db)
    fees = FeeStore(db)
    inventory = InventoryStore(db)
    networks = NetworkStore(db)
    networks.put_network(
        TransferNetwork.build(
            "BTC",
            "BTC-MAIN",
            withdraw_fee="0.0002",
            min_withdraw="0.001",
            confirmations=3,
            minutes_per_confirmation="10",
        )
    )
    for code in VENUES:
        venues.add(
            Venue.build(
                code,
                code.title(),
                staleness_budget_ms=60000,
                depth_limit_bps="500",
                notional_cap="10000000",
            )
        )
        instruments.add(
            Instrument.build(
                code,
                "BTC-USD",
                tick_size="0.01",
                lot_step="0.0001",
                min_notional="10",
                max_notional="10000000",
            )
        )
        fees.put_ladder(FeeLadder.build(code, (("0", "0", "5"),)))
        fees.record_volume(code, dec("0"), as_of=AS_OF)
        networks.put_support(VenueNetwork.build(code, "BTC", "BTC-MAIN"))
        for asset, free, ceiling in (("BTC", "50", "1000"), ("USD", "5000000", "50000000")):
            inventory.put_position(Position.build(code, asset, free=free, as_of=AS_OF))
            inventory.put_band(Band.build(code, asset, floor="0", target="25", ceiling=ceiling))


def _load_books(db: Database) -> None:
    books = BookStore(db)
    books.add(
        Book.build(
            "kraken",
            "BTC-USD",
            observed_at=AT,
            bids=(("99.00", "40"), ("98.50", "100")),
            asks=(("100.00", "40"), ("100.50", "100")),
        )
    )
    books.add(
        Book.build(
            "okx",
            "BTC-USD",
            observed_at=AT,
            bids=(("101.00", "40"), ("100.50", "100")),
            asks=(("102.00", "40"), ("102.50", "100")),
        )
    )


def _scanner(db: Database) -> Scanner:
    return Scanner(
        db=db,
        clock=FixedClock(AT),
        terms=ScanTerms(min_edge_bps=dec("2"), pairing_window_ms=1000, wanted_size=dec("2")),
        caps=CapSet(
            venue_cap=dec("10000000"),
            venue_used=dec("0"),
            asset_cap=dec("10000000"),
            asset_used=dec("0"),
            gross_cap=dec("100000000"),
            gross_used=dec("0"),
        ),
        pricer=StoreRebalancePricer(
            networks=NetworkStore(db),
            terms=CarryTerms(carry_bps_per_hour=dec("6"), cycles_served=10),
            stranded_bps=dec("250"),
        ),
    )


def run(*, quiet: bool = False) -> dict[str, Decimal | int | str]:
    """Set a desk up, scan it, fill a plan and report. Return what happened."""
    db = Database.in_memory()
    try:
        install(db, applied_at=AS_OF)
        _seed(db)
        _load_books(db)
        report = _scanner(db).run()
        if report.pairs_priced != 1:
            raise AssertionError(f"expected one priced pair, got {report.pairs_priced}")
        if report.actionable != 1:
            raise AssertionError(f"expected one actionable plan, got {report.actionable}")

        plans = PlanStore(db)
        plan = plans.actionable(report.session)[0]
        if not plan.arithmetic_holds():
            raise AssertionError(f"{plan.ref} does not add up")

        fills = FillStore(db)
        for index, leg in enumerate(plan.legs):
            fills.add(
                Fill(
                    plan_ref=plan.ref,
                    leg_index=index,
                    venue=leg.venue,
                    takes=leg.takes,
                    price=leg.price,
                    size=leg.size,
                    fee_amount=leg.fee_amount,
                    filled_at=AS_OF,
                ),
                venue_trade_id=f"smoke-{index}",
            )

        found = attribute(plan, fills.results_for(plan))
        if found.has_leg_risk:
            raise AssertionError(f"{plan.ref} came back one sided")
        if found.gap_bps != Decimal(0):
            raise AssertionError(f"{plan.ref} drifted by {found.gap_bps} against a clean fill")

        summary = summarise(plans, report.session)
        edge = build_edge_report(plans, fills, session_ref=report.session)
        outcome: dict[str, Decimal | int | str] = {
            "session": report.session,
            "plans": summary.plans,
            "actionable": summary.actionable,
            "net_bps": plan.net_bps,
            "realised_bps": edge.realised_bps,
            "notional": plan.notional,
        }
        if not quiet:
            for key, value in outcome.items():
                print(f"smoke: {key:<12} {value}")
        return outcome
    finally:
        db.close()


def main(argv: tuple[str, ...] = ()) -> int:
    """Run the whole thing and report."""
    args = argv or tuple(sys.argv[1:])
    try:
        run(quiet="--quiet" in args)
    except (AssertionError, LegviseError) as failure:
        print(f"smoke: FAILED {failure}")
        return 1
    print("smoke: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
