"""Fixtures every test layer shares: a migrated database and a stopped clock."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from legvise.clock import FixedClock
from legvise.model.venue import Venue
from legvise.store.db import Database
from legvise.store.schema import install

INSTALLED_AT = "2025-02-11T08:00:00+00:00"
SESSION_START = dt.datetime(2025, 2, 11, 9, 30, tzinfo=dt.UTC)


@pytest.fixture()
def db() -> Iterator[Database]:
    """An in-memory book of record with the schema already applied.

    Closed on the way out. An in-memory database costs nothing to leak in the
    sense that matters -- there is no file -- but a connection nothing closed
    is still a connection, and on Python 3.13 the collector says so out loud:
    `ResourceWarning: unclosed database`, raised as an error by this suite's
    `filterwarnings`, blaming whichever test happened to be running when the
    collection ran rather than the one that leaked it.
    """
    handle = Database.in_memory()
    install(handle, applied_at=INSTALLED_AT)
    yield handle
    handle.close()


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
