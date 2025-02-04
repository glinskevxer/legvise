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

MIGRATIONS: tuple[Migration, ...] = (_M0001,)


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
