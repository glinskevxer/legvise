"""Every module has a test module, and every test module has a module.

The first half is the obvious one. The second half is the one that catches
something: a test module left behind after the code it covered was renamed
keeps passing, keeps being counted, and covers nothing.

This is a coverage check in the crude sense of "did anybody write a file about
this", which is a different question from line coverage and worth asking
separately. A module can be at ninety percent line coverage because something
else exercises it in passing and still have nobody who thought about it.
"""

from __future__ import annotations

import sys

from legvise.tools.walk import report, source_files, suite_files

__all__ = ["expected_test_module", "main", "problems", "untested"]

EXEMPT = frozenset(
    {
        "legvise",
        "legvise.cli.main",
        "legvise.tools.check_docstrings",
        "legvise.tools.check_layers",
        "legvise.tools.check_tests",
        "legvise.tools.check_wiring",
    }
)


def expected_test_module(module: str) -> str:
    """Where the test module for a package module should live."""
    parts = module.split(".")[1:]
    if not parts:
        return "tests.test_package"
    leaf = f"test_{parts[-1]}"
    return ".".join(["tests", *parts[:-1], leaf])


def _covered() -> set[str]:
    return {source.module for source in suite_files()}


def untested() -> tuple[str, ...]:
    """Modules with no test module named after them."""
    covered = _covered()
    out: list[str] = []
    for source in source_files():
        if source.is_package_init or source.module in EXEMPT:
            continue
        expected = expected_test_module(source.module)
        if expected not in covered and f"{expected}_cli" not in covered:
            out.append(source.module)
    return tuple(sorted(out))


def stranded() -> tuple[str, ...]:
    """Test modules with no package module they could be testing."""
    modules = {source.module for source in source_files()}
    wanted = {expected_test_module(module) for module in modules}
    wanted |= {f"{name}_cli" for name in wanted}
    out = [
        source.module
        for source in suite_files()
        if not source.is_package_init
        and source.module.rsplit(".", 1)[-1].startswith("test_")
        and source.module not in wanted
    ]
    return tuple(sorted(out))


def problems() -> list[str]:
    """One line per module with no test, and per test with no module."""
    found = [f"{module} has no test module" for module in untested()]
    found.extend(f"{module} tests nothing that exists" for module in stranded())
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_tests", problems())


if __name__ == "__main__":
    sys.exit(main())
