"""Reading and writing balances and the bands that govern them.

Balances are overwritten wholesale by whatever job reconciles against the
venues; there is no attempt to keep a running total here. A desk that derives
its balance from its own fill history and never checks it against the venue
finds out it was wrong at the worst possible moment.

Bands are edited by a human and change rarely.
"""

from __future__ import annotations

import sqlite3

from legvise.errors import NotFound
from legvise.ids import asset_code
from legvise.model.inventory import Band, Position
from legvise.rows import as_decimal, as_text
from legvise.store.db import Database

__all__ = ["InventoryStore"]

_POSITION_COLUMNS = "venue_code, asset, free, locked, as_of"
_BAND_COLUMNS = "venue_code, asset, floor_qty, target_qty, ceiling_qty"


def _read_position(row: sqlite3.Row) -> Position:
    return Position(
        venue=as_text(row, "venue_code"),
        asset=as_text(row, "asset"),
        free=as_decimal(row, "free"),
        locked=as_decimal(row, "locked"),
        as_of=as_text(row, "as_of"),
    )


def _read_band(row: sqlite3.Row) -> Band:
    return Band(
        venue=as_text(row, "venue_code"),
        asset=as_text(row, "asset"),
        floor=as_decimal(row, "floor_qty"),
        target=as_decimal(row, "target_qty"),
        ceiling=as_decimal(row, "ceiling_qty"),
    )


class InventoryStore:
    """The position table and the band table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def put_position(self, position: Position) -> Position:
        """Write a balance, replacing whatever was there."""
        self._db.execute(
            f"INSERT INTO position ({_POSITION_COLUMNS}) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (venue_code, asset) DO UPDATE SET free = excluded.free,"
            " locked = excluded.locked, as_of = excluded.as_of",
            (
                position.venue,
                position.asset,
                position.free,
                position.locked,
                position.as_of,
            ),
        )
        return position

    def position(self, venue: str, asset: str) -> Position | None:
        """One balance, or nothing if the desk holds none of it there."""
        row = self._db.query_one(
            f"SELECT {_POSITION_COLUMNS} FROM position WHERE venue_code = ? AND asset = ?",
            (venue, asset_code(asset)),
        )
        return None if row is None else _read_position(row)

    def require_position(self, venue: str, asset: str) -> Position:
        """One balance, refusing to price a leg without it."""
        found = self.position(venue, asset)
        if found is None:
            raise NotFound("position", f"{venue}:{asset}")
        return found

    def positions_on(self, venue: str) -> tuple[Position, ...]:
        """Every balance on one venue, in asset order."""
        rows = self._db.query(
            f"SELECT {_POSITION_COLUMNS} FROM position WHERE venue_code = ? ORDER BY asset",
            (venue,),
        )
        return tuple(_read_position(r) for r in rows)

    def positions_of(self, asset: str) -> tuple[Position, ...]:
        """The same asset across every venue, in venue order."""
        rows = self._db.query(
            f"SELECT {_POSITION_COLUMNS} FROM position WHERE asset = ? ORDER BY venue_code",
            (asset_code(asset),),
        )
        return tuple(_read_position(r) for r in rows)

    def put_band(self, band: Band) -> Band:
        """Write a band, replacing whatever was there."""
        self._db.execute(
            f"INSERT INTO inventory_band ({_BAND_COLUMNS}) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (venue_code, asset) DO UPDATE SET floor_qty = excluded.floor_qty,"
            " target_qty = excluded.target_qty, ceiling_qty = excluded.ceiling_qty",
            (band.venue, band.asset, band.floor, band.target, band.ceiling),
        )
        return band

    def band(self, venue: str, asset: str) -> Band | None:
        """One band, or nothing if the desk has not set one."""
        row = self._db.query_one(
            f"SELECT {_BAND_COLUMNS} FROM inventory_band WHERE venue_code = ? AND asset = ?",
            (venue, asset_code(asset)),
        )
        return None if row is None else _read_band(row)

    def require_band(self, venue: str, asset: str) -> Band:
        """One band, refusing to size a leg without one."""
        found = self.band(venue, asset)
        if found is None:
            raise NotFound("inventory band", f"{venue}:{asset}")
        return found

    def bands_on(self, venue: str) -> tuple[Band, ...]:
        """Every band on one venue, in asset order."""
        rows = self._db.query(
            f"SELECT {_BAND_COLUMNS} FROM inventory_band WHERE venue_code = ? ORDER BY asset",
            (venue,),
        )
        return tuple(_read_band(r) for r in rows)

    def remove_band(self, venue: str, asset: str) -> None:
        """Drop a band."""
        cursor = self._db.execute(
            "DELETE FROM inventory_band WHERE venue_code = ? AND asset = ?",
            (venue, asset_code(asset)),
        )
        if cursor.rowcount == 0:
            raise NotFound("inventory band", f"{venue}:{asset}")

    def assets_held(self) -> tuple[str, ...]:
        """Every asset the desk holds anywhere, in order."""
        rows = self._db.query("SELECT DISTINCT asset FROM position ORDER BY asset")
        return tuple(as_text(r, "asset") for r in rows)
