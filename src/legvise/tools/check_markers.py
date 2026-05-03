"""No unfinished work is left in the tree, and no test is quietly switched off.

Two things that are fine on a branch and not fine on `main`.

A `TODO` is a note to somebody who is not going to read it. Either the work is
worth doing, in which case it belongs in the tracker, or it is not, in which case
the comment is a lie that gets read as a plan for years.

A skipped test is worse, because it is counted. `pytest.mark.skip` and
`xfail` both report as passes at the summary line, so a suite with four of them
says "2306 passed" and means "2302 passed and four nobody has looked at since
March".

The exception is `pragma: no cover`, which is a coverage instruction rather than
an unfinished thought, and is checked for by `check_docstrings`' cousin nowhere:
it is allowed and counted, so a tree that grows them can be seen doing it.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import Final

from legvise.tools.walk import SourceFile, report, source_files, suite_files

__all__ = ["MARKERS", "coverage_pragmas", "main", "problems", "skipped_tests"]

MARKERS: Final = ("TODO", "FIXME", "XXX", "HACK", "WIP")

_MARKER: Final = re.compile(r"\b(" + "|".join(MARKERS) + r")\b")
_PRAGMA: Final = re.compile(r"pragma:\s*no cover")

SKIP_DECORATORS: Final = frozenset({"skip", "skipif", "xfail"})

# This module names the markers it looks for, so it cannot look at itself.
EXEMPT: Final = ("legvise.tools.check_markers", "tests.tools.test_check_markers")


def _marker_lines(source: SourceFile) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(source.text.splitlines(), start=1):
        match = _MARKER.search(line)
        if match:
            found.append((number, match.group(1)))
    return found


def _skip_names(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        return _skip_names(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def skipped_tests() -> tuple[tuple[str, str, str], ...]:
    """Every test carrying a skip or xfail marker, as (module, name, marker)."""
    found: list[tuple[str, str, str]] = []
    for source in suite_files():
        if source.module in EXEMPT:
            continue
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                name = _skip_names(decorator)
                if name in SKIP_DECORATORS:
                    found.append((source.module, node.name, str(name)))
    return tuple(found)


def coverage_pragmas() -> tuple[tuple[str, int], ...]:
    """Every `pragma: no cover`, so a tree that grows them can be seen doing it."""
    found: list[tuple[str, int]] = []
    for source in source_files():
        for number, line in enumerate(source.text.splitlines(), start=1):
            if _PRAGMA.search(line):
                found.append((source.module, number))
    return tuple(found)


def problems() -> list[str]:
    """Every leftover marker, and every test nobody is running."""
    found: list[str] = []
    for source in (*source_files(), *suite_files()):
        if source.module in EXEMPT:
            continue
        for number, marker in _marker_lines(source):
            found.append(f"{source.module}:{number} still says {marker}")
    for module, name, marker in skipped_tests():
        found.append(f"{module}.{name} is marked {marker} and counts as a pass")
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_markers", problems())


if __name__ == "__main__":
    sys.exit(main())
