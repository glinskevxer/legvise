"""Transfer networks, which is how inventory gets back where it belongs.

An asset is not one thing to move. USDT on Tron settles in about a minute for a
flat dollar; the same USDT on Ethereum can cost thirty and take fifteen minutes;
the same balance on a venue that has suspended withdrawals cannot move at all.
The desk's rebalancing cost therefore depends on which network is open at both
ends, and "both ends" is the part that is easy to forget -- a venue that allows
withdrawals on a network the receiving venue does not credit is no route.

None of this happens inside a plan. It happens afterwards, on a slower clock,
and its cost is amortised back across the plans that caused the imbalance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from legvise.errors import BadArgument
from legvise.ids import asset_code, venue_code
from legvise.money import ZERO, dec

__all__ = ["TransferNetwork", "VenueNetwork"]

_NETWORK_RE: Final = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,15}$")


def network_code(text: str) -> str:
    """Normalise a network code, or refuse it."""
    out = text.strip().upper()
    if not _NETWORK_RE.match(out):
        raise BadArgument("network", text, "expected 2 to 16 characters of A-Z, 0-9, _ and -")
    return out


@dataclass(frozen=True, slots=True)
class TransferNetwork:
    """One way of moving one asset, and what it costs in money and time."""

    asset: str
    code: str
    withdraw_fee: Decimal
    min_withdraw: Decimal
    confirmations: int
    minutes_per_confirmation: Decimal

    def __post_init__(self) -> None:
        if self.asset != asset_code(self.asset):
            raise BadArgument("asset", self.asset, "asset codes are stored normalised")
        if self.code != network_code(self.code):
            raise BadArgument("code", self.code, "network codes are stored normalised")
        if self.withdraw_fee < ZERO:
            raise BadArgument("withdraw_fee", str(self.withdraw_fee), "a fee is not negative")
        if self.min_withdraw <= ZERO:
            raise BadArgument(
                "min_withdraw", str(self.min_withdraw), "a minimum withdrawal has to be positive"
            )
        if self.confirmations <= 0:
            raise BadArgument(
                "confirmations", self.confirmations, "a transfer needs at least one confirmation"
            )
        if self.minutes_per_confirmation <= ZERO:
            raise BadArgument(
                "minutes_per_confirmation",
                str(self.minutes_per_confirmation),
                "a block takes some time",
            )

    @property
    def settle_minutes(self) -> Decimal:
        """How long a transfer takes to clear, in minutes."""
        return self.minutes_per_confirmation * Decimal(self.confirmations)

    @property
    def key(self) -> tuple[str, str]:
        """The pair the store keys on."""
        return (self.asset, self.code)

    def net_of_fee(self, amount: Decimal) -> Decimal:
        """What arrives at the other end after the network fee comes off."""
        if amount < self.min_withdraw:
            raise BadArgument(
                "amount", str(amount), f"below the {self.code} minimum of {self.min_withdraw}"
            )
        return amount - self.withdraw_fee

    @classmethod
    def build(
        cls,
        asset: str,
        code: str,
        *,
        withdraw_fee: str | Decimal,
        min_withdraw: str | Decimal,
        confirmations: int,
        minutes_per_confirmation: str | Decimal,
    ) -> TransferNetwork:
        """Build a network from loose input."""
        return cls(
            asset=asset_code(asset),
            code=network_code(code),
            withdraw_fee=dec(withdraw_fee, field="withdraw_fee"),
            min_withdraw=dec(min_withdraw, field="min_withdraw"),
            confirmations=confirmations,
            minutes_per_confirmation=dec(
                minutes_per_confirmation, field="minutes_per_confirmation"
            ),
        )


@dataclass(frozen=True, slots=True)
class VenueNetwork:
    """Whether one venue will send or receive one asset over one network."""

    venue: str
    asset: str
    network: str
    deposit_enabled: bool
    withdraw_enabled: bool

    def __post_init__(self) -> None:
        if self.venue != venue_code(self.venue):
            raise BadArgument("venue", self.venue, "venue codes are stored normalised")
        if self.asset != asset_code(self.asset):
            raise BadArgument("asset", self.asset, "asset codes are stored normalised")
        if self.network != network_code(self.network):
            raise BadArgument("network", self.network, "network codes are stored normalised")

    @property
    def key(self) -> tuple[str, str, str]:
        """The triple the store keys on."""
        return (self.venue, self.asset, self.network)

    @classmethod
    def build(
        cls,
        venue: str,
        asset: str,
        network: str,
        *,
        deposit_enabled: bool = True,
        withdraw_enabled: bool = True,
    ) -> VenueNetwork:
        """Build a venue network entry from loose input."""
        return cls(
            venue=venue_code(venue),
            asset=asset_code(asset),
            network=network_code(network),
            deposit_enabled=deposit_enabled,
            withdraw_enabled=withdraw_enabled,
        )
