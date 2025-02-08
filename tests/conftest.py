"""Fixtures every test layer shares: a migrated database and a stopped clock."""

from __future__ import annotations

import datetime as dt

import pytest

from legvise.clock import FixedClock
from legvise.model.venue import Venue
from legvise.store.db import Database
from legvise.store.schema import install

INSTALLED_AT = "2025-02-11T08:00:00+00:00"
SESSION_START = dt.datetime(2025, 2, 11, 9, 30, tzinfo=dt.UTC)


@pytest.fixture()
def db() -> Database:
    """An in-memory book of record with the schema already applied."""
    handle = Database.in_memory()
    install(handle, applied_at=INSTALLED_AT)
    return handle


@pytest.fixture()
def clock() -> FixedClock:
    """A clock the test moves by hand."""
    return FixedClock(SESSION_START)


def make_venue(code: str = "kraken", **changes: object) -> Venue:
    """A venue with sensible desk defaults, for tests that need one."""
    fields: dict[str, object] = {
        "display_name": code.title(),
        "staleness_budget_ms": 750,
        "depth_limit_bps": "35",
        "notional_cap": "250000",
    }
    fields.update(changes)
    return Venue.build(code, **fields)  # type: ignore[arg-type]
