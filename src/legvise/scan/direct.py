"""Pricing one cross-venue opportunity end to end.

This is where the rest of the package meets. Buy the base on one venue, sell it
on another, both against inventory already sitting there, and find out whether
what is left after every cost is worth sending.

The edge is decomposed the same way every time:

    net = gross - fees - slippage - rebalance

`gross` is touch to touch, which is the optimistic number. `slippage` is what
sweeping for the actual size costs against each touch. Keeping those two apart
is deliberate: a pair whose gross edge is fine and whose slippage eats it is a
sizing problem, and one whose gross edge was never there is a different problem,
and a single "realised spread" number cannot tell them apart.

Nothing here writes to the store or reads a clock of its own.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from legvise.fees.quote import FeeContext, charge_for
from legvise.market.depth import slippage_bps, walk
from legvise.market.spread import raw_cross_bps
from legvise.market.staleness import check_pairing, require_fresh
from legvise.market.sweep import Sweep
from legvise.model.book import Book, Side
from legvise.model.instrument import Instrument
from legvise.model.inventory import Band, Position
from legvise.model.leg import Leg
from legvise.model.plan import Plan, PlanKind, PlanStatus
from legvise.model.venue import Venue
from legvise.money import BPS, ZERO
from legvise.risk.bands import excess_above_ceiling
from legvise.risk.caps import CapSet
from legvise.rules import refuse
from legvise.scan.sizer import size_leg

__all__ = [
    "NoRebalanceCost",
    "RebalancePricer",
    "ScanTerms",
    "VenueView",
    "price_cross_venue",
]


class RebalancePricer(Protocol):
    """Whatever knows what it costs to put an asset back where it came from."""

    def charge_bps(
        self,
        *,
        asset: str,
        sender: str,
        receiver: str,
        excess: Decimal,
        unit_price: Decimal,
        notional: Decimal,
    ) -> Decimal:
        """Basis points to charge one plan for the transfer it will cause."""
        ...


class NoRebalanceCost:
    """A pricer for a desk that does not charge itself for transfers."""

    def charge_bps(
        self,
        *,
        asset: str,
        sender: str,
        receiver: str,
        excess: Decimal,
        unit_price: Decimal,
        notional: Decimal,
    ) -> Decimal:
        """Always nothing."""
        del asset, sender, receiver, excess, unit_price, notional
        return ZERO


@dataclass(frozen=True, slots=True)
class ScanTerms:
    """The desk's settings for one scan."""

    min_edge_bps: Decimal
    pairing_window_ms: int
    wanted_size: Decimal


@dataclass(frozen=True, slots=True)
class VenueView:
    """Everything about one venue that pricing a leg on it needs."""

    venue: Venue
    instrument: Instrument
    book: Book
    fees: FeeContext
    base_position: Position
    base_band: Band
    quote_position: Position
    quote_band: Band
    caps: CapSet


def price_cross_venue(
    buy: VenueView,
    sell: VenueView,
    terms: ScanTerms,
    *,
    ref: str,
    now: dt.datetime,
    pricer: RebalancePricer | None = None,
) -> Plan:
    """Price buying on one venue and selling on the other."""
    charger = pricer or NoRebalanceCost()
    _check_pair(buy, sell, terms, now)

    gross_bps = raw_cross_bps(buy.book, sell.book)
    size = _common_size(buy, sell, terms)
    bought = walk(buy.book, Side.ASK, size)
    sold = walk(sell.book, Side.BID, size)

    buy_fee = charge_for(buy.fees, bought.notional, resting=False)
    sell_fee = charge_for(sell.fees, sold.notional, resting=False)
    fee_total = buy_fee.signed_quote_amount + sell_fee.signed_quote_amount
    fee_bps = fee_total / bought.notional * BPS
    slip_bps = slippage_bps(buy.book, bought) + slippage_bps(sell.book, sold)

    excess = excess_above_ceiling(buy.base_position, buy.base_band, size)
    rebalance_bps = charger.charge_bps(
        asset=buy.instrument.base,
        sender=buy.venue.code,
        receiver=sell.venue.code,
        excess=excess,
        unit_price=bought.vwap,
        notional=bought.notional,
    )

    net_bps = gross_bps - fee_bps - slip_bps - rebalance_bps
    status = PlanStatus.PRICED if size >= terms.wanted_size else PlanStatus.TRIMMED
    plan = Plan(
        ref=ref,
        kind=PlanKind.CROSS_VENUE,
        symbol=buy.instrument.symbol,
        legs=(
            _leg(buy, Side.ASK, bought, buy_fee.rate_bps, buy_fee.quote_amount),
            _leg(sell, Side.BID, sold, sell_fee.rate_bps, sell_fee.quote_amount),
        ),
        notional=bought.notional,
        gross_bps=gross_bps,
        fee_bps=fee_bps,
        slippage_bps=slip_bps,
        rebalance_bps=rebalance_bps,
        net_bps=net_bps,
        status=status,
    ).require_arithmetic()

    if net_bps < terms.min_edge_bps:
        raise refuse(
            "EDGE.01",
            f"{plan.ref} nets {net_bps} against a floor of {terms.min_edge_bps}",
        )
    return plan


def _check_pair(buy: VenueView, sell: VenueView, terms: ScanTerms, now: dt.datetime) -> None:
    if buy.instrument.symbol != sell.instrument.symbol:
        raise refuse("EDGE.02", f"{buy.instrument.symbol} against {sell.instrument.symbol}")
    if buy.venue.code == sell.venue.code:
        raise refuse("EDGE.02", f"{buy.venue.code} against itself")
    require_fresh(buy.book, buy.venue, now)
    require_fresh(sell.book, sell.venue, now)
    check_pairing(buy.book, sell.book, terms.pairing_window_ms)


def _common_size(buy: VenueView, sell: VenueView, terms: ScanTerms) -> Decimal:
    buy_side = size_leg(
        buy.book,
        buy.instrument,
        side=Side.ASK,
        depth_limit_bps=buy.venue.depth_limit_bps,
        spending=buy.quote_position,
        spending_band=buy.quote_band,
        receiving=buy.base_position,
        receiving_band=buy.base_band,
        caps=buy.caps,
        wanted=terms.wanted_size,
    )
    sell_side = size_leg(
        sell.book,
        sell.instrument,
        side=Side.BID,
        depth_limit_bps=sell.venue.depth_limit_bps,
        spending=sell.base_position,
        spending_band=sell.base_band,
        receiving=sell.quote_position,
        receiving_band=sell.quote_band,
        caps=sell.caps,
        wanted=terms.wanted_size,
    )
    return min(buy_side.size, sell_side.size)


def _leg(view: VenueView, takes: Side, sweep: Sweep, fee_bps: Decimal, fee: Decimal) -> Leg:
    return Leg(
        venue=view.venue.code,
        symbol=view.instrument.symbol,
        takes=takes,
        price=sweep.vwap,
        size=sweep.size,
        fee_bps=fee_bps,
        fee_amount=fee,
        levels_swept=sweep.levels,
        slippage_bps=slippage_bps(view.book, sweep),
    )
