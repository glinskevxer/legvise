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

_M0003 = Migration(
    version=3,
    name="fee ladders and trailing volume",
    statements=(
        """
        CREATE TABLE fee_tier (
            venue_code     TEXT NOT NULL REFERENCES venue (code) ON DELETE CASCADE,
            rung           INTEGER NOT NULL CHECK (rung >= 0),
            min_volume_30d TEXT NOT NULL,
            maker_bps      TEXT NOT NULL,
            taker_bps      TEXT NOT NULL,
            PRIMARY KEY (venue_code, rung)
        )
        """,
        """
        CREATE TABLE venue_volume (
            venue_code  TEXT PRIMARY KEY REFERENCES venue (code) ON DELETE CASCADE,
            volume_30d  TEXT NOT NULL,
            as_of       TEXT NOT NULL
        )
        """,
    ),
)

_M0004 = Migration(
    version=4,
    name="positions and inventory bands",
    statements=(
        """
        CREATE TABLE position (
            venue_code TEXT NOT NULL REFERENCES venue (code) ON DELETE CASCADE,
            asset      TEXT NOT NULL,
            free       TEXT NOT NULL,
            locked     TEXT NOT NULL,
            as_of      TEXT NOT NULL,
            PRIMARY KEY (venue_code, asset)
        )
        """,
        """
        CREATE TABLE inventory_band (
            venue_code  TEXT NOT NULL REFERENCES venue (code) ON DELETE CASCADE,
            asset       TEXT NOT NULL,
            floor_qty   TEXT NOT NULL,
            target_qty  TEXT NOT NULL,
            ceiling_qty TEXT NOT NULL,
            PRIMARY KEY (venue_code, asset)
        )
        """,
        "CREATE INDEX ix_position_asset ON position (asset)",
        "CREATE INDEX ix_band_asset ON inventory_band (asset)",
    ),
)

_M0005 = Migration(
    version=5,
    name="transfer networks",
    statements=(
        """
        CREATE TABLE transfer_network (
            asset                    TEXT NOT NULL,
            code                     TEXT NOT NULL,
            withdraw_fee             TEXT NOT NULL,
            min_withdraw             TEXT NOT NULL,
            confirmations            INTEGER NOT NULL CHECK (confirmations > 0),
            minutes_per_confirmation TEXT NOT NULL,
            PRIMARY KEY (asset, code)
        )
        """,
        """
        CREATE TABLE venue_network (
            venue_code       TEXT NOT NULL REFERENCES venue (code) ON DELETE CASCADE,
            asset            TEXT NOT NULL,
            network          TEXT NOT NULL,
            deposit_enabled  INTEGER NOT NULL CHECK (deposit_enabled IN (0, 1)),
            withdraw_enabled INTEGER NOT NULL CHECK (withdraw_enabled IN (0, 1)),
            PRIMARY KEY (venue_code, asset, network),
            FOREIGN KEY (asset, network)
                REFERENCES transfer_network (asset, code) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX ix_venue_network_pair ON venue_network (asset, network)",
    ),
)

_M0006 = Migration(
    version=6,
    name="scan sessions and plans",
    statements=(
        """
        CREATE TABLE scan_session (
            ref               TEXT PRIMARY KEY,
            started_at        TEXT NOT NULL,
            min_edge_bps      TEXT NOT NULL,
            pairing_window_ms INTEGER NOT NULL CHECK (pairing_window_ms >= 0),
            wanted_size       TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE plan (
            ref           TEXT PRIMARY KEY,
            session_ref   TEXT NOT NULL REFERENCES scan_session (ref) ON DELETE CASCADE,
            kind          TEXT NOT NULL CHECK (kind IN ('cross_venue', 'triangular')),
            symbol        TEXT NOT NULL,
            notional      TEXT NOT NULL,
            gross_bps     TEXT NOT NULL,
            fee_bps       TEXT NOT NULL,
            slippage_bps  TEXT NOT NULL,
            rebalance_bps TEXT NOT NULL,
            net_bps       TEXT NOT NULL,
            status        TEXT NOT NULL CHECK (status IN ('priced', 'trimmed', 'refused')),
            clause        TEXT
        )
        """,
        """
        CREATE TABLE plan_leg (
            plan_ref     TEXT NOT NULL REFERENCES plan (ref) ON DELETE CASCADE,
            leg_index    INTEGER NOT NULL CHECK (leg_index >= 0),
            venue_code   TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            takes        TEXT NOT NULL CHECK (takes IN ('bid', 'ask')),
            price        TEXT NOT NULL,
            size         TEXT NOT NULL,
            fee_bps      TEXT NOT NULL,
            fee_amount   TEXT NOT NULL,
            levels_swept INTEGER NOT NULL CHECK (levels_swept >= 1),
            slippage_bps TEXT NOT NULL,
            PRIMARY KEY (plan_ref, leg_index)
        )
        """,
        "CREATE INDEX ix_plan_session ON plan (session_ref)",
        "CREATE INDEX ix_plan_clause ON plan (clause)",
        "CREATE INDEX ix_plan_symbol ON plan (symbol)",
        "CREATE INDEX ix_plan_leg_plan ON plan_leg (plan_ref)",
    ),
)

_M0007 = Migration(
    version=7,
    name="fills against a plan",
    statements=(
        """
        CREATE TABLE fill (
            plan_ref       TEXT NOT NULL REFERENCES plan (ref) ON DELETE CASCADE,
            leg_index      INTEGER NOT NULL CHECK (leg_index >= 0),
            venue_code     TEXT NOT NULL,
            takes          TEXT NOT NULL CHECK (takes IN ('bid', 'ask')),
            price          TEXT NOT NULL,
            size           TEXT NOT NULL,
            fee_amount     TEXT NOT NULL,
            filled_at      TEXT NOT NULL,
            venue_trade_id TEXT NOT NULL,
            PRIMARY KEY (venue_code, venue_trade_id)
        )
        """,
        "CREATE INDEX ix_fill_plan ON fill (plan_ref, leg_index)",
        "CREATE INDEX ix_fill_time ON fill (filled_at)",
    ),
)

MIGRATIONS: tuple[Migration, ...] = (
    _M0001,
    _M0002,
    _M0003,
    _M0004,
    _M0005,
    _M0006,
    _M0007,
)


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
