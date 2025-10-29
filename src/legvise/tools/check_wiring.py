"""Every module is reachable from the command tree, and nothing is orphaned.

A module with green tests and no caller is a module that is tested and not used.
That is worse than untested code, because the test suite reports it as covered
and the coverage number says everything is fine. It happens most often after a
refactor moves the last real call site and nobody notices, and the module keeps
passing its own tests for months.

So the graph is walked from `legvise.cli.main` and anything it cannot reach is
reported. `tools` is exempt -- a check is entered from the command line, not
from the app -- and so is the package root.
"""

from __future__ import annotations

import sys
from collections import deque

from legvise.tools.walk import SourceFile, report, source_files

__all__ = ["ENTRY_POINTS", "main", "problems", "reachable"]

ENTRY_POINTS = ("legvise.cli.main",)
EXEMPT_PREFIXES = ("legvise.tools",)


def _graph() -> dict[str, SourceFile]:
    return {source.module: source for source in source_files()}


def reachable(entries: tuple[str, ...] = ENTRY_POINTS) -> set[str]:
    """Every module reachable by following imports from the entry points."""
    modules = _graph()
    seen: set[str] = set()
    queue: deque[str] = deque(entries)
    while queue:
        here = queue.popleft()
        if here in seen or here not in modules:
            continue
        seen.add(here)
        for imported in modules[here].imports():
            if imported not in seen:
                queue.append(imported)
    return seen


def _is_exempt(module: str) -> bool:
    if module == "legvise":
        return True
    return any(module.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def orphans() -> tuple[str, ...]:
    """Modules the command tree cannot reach, in order."""
    live = reachable()
    return tuple(
        sorted(
            source.module
            for source in source_files()
            if not source.is_package_init
            and not _is_exempt(source.module)
            and source.module not in live
        )
    )


def problems() -> list[str]:
    """One line per orphan."""
    return [f"{module} is not reachable from the command tree" for module in orphans()]


def main() -> int:
    """Run the check and report."""
    return report("check_wiring", problems())


if __name__ == "__main__":
    sys.exit(main())
