"""Fee ladders and the trailing volume that picks a rung out of one.

The ladder and the volume live in separate tables because they change on
completely different clocks. A venue republishes its ladder once or twice a
year; the desk's trailing volume moves every day. Storing the resolved rate
would mean rewriting it nightly and losing the ability to reprice an old plan
against the ladder that was live when it was written.
"""

from __future__ import annotations

from decimal import Decimal

from legvise.errors import NotFound
from legvise.model.fee import FeeLadder, FeeTier
from legvise.rows import as_decimal, as_text
from legvise.store.db import Database

__all__ = ["FeeStore"]

_TIER_COLUMNS = "venue_code, rung, min_volume_30d, maker_bps, taker_bps"


class FeeStore:
    """The fee tier table and the trailing volume table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def put_ladder(self, ladder: FeeLadder) -> FeeLadder:
        """Replace a venue's whole ladder in one transaction.

        Replace, not merge. A ladder with a rung removed has to end up with that
        rung gone, and an upsert per rung leaves the old one behind.
        """
        with self._db.tx():
            self._db.execute("DELETE FROM fee_tier WHERE venue_code = ?", (ladder.venue,))
            for rung, tier in enumerate(ladder.tiers):
                self._db.execute(
                    f"INSERT INTO fee_tier ({_TIER_COLUMNS}) VALUES (?, ?, ?, ?, ?)",
                    (
                        ladder.venue,
                        rung,
                        tier.min_volume_30d,
                        tier.maker_bps,
                        tier.taker_bps,
                    ),
                )
        return ladder

    def ladder(self, venue: str) -> FeeLadder:
        """One venue's ladder, or a `NotFound` naming it."""
        found = self.find_ladder(venue)
        if found is None:
            raise NotFound("fee ladder", venue)
        return found

    def find_ladder(self, venue: str) -> FeeLadder | None:
        """One venue's ladder, or nothing."""
        rows = self._db.query(
            f"SELECT {_TIER_COLUMNS} FROM fee_tier WHERE venue_code = ? ORDER BY rung",
            (venue,),
        )
        if not rows:
            return None
        tiers = tuple(
            FeeTier(
                min_volume_30d=as_decimal(r, "min_volume_30d"),
                maker_bps=as_decimal(r, "maker_bps"),
                taker_bps=as_decimal(r, "taker_bps"),
            )
            for r in rows
        )
        return FeeLadder(venue=as_text(rows[0], "venue_code"), tiers=tiers)

    def venues_with_ladders(self) -> tuple[str, ...]:
        """Every venue that has a ladder on file."""
        rows = self._db.query("SELECT DISTINCT venue_code FROM fee_tier ORDER BY venue_code")
        return tuple(as_text(r, "venue_code") for r in rows)

    def record_volume(self, venue: str, volume_30d: Decimal, *, as_of: str) -> None:
        """Write the desk's trailing thirty day volume on a venue."""
        self._db.execute(
            "INSERT INTO venue_volume (venue_code, volume_30d, as_of) VALUES (?, ?, ?)"
            " ON CONFLICT (venue_code) DO UPDATE SET volume_30d = excluded.volume_30d,"
            " as_of = excluded.as_of",
            (venue, volume_30d, as_of),
        )

    def volume(self, venue: str) -> Decimal | None:
        """The recorded trailing volume, or nothing if nobody has recorded one."""
        row = self._db.query_one(
            "SELECT volume_30d FROM venue_volume WHERE venue_code = ?", (venue,)
        )
        return None if row is None else as_decimal(row, "volume_30d")

    def volume_as_of(self, venue: str) -> str | None:
        """When the recorded volume was measured."""
        row = self._db.query_one("SELECT as_of FROM venue_volume WHERE venue_code = ?", (venue,))
        return None if row is None else as_text(row, "as_of")

    def clear_volume(self, venue: str) -> None:
        """Forget a venue's recorded volume, so pricing refuses until it is set."""
        self._db.execute("DELETE FROM venue_volume WHERE venue_code = ?", (venue,))
