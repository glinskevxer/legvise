"""A migration that has shipped is frozen, and the lock file is the proof.

`store.migrations` already refuses to run a step whose text has changed since it
was applied. That protects a database that has already seen the step. It does
nothing for the developer who edits migration four on a laptop where the schema
was built this morning, sees green tests, and ships a change that will refuse to
apply on every machine that has been running for a week.

So the digests live in `migrations.lock`, in the repository, and this check
compares the code against the file. Adding a step appends a line; editing a
shipped one fails, loudly, on the machine where it was edited.

Run with `--write` to record new steps. There is no flag that rewrites an
existing line, because that is the thing being prevented.
"""

from __future__ import annotations

import sys

from legvise.store.schema import MIGRATIONS
from legvise.tools.walk import repo_root, report

__all__ = ["LOCK_NAME", "current_lines", "main", "problems", "read_lock"]

LOCK_NAME = "migrations.lock"
HEADER = (
    "# Digest of every migration that has shipped. Append only.",
    "# Edit a line here and check_migrations will tell you why not.",
)


def current_lines() -> tuple[str, ...]:
    """What the lock file should say, given the code."""
    return tuple(f"{step.version:04d} {step.digest()} {step.name}" for step in MIGRATIONS)


def read_lock() -> tuple[str, ...]:
    """What the lock file does say, comments and blanks dropped."""
    path = repo_root() / LOCK_NAME
    if not path.exists():
        return ()
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def write_lock() -> int:
    """Write the lock file from the code and report how many steps it holds."""
    path = repo_root() / LOCK_NAME
    body = "\n".join([*HEADER, *current_lines()])
    path.write_text(body + "\n", encoding="utf-8", newline="\n")
    return len(MIGRATIONS)


def problems() -> list[str]:
    """Every step whose digest has moved, and every step nobody locked."""
    locked = {line.split(" ", 1)[0]: line for line in read_lock()}
    found: list[str] = []
    for line in current_lines():
        version = line.split(" ", 1)[0]
        if version not in locked:
            found.append(f"migration {version} is not in {LOCK_NAME}; run with --write")
        elif locked[version] != line:
            found.append(
                f"migration {version} has changed since it shipped:"
                f" locked {locked[version]!r}, code {line!r}"
            )
    for version in sorted(set(locked) - {line.split(" ", 1)[0] for line in current_lines()}):
        found.append(f"{LOCK_NAME} holds migration {version} the code no longer has")
    return found


def main(argv: tuple[str, ...] = ()) -> int:
    """Run the check, or rewrite the lock file when asked."""
    args = argv or tuple(sys.argv[1:])
    if "--write" in args:
        count = write_lock()
        print(f"check_migrations: wrote {count} steps to {LOCK_NAME}")
        return 0
    return report("check_migrations", problems())


if __name__ == "__main__":
    sys.exit(main())
