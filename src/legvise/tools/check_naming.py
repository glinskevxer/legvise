"""Test names are sentences about the desk, not labels on a function.

`test_venue` tells a reader nothing. `test_a_venue_that_is_not_there_names_it`
tells them what the code promises, and when it fails the name is the bug report.
That is worth enforcing mechanically, because the pressure while writing the
fortieth test of an afternoon is all in the other direction.

Three rules:

- at least `LEAST_WORDS` words after the `test_` prefix, so a name has to be a
  clause rather than a noun
- no word from `VAGUE`, because "works" and "correct" are the words a name
  reaches for when nobody has decided what the test is actually asserting
- no trailing number, because `test_sizing_2` means somebody copied
  `test_sizing` and did not think about what changed
"""

from __future__ import annotations

import ast
import re
import sys
from typing import Final

from legvise.tools.walk import report, suite_files

__all__ = ["LEAST_WORDS", "VAGUE", "main", "problems", "named_tests"]

LEAST_WORDS: Final = 5

VAGUE: Final = frozenset(
    {
        "basic",
        "correct",
        "correctly",
        "fine",
        "good",
        "ok",
        "okay",
        "properly",
        "simple",
        "stuff",
        "valid",
        "works",
    }
)

_TRAILING_NUMBER: Final = re.compile(r"_\d+$")


def named_tests() -> tuple[tuple[str, str], ...]:
    """Every test function in the suite, as (module, name).

    Not called `test_names`, for the same reason `walk.suite_files` is not
    called `test_files`: pytest collects anything starting with `test_` that a
    test module imports, and the failure it produces points nowhere useful.
    """
    found: list[tuple[str, str]] = []
    for source in suite_files():
        for node in ast.walk(source.tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.append((source.module, node.name))
    return tuple(found)


def _words(name: str) -> list[str]:
    return [word for word in name.removeprefix("test_").split("_") if word]


def problems() -> list[str]:
    """Every test name that is a label rather than a sentence."""
    found: list[str] = []
    for module, name in named_tests():
        words = _words(name)
        if len(words) < LEAST_WORDS:
            found.append(f"{module}.{name} is {len(words)} words, wanted {LEAST_WORDS}")
        vague = sorted(set(words) & VAGUE)
        if vague:
            found.append(f"{module}.{name} says {', '.join(vague)}, which says nothing")
        if _TRAILING_NUMBER.search(name):
            found.append(f"{module}.{name} ends in a number, so it was copied")
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_naming", problems())


if __name__ == "__main__":
    sys.exit(main())
