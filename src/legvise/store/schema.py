"""Every table the desk keeps, as an ordered list of migrations.

Read this file top to bottom to see how the schema grew. Nothing here is ever
edited once it has shipped; a change is a new numbered step at the bottom.
"""

from __future__ import annotations

from legvise.store.db import Database
from legvise.store.migrations import Migration, migrate

__all__ = ["MIGRATIONS", "install", "table_names"]

_M0001 = Migration(
    version=1,
    name="venues and instruments",
    statements=(
        """
        CREATE TABLE venue (
            code                TEXT PRIMARY KEY,
            display_name        TEXT NOT NULL,
            staleness_budget_ms INTEGER NOT NULL CHECK (staleness_budget_ms > 0),
            depth_limit_bps     TEXT NOT NULL,
            notional_cap        TEXT NOT NULL,
            pays_maker_rebate   INTEGER NOT NULL CHECK (pays_maker_rebate IN (0, 1)),
            active              INTEGER NOT NULL CHECK (active IN (0, 1))
        )
        """,
        """
        CREATE TABLE instrument (
            venue_code    TEXT NOT NULL REFERENCES venue (code) ON DELETE CASCADE,
            symbol        TEXT NOT NULL,
            base_asset    TEXT NOT NULL,
            quote_asset   TEXT NOT NULL,
            venue_symbol  TEXT NOT NULL,
            tick_size     TEXT NOT NULL,
            lot_step      TEXT NOT NULL,
            min_notional  TEXT NOT NULL,
            max_notional  TEXT NOT NULL,
            active        INTEGER NOT NULL CHECK (active IN (0, 1)),
            PRIMARY KEY (venue_code, symbol)
        )
        """,
        "CREATE INDEX ix_instrument_symbol ON instrument (symbol)",
        "CREATE INDEX ix_instrument_base ON instrument (base_asset)",
    ),
)

_M0002 = Migration(
    version=2,
    name="book snapshots",
    statements=(
        """
        CREATE TABLE book_snapshot (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            venue_code  TEXT NOT NULL REFERENCES venue (code) ON DELETE CASCADE,
            symbol      TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            sequence    INTEGER NOT NULL CHECK (sequence >= 0)
        )
        """,
        """
        CREATE TABLE book_level (
            snapshot_id INTEGER NOT NULL REFERENCES book_snapshot (id) ON DELETE CASCADE,
            side        TEXT NOT NULL CHECK (side IN ('bid', 'ask')),
            rank        INTEGER NOT NULL CHECK (rank >= 0),
            price       TEXT NOT NULL,
            size        TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, side, rank)
        )
        """,
        "CREATE INDEX ix_snapshot_lookup ON book_snapshot (venue_code, symbol, observed_at)",
        "CREATE INDEX ix_snapshot_symbol ON book_snapshot (symbol)",
        "CREATE INDEX ix_level_snapshot ON book_level (snapshot_id)",
    ),
)

MIGRATIONS: tuple[Migration, ...] = (_M0001, _M0002)


def install(db: Database, *, applied_at: str) -> tuple[int, ...]:
    """Bring a database up to the current schema and say what it ran."""
    return migrate(db, MIGRATIONS, applied_at=applied_at)


def table_names(db: Database) -> tuple[str, ...]:
    """Every table in the database, sorted, ledger included."""
    rows = db.query(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return tuple(str(r["name"]) for r in rows)
