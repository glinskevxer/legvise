"""The rebalance pricer the live scanner uses, backed by the network store.

`scan.direct` takes a `RebalancePricer` rather than reaching for the store
itself, so the pricing path stays testable without a database. This is the
implementation that actually looks routes up.

Two decisions worth reading before changing anything here.

A plan that causes **no** excess is charged nothing, and that is checked before
any route lookup, because the common case is no excess and a database round
trip per candidate pair is the difference between a scan that finishes inside
the pairing window and one that does not.

A plan that causes an excess with **no open route** is charged rather than
refused. The desk can still do the trade; it just has to unwind the imbalance
by trading rather than transferring, which is more expensive. `stranded_bps` is
the number that stands in for that, and setting it to something enormous is how
an operator turns it back into a refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from legvise.errors import Refused
from legvise.money import ZERO
from legvise.routing.rebalance import CarryTerms, amortised_bps, cheapest_route
from legvise.store.networks import NetworkStore

__all__ = ["StoreRebalancePricer"]


@dataclass(frozen=True, slots=True)
class StoreRebalancePricer:
    """Prices the cheapest open route, or falls back to a stranding charge."""

    networks: NetworkStore
    terms: CarryTerms
    stranded_bps: Decimal

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
        if excess <= ZERO:
            return ZERO
        routes = self.networks.routes_between(asset, sender, receiver)
        try:
            quote = cheapest_route(routes, excess, self.terms)
        except Refused:
            return self.stranded_bps
        return amortised_bps(quote, unit_price, notional, self.terms)

    def route_for(self, asset: str, sender: str, receiver: str, excess: Decimal) -> str | None:
        """Which network would carry the excess, or nothing when none can."""
        if excess <= ZERO:
            return None
        routes = self.networks.routes_between(asset, sender, receiver)
        try:
            return cheapest_route(routes, excess, self.terms).network
        except Refused:
            return None
