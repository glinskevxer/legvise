"""The changelog has an entry for the version the code says it is.

A changelog that lags the version is worse than none: a reader takes the top
entry as current and it describes the release before this one. So the check is
narrow and mechanical. The top entry's version has to match `__version__`, the
versions have to descend, and every one of them has to parse.

What is deliberately not checked is whether the entry is any good. A changelog
generated from commit subjects is a list of commit subjects, and nobody reads
one of those twice.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

from legvise import __version__
from legvise.tools.walk import repo_root, report

__all__ = ["CHANGELOG_NAME", "Entry", "entries", "main", "problems"]

CHANGELOG_NAME = "CHANGELOG.md"
_HEADING: Final = re.compile(r"^##\s+(\d+)\.(\d+)\.(\d+)\s*(?:-\s*(.*))?$")


class Entry(NamedTuple):
    """One released version and the date beside it."""

    version: str
    parts: tuple[int, int, int]
    note: str

    @property
    def is_dated(self) -> bool:
        """True when the heading carries something after the version."""
        return bool(self.note.strip())


def target() -> Path:
    """Where the changelog lives."""
    return repo_root() / CHANGELOG_NAME


def entries() -> tuple[Entry, ...]:
    """Every version heading, in the order the file lists them."""
    path = target()
    if not path.exists():
        return ()
    found: list[Entry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _HEADING.match(line.strip())
        if match:
            major, minor, patch, note = match.groups()
            found.append(
                Entry(
                    version=f"{major}.{minor}.{patch}",
                    parts=(int(major), int(minor), int(patch)),
                    note=note or "",
                )
            )
    return tuple(found)


def body_of(version: str) -> tuple[str, ...]:
    """The lines under one version's heading, blanks dropped."""
    path = target()
    if not path.exists():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    collecting = False
    found: list[str] = []
    for line in lines:
        match = _HEADING.match(line.strip())
        if match:
            if collecting:
                break
            collecting = f"{match.group(1)}.{match.group(2)}.{match.group(3)}" == version
            continue
        if collecting and line.strip():
            found.append(line.rstrip())
    return tuple(found)


def problems() -> list[str]:
    """Every way the changelog and the code disagree."""
    if not target().exists():
        return [f"{CHANGELOG_NAME} is missing"]
    found: list[str] = []
    listed = entries()
    if not listed:
        return [f"{CHANGELOG_NAME} has no version headings"]
    if listed[0].version != __version__:
        found.append(
            f"{CHANGELOG_NAME} tops out at {listed[0].version}, the code says {__version__}"
        )
    versions = [entry.parts for entry in listed]
    if versions != sorted(versions, reverse=True):
        found.append(f"{CHANGELOG_NAME} lists its versions out of order")
    if len(versions) != len(set(versions)):
        found.append(f"{CHANGELOG_NAME} lists a version twice")
    for entry in listed:
        if not entry.is_dated:
            found.append(f"{CHANGELOG_NAME} entry {entry.version} has no date")
        if not body_of(entry.version):
            found.append(f"{CHANGELOG_NAME} entry {entry.version} says nothing")
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_changelog", problems())


if __name__ == "__main__":
    sys.exit(main())
