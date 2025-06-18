"""Reading and writing transfer networks and the venues that support them.

The one query worth knowing about is `routes_between`. Everything else here is
ordinary storage; that one answers the question the rebalancer actually asks,
which is "which networks can move this asset from A to B right now", and it has
to check the sending end and the receiving end separately because a venue can
have one open and the other shut.
"""

from __future__ import annotations

import sqlite3

from legvise.errors import NotFound
from legvise.ids import asset_code
from legvise.model.network import TransferNetwork, VenueNetwork, network_code
from legvise.rows import as_bool, as_decimal, as_int, as_text, flag
from legvise.store.db import Database

__all__ = ["NetworkStore"]

_NETWORK_COLUMNS = (
    "asset, code, withdraw_fee, min_withdraw, confirmations, minutes_per_confirmation"
)
_VENUE_NETWORK_COLUMNS = "venue_code, asset, network, deposit_enabled, withdraw_enabled"


def _read_network(row: sqlite3.Row) -> TransferNetwork:
    return TransferNetwork(
        asset=as_text(row, "asset"),
        code=as_text(row, "code"),
        withdraw_fee=as_decimal(row, "withdraw_fee"),
        min_withdraw=as_decimal(row, "min_withdraw"),
        confirmations=as_int(row, "confirmations"),
        minutes_per_confirmation=as_decimal(row, "minutes_per_confirmation"),
    )


def _read_venue_network(row: sqlite3.Row) -> VenueNetwork:
    return VenueNetwork(
        venue=as_text(row, "venue_code"),
        asset=as_text(row, "asset"),
        network=as_text(row, "network"),
        deposit_enabled=as_bool(row, "deposit_enabled"),
        withdraw_enabled=as_bool(row, "withdraw_enabled"),
    )


class NetworkStore:
    """The transfer network table and the venue support table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def put_network(self, network: TransferNetwork) -> TransferNetwork:
        """Write a network, replacing whatever was there."""
        self._db.execute(
            f"INSERT INTO transfer_network ({_NETWORK_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (asset, code) DO UPDATE SET withdraw_fee = excluded.withdraw_fee,"
            " min_withdraw = excluded.min_withdraw, confirmations = excluded.confirmations,"
            " minutes_per_confirmation = excluded.minutes_per_confirmation",
            (
                network.asset,
                network.code,
                network.withdraw_fee,
                network.min_withdraw,
                network.confirmations,
                network.minutes_per_confirmation,
            ),
        )
        return network

    def network(self, asset: str, code: str) -> TransferNetwork | None:
        """One network, or nothing."""
        row = self._db.query_one(
            f"SELECT {_NETWORK_COLUMNS} FROM transfer_network WHERE asset = ? AND code = ?",
            (asset_code(asset), network_code(code)),
        )
        return None if row is None else _read_network(row)

    def require_network(self, asset: str, code: str) -> TransferNetwork:
        """One network, refusing to price a transfer without it."""
        found = self.network(asset, code)
        if found is None:
            raise NotFound("transfer network", f"{asset}:{code}")
        return found

    def networks_for(self, asset: str) -> tuple[TransferNetwork, ...]:
        """Every network that can move an asset, in code order."""
        rows = self._db.query(
            f"SELECT {_NETWORK_COLUMNS} FROM transfer_network WHERE asset = ? ORDER BY code",
            (asset_code(asset),),
        )
        return tuple(_read_network(r) for r in rows)

    def put_support(self, entry: VenueNetwork) -> VenueNetwork:
        """Record whether a venue will send and receive on a network."""
        self._db.execute(
            f"INSERT INTO venue_network ({_VENUE_NETWORK_COLUMNS}) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (venue_code, asset, network)"
            " DO UPDATE SET deposit_enabled = excluded.deposit_enabled,"
            " withdraw_enabled = excluded.withdraw_enabled",
            (
                entry.venue,
                entry.asset,
                entry.network,
                flag(entry.deposit_enabled),
                flag(entry.withdraw_enabled),
            ),
        )
        return entry

    def support(self, venue: str, asset: str, code: str) -> VenueNetwork | None:
        """What one venue will do with one network, or nothing."""
        row = self._db.query_one(
            f"SELECT {_VENUE_NETWORK_COLUMNS} FROM venue_network"
            " WHERE venue_code = ? AND asset = ? AND network = ?",
            (venue, asset_code(asset), network_code(code)),
        )
        return None if row is None else _read_venue_network(row)

    def support_on(self, venue: str, asset: str) -> tuple[VenueNetwork, ...]:
        """Every network a venue lists for an asset, in code order."""
        rows = self._db.query(
            f"SELECT {_VENUE_NETWORK_COLUMNS} FROM venue_network"
            " WHERE venue_code = ? AND asset = ? ORDER BY network",
            (venue, asset_code(asset)),
        )
        return tuple(_read_venue_network(r) for r in rows)

    def routes_between(self, asset: str, sender: str, receiver: str) -> tuple[TransferNetwork, ...]:
        """Networks that can actually move `asset` from `sender` to `receiver`.

        Both ends have to agree: the sender has to allow withdrawals and the
        receiver has to credit deposits. A network either side has never heard
        of is not a route.
        """
        rows = self._db.query(
            f"SELECT n.{', n.'.join(_NETWORK_COLUMNS.split(', '))} FROM transfer_network n"
            " JOIN venue_network out_leg ON out_leg.asset = n.asset"
            " AND out_leg.network = n.code AND out_leg.venue_code = ?"
            " JOIN venue_network in_leg ON in_leg.asset = n.asset"
            " AND in_leg.network = n.code AND in_leg.venue_code = ?"
            " WHERE n.asset = ? AND out_leg.withdraw_enabled = 1 AND in_leg.deposit_enabled = 1"
            " ORDER BY n.code",
            (sender, receiver, asset_code(asset)),
        )
        return tuple(_read_network(r) for r in rows)
