"""Pricing a conversion loop for real, against depth and fees.

`scan.triangular` finds loops at the touch, which is a screen rather than a
price. This module takes one of those loops and works out what actually comes
back after sweeping each book for the size and paying the venue on every hop.

Three hops means three fees. At sixteen basis points a side that is forty eight
basis points of cost against a loop that screened at twelve, which is why a
triangular scanner that prices at the touch and stops there produces a list of
opportunities that all lose money.

The walk direction changes per hop and it is easy to get backwards. A hop
holding the base sells it, which means walking the bids for a **size**. A hop
holding the quote buys the base, which means walking the asks for a **budget**.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.fees.quote import FeeContext, charge_for
from legvise.ids import Symbol
from legvise.market.depth import Sweep, walk, walk_for_notional
from legvise.model.book import Book, Side
from legvise.model.cycle import Cycle, Hop
from legvise.model.plan import Leg, Plan, PlanKind, PlanStatus
from legvise.money import ZERO, dec
from legvise.rules import refuse

__all__ = ["HopFill", "LoopQuote", "price_cycle"]

ONE = dec("1")
BPS = dec("10000")


@dataclass(frozen=True, slots=True)
class HopFill:
    """What one hop of a loop actually got."""

    hop: Hop
    sweep: Sweep
    received: Decimal
    fee_paid: Decimal
    fee_bps: Decimal

    @property
    def realised_rate(self) -> Decimal:
        """Units out per unit in, after the fee."""
        return self.received / self.spent

    @property
    def spent(self) -> Decimal:
        """How much of the from asset the hop consumed."""
        return self.sweep.notional if self.hop.takes is Side.ASK else self.sweep.size


@dataclass(frozen=True, slots=True)
class LoopQuote:
    """A whole loop, priced hop by hop."""

    cycle: Cycle
    start_amount: Decimal
    fills: tuple[HopFill, ...]
    returned: Decimal

    @property
    def net_bps(self) -> Decimal:
        """What the loop makes after every fee, in basis points."""
        return (self.returned - self.start_amount) / self.start_amount * BPS

    @property
    def fee_bps(self) -> Decimal:
        """The gap between the touch edge and the priced edge."""
        return self.cycle.gross_bps - self.net_bps


def price_cycle(
    cycle: Cycle,
    books: dict[Symbol, Book],
    fees: FeeContext,
    *,
    start_amount: Decimal,
) -> LoopQuote:
    """Walk a loop for real and report what comes back."""
    if start_amount <= ZERO:
        raise BadArgument("start_amount", str(start_amount), "a loop starts with something")
    holding = start_amount
    fills: list[HopFill] = []
    for hop in cycle.hops:
        book = books.get(hop.symbol)
        if book is None:
            raise refuse("BOOK.02", f"{cycle.venue} has no book for {hop.symbol}")
        fills.append(_fill(hop, book, fees, holding))
        holding = fills[-1].received
    return LoopQuote(
        cycle=cycle,
        start_amount=start_amount,
        fills=tuple(fills),
        returned=holding,
    )


def _fill(hop: Hop, book: Book, fees: FeeContext, holding: Decimal) -> HopFill:
    side = hop.takes
    if side is Side.BID:
        sweep = walk(book, side, holding)
        if not sweep.complete:
            raise refuse("DEPTH.01", f"{book.venue} {hop.symbol} for {holding}")
        gross = sweep.notional
    else:
        sweep = walk_for_notional(book, side, holding)
        if not sweep.complete:
            raise refuse("DEPTH.01", f"{book.venue} {hop.symbol} for {holding}")
        gross = sweep.size
    charge = charge_for(fees, sweep.notional, resting=False)
    taken = _fee_in_received(charge.signed_quote_amount, sweep, side)
    return HopFill(
        hop=hop,
        sweep=sweep,
        received=gross - taken,
        fee_paid=taken,
        fee_bps=charge.rate_bps,
    )


def _fee_in_received(quote_fee: Decimal, sweep: Sweep, side: Side) -> Decimal:
    """The fee expressed in whatever asset the hop received.

    A venue charges in the quote asset. On a sell that is what arrives, so the
    fee comes straight off. On a buy the base arrives, so the same charge has to
    be divided by the price actually paid.
    """
    if side is Side.BID:
        return quote_fee
    return quote_fee / sweep.vwap


def as_plan(quote: LoopQuote, *, ref: str, min_edge_bps: Decimal) -> Plan:
    """Turn a priced loop into a plan record, refusing one that does not pay."""
    legs = tuple(
        Leg(
            venue=quote.cycle.venue,
            symbol=fill.hop.symbol,
            takes=fill.hop.takes,
            price=fill.sweep.vwap,
            size=fill.sweep.size,
            fee_bps=fill.fee_bps,
            fee_amount=fill.fee_paid,
            levels_swept=fill.sweep.levels,
            slippage_bps=ZERO,
        )
        for fill in quote.fills
    )
    plan = Plan(
        ref=ref,
        kind=PlanKind.TRIANGULAR,
        symbol=quote.cycle.hops[0].symbol,
        legs=legs,
        notional=quote.fills[0].sweep.notional,
        gross_bps=quote.cycle.gross_bps,
        fee_bps=quote.fee_bps,
        slippage_bps=ZERO,
        rebalance_bps=ZERO,
        net_bps=quote.net_bps,
        status=PlanStatus.PRICED,
    ).require_arithmetic()
    if quote.net_bps < min_edge_bps:
        raise refuse("EDGE.01", f"{ref} nets {quote.net_bps} against {min_edge_bps}")
    return plan
