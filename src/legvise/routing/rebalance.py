"""What it costs to put inventory back, and how that lands on a plan.

A prefunded desk pays for arbitrage twice. Once at the touch, in fees and
slippage, and once later when somebody moves the inventory the trade displaced.
The second cost is invisible in the plan that caused it unless it is put there
on purpose, which is what this module does.

Two parts to the number:

- the **network fee**, which is flat per transfer and therefore cheaper per unit
  the more the desk moves at once
- the **carry**, which is what the capital costs while it is in flight. A forty
  minute settlement on a network with a one dollar fee is not obviously cheaper
  than a one minute settlement at twelve dollars, and which one wins depends on
  the size

Both are then divided by the number of plans the transfer is expected to serve,
because a transfer that clears the imbalance from twenty cycles should not be
charged in full to the one that happened to cross the ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

from legvise.errors import BadArgument
from legvise.model.network import TransferNetwork
from legvise.money import BPS, ZERO, dec
from legvise.rules import refuse

__all__ = ["CarryTerms", "RouteQuote", "amortised_bps", "cheapest_route", "quote_route"]

MINUTES_PER_HOUR = dec("60")


class CarryTerms(NamedTuple):
    """What the desk charges itself for capital in flight."""

    carry_bps_per_hour: Decimal
    cycles_served: int

    def validated(self) -> CarryTerms:
        """Refuse terms that would make the amortisation meaningless."""
        if self.carry_bps_per_hour < ZERO:
            raise BadArgument(
                "carry_bps_per_hour", str(self.carry_bps_per_hour), "carry is not negative"
            )
        if self.cycles_served <= 0:
            raise BadArgument(
                "cycles_served", self.cycles_served, "a transfer serves at least one cycle"
            )
        return self


@dataclass(frozen=True, slots=True)
class RouteQuote:
    """One way of moving an amount, priced in the asset being moved."""

    network: str
    amount: Decimal
    fee: Decimal
    carry: Decimal
    settle_minutes: Decimal

    @property
    def total(self) -> Decimal:
        """Everything the transfer costs, in units of the asset moved."""
        return self.fee + self.carry

    @property
    def arrives(self) -> Decimal:
        """How much of the asset actually lands at the other end."""
        return self.amount - self.fee


def quote_route(network: TransferNetwork, amount: Decimal, terms: CarryTerms) -> RouteQuote:
    """Price one network for moving `amount` of its asset."""
    terms.validated()
    if amount <= ZERO:
        raise BadArgument("amount", str(amount), "a transfer needs a positive amount")
    if amount < network.min_withdraw:
        raise refuse(
            "BAND.02",
            f"{network.code} needs at least {network.min_withdraw}, not {amount}",
        )
    hours = network.settle_minutes / MINUTES_PER_HOUR
    carry = amount * terms.carry_bps_per_hour / BPS * hours
    return RouteQuote(
        network=network.code,
        amount=amount,
        fee=network.withdraw_fee,
        carry=carry,
        settle_minutes=network.settle_minutes,
    )


def cheapest_route(
    networks: tuple[TransferNetwork, ...], amount: Decimal, terms: CarryTerms
) -> RouteQuote:
    """The cheapest usable network, refusing when none of them can take it.

    Ties break on settlement time, then on code, so the answer does not depend
    on the order the store happened to return.
    """
    quotes: list[RouteQuote] = []
    for network in networks:
        if amount < network.min_withdraw:
            continue
        quotes.append(quote_route(network, amount, terms))
    if not quotes:
        raise refuse("BAND.02", f"no open network can move {amount}")
    return min(quotes, key=lambda q: (q.total, q.settle_minutes, q.network))


def amortised_bps(
    quote: RouteQuote, unit_price: Decimal, notional: Decimal, terms: CarryTerms
) -> Decimal:
    """The transfer's share of one plan, as basis points of that plan's notional.

    `unit_price` converts the asset being moved into the quote asset the plan is
    denominated in, because a transfer of BTC has to be charged against a plan
    measured in dollars.
    """
    terms.validated()
    if unit_price <= ZERO:
        raise BadArgument("unit_price", str(unit_price), "a conversion price has to be positive")
    if notional <= ZERO:
        raise BadArgument("notional", str(notional), "a plan needs a notional to charge against")
    in_quote = quote.total * unit_price
    per_cycle = in_quote / Decimal(terms.cycles_served)
    return per_cycle / notional * BPS
