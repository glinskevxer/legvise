"""Forward-only migrations, applied in order and recorded as they go.

There is no down migration and there is not going to be one. The book of record
is a file; the recovery story is a copy of the file, which is honest, and a
half-written down migration is a way to lose the copy you still had.

A migration that has already been applied is frozen. Its text is hashed into
`applied_migration` when it runs, and the runner refuses to start if an earlier
migration's text has moved since. Editing a shipped migration is the mistake
this catches, and it is a quiet one otherwise: the developer sees the new text,
production sees the old schema, and nothing says so.
"""

from __future__ import annotations

import hashlib
from typing import NamedTuple

from legvise.errors import Refused
from legvise.store.db import Database

__all__ = ["Migration", "applied_versions", "migrate", "pending", "text_digest"]

_LEDGER = """
CREATE TABLE IF NOT EXISTS applied_migration (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    digest      TEXT NOT NULL,
    applied_at  TEXT NOT NULL
)
"""


class Migration(NamedTuple):
    """One numbered step, its name, and the statements it runs."""

    version: int
    name: str
    statements: tuple[str, ...]

    def digest(self) -> str:
        """A stable hash of everything this migration does."""
        return text_digest(self.statements)


def text_digest(statements: tuple[str, ...]) -> str:
    """Hash a migration's statements, ignoring the whitespace around them."""
    joined = "\n".join(s.strip() for s in statements)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _ensure_ledger(db: Database) -> None:
    db.execute(_LEDGER)


def applied_versions(db: Database) -> dict[int, str]:
    """Every applied version mapped to the digest it was applied with."""
    _ensure_ledger(db)
    rows = db.query("SELECT version, digest FROM applied_migration ORDER BY version")
    return {int(r["version"]): str(r["digest"]) for r in rows}


def pending(db: Database, steps: tuple[Migration, ...]) -> tuple[Migration, ...]:
    """The steps that have not run yet, in order.

    Raises if a step that already ran no longer matches what it ran as.
    """
    seen = applied_versions(db)
    out: list[Migration] = []
    for step in steps:
        if step.version not in seen:
            out.append(step)
            continue
        if seen[step.version] != step.digest():
            raise Refused(
                f"migration {step.version:04d} {step.name}",
                "it has already been applied and its text has changed since",
            )
    return tuple(out)


def migrate(db: Database, steps: tuple[Migration, ...], *, applied_at: str) -> tuple[int, ...]:
    """Run every pending step in one transaction and return what ran."""
    todo = pending(db, steps)
    if not todo:
        return ()
    with db.tx():
        for step in todo:
            for statement in step.statements:
                db.execute(statement)
            db.execute(
                "INSERT INTO applied_migration (version, name, digest, applied_at)"
                " VALUES (?, ?, ?, ?)",
                (step.version, step.name, step.digest(), applied_at),
            )
    return tuple(s.version for s in todo)
