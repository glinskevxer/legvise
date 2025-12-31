"""Errors are raised the desk's way, and nothing else escapes the package.

Two rules about how failure leaves this codebase.

**Every raise is a package error.** A bare `ValueError` from inside the pricing
path reaches the CLI as a traceback rather than as a message, because the
translation in `DeskGroup` only catches `LegviseError`. The exceptions to that
are `click` errors, which the CLI raises on purpose, and `AssertionError`, which
means a bug rather than a refusal.

**Every `raise` in the domain carries a reason.** `NotFound("venue")` with no key
and `BadArgument(field, value)` with no `why` are refusals a reader has to go
looking for the cause of, and the whole point of the error types is that they
carry their parts.

The check reads the source, so a raise on a branch nothing has exercised counts
the same as one on the happy path.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from legvise.tools.walk import report, source_files

__all__ = [
    "ALLOWED_BUILTINS",
    "ALLOWED_FACTORIES",
    "ARITY",
    "main",
    "problems",
    "raises_in",
]

ALLOWED_BUILTINS: Final = frozenset({"AssertionError", "NotImplementedError", "StopIteration"})

# `refuse` returns a `Refused` for the caller to raise, so `raise refuse(...)` is
# the package idiom rather than an exception type. `SystemExit` is the console
# script handing an exit code back to the shell.
ALLOWED_FACTORIES: Final = frozenset({"refuse", "SystemExit"})

PACKAGE_ERRORS: Final = frozenset(
    {"LegviseError", "NotFound", "Conflict", "BadArgument", "Refused", "StaleData"}
)

# How many positional arguments each package error needs to be readable.
ARITY: Final = {
    "NotFound": 2,
    "Conflict": 2,
    "BadArgument": 3,
    "Refused": 2,
    "StaleData": 3,
    "LegviseError": 1,
}

CLI_PREFIX: Final = "legvise.cli"


def _raised_name(node: ast.Raise) -> tuple[str, int] | None:
    if node.exc is None:
        return None
    target = node.exc
    if isinstance(target, ast.Call):
        return (_callable_name(target.func), len(target.args))
    if isinstance(target, ast.Name):
        return (target.id, -1)
    if isinstance(target, ast.Attribute):
        return (target.attr, -1)
    return None


def _callable_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return "?"


def raises_in(module_prefix: str = "legvise") -> list[tuple[str, str, int]]:
    """Every raise in the package, as (module, name, positional argument count)."""
    found: list[tuple[str, str, int]] = []
    for source in source_files():
        if not source.module.startswith(module_prefix):
            continue
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Raise):
                named = _raised_name(node)
                if named is not None:
                    found.append((source.module, named[0], named[1]))
    return found


def _is_click(name: str) -> bool:
    return name.startswith(("Usage", "Bad", "Click", "Abort", "Exit")) and name not in ARITY


def problems() -> list[str]:
    """Every stray exception type, and every package error raised bare."""
    found: list[str] = []
    for module, name, arity in raises_in():
        if module.startswith("legvise.tools"):
            continue
        if name in PACKAGE_ERRORS:
            wanted = ARITY[name]
            if 0 <= arity < wanted:
                found.append(f"{module} raises {name} with {arity} of {wanted} parts")
            continue
        if name in ALLOWED_BUILTINS or name in ALLOWED_FACTORIES:
            continue
        if module.startswith(CLI_PREFIX) and _is_click(name):
            continue
        found.append(f"{module} raises {name}, which is not one of the package errors")
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_errors", problems())


if __name__ == "__main__":
    sys.exit(main())
