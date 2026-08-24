"""One command that runs every check and says whether the tree can ship.

CI runs the checks as separate steps so a failure names itself in the job list.
A person about to cut a release wants the opposite: one command, one answer, and
the whole list of what is wrong rather than the first thing that broke.

So this imports each check and calls it, which is the same code CI runs and not
a second copy of the list. A check added to `legvise.tools` and forgotten here
is caught by `test_every_check_is_in_the_release_gate`, which walks the package
rather than trusting this file.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Final

from legvise.tools import (
    build_architecture,
    build_commands,
    build_glossary,
    build_operations,
    build_rules,
    check_changelog,
    check_cli,
    check_docstrings,
    check_errors,
    check_gate,
    check_help,
    check_indexes,
    check_layers,
    check_markers,
    check_migrations,
    check_naming,
    check_package,
    check_readme,
    check_rules,
    check_sql,
    check_tests,
    check_wiring,
    schema_dump,
    smoke,
)

__all__ = ["GATES", "GENERATED", "failures", "main"]

Gate = Callable[[], list[str]]

GATES: Final[tuple[tuple[str, Gate], ...]] = (
    ("check_docstrings", check_docstrings.problems),
    ("check_layers", check_layers.problems),
    ("check_wiring", check_wiring.problems),
    ("check_tests", check_tests.problems),
    ("check_cli", check_cli.problems),
    ("check_help", check_help.problems),
    ("check_sql", check_sql.problems),
    ("check_indexes", check_indexes.problems),
    ("check_migrations", check_migrations.problems),
    ("check_markers", check_markers.problems),
    ("check_naming", check_naming.problems),
    ("check_rules", check_rules.problems),
    ("check_errors", check_errors.problems),
    ("check_gate", check_gate.problems),
    ("check_package", check_package.problems),
    ("check_readme", check_readme.problems),
    ("check_changelog", check_changelog.problems),
)

GENERATED: Final[tuple[tuple[str, Callable[[], bool]], ...]] = (
    ("schema_dump", schema_dump.is_current),
    ("build_rules", build_rules.is_current),
    ("build_glossary", build_glossary.is_current),
    ("build_architecture", build_architecture.is_current),
    ("build_commands", build_commands.is_current),
    ("build_operations", build_operations.is_current),
)


def failures() -> dict[str, list[str]]:
    """Every gate that has something to say, keyed by name."""
    found: dict[str, list[str]] = {}
    for name, gate in GATES:
        problems = gate()
        if problems:
            found[name] = problems
    for name, is_current in GENERATED:
        if not is_current():
            found[name] = [f"{name} output is stale; regenerate it"]
    if smoke.main(("--quiet",)) != 0:
        found["smoke"] = ["the end to end run did not come back clean"]
    return found


def main(argv: tuple[str, ...] = ()) -> int:
    """Run every gate and print a verdict."""
    args = argv or tuple(sys.argv[1:])
    verbose = "--verbose" in args
    found = failures()
    total = 0
    for name in sorted(found):
        problems = found[name]
        total += len(problems)
        print(f"release_check: {name} has {len(problems)} problem(s)")
        if verbose:
            for problem in problems:
                print(f"    {problem}")
    if total:
        print(f"release_check: {total} problem(s) across {len(found)} gate(s)")
        return 1
    print(f"release_check: {len(GATES) + len(GENERATED) + 1} gates clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
