"""Every module and every public definition says what it is for.

Not a style rule. A package where half the functions carry a docstring and half
do not is one where a reader cannot tell whether the missing ones are obvious or
merely undocumented, and the answer is usually the second one.

Private helpers, `__post_init__` and the dunder methods are exempt: the name
already says it, and requiring a docstring there produces "Initialise the
instance." forty times, which is worse than nothing.
"""

from __future__ import annotations

import ast
import sys

from legvise.tools.walk import SourceFile, report, source_files, suite_files

__all__ = ["main", "problems"]

EXEMPT_NAMES = frozenset({"__post_init__", "__str__", "__repr__", "__eq__", "__hash__"})


def _needs_docstring(node: ast.AST) -> bool:
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return False
    if node.name in EXEMPT_NAMES:
        return False
    return not node.name.startswith("_")


def _module_problems(source: SourceFile) -> list[str]:
    found: list[str] = []
    if source.docstring() is None and not source.is_package_init:
        found.append(f"{source.module} has no module docstring")
    for node in source.definitions():
        if _needs_docstring(node) and ast.get_docstring(node) is None:
            found.append(f"{source.module}.{node.name} has no docstring")
    return found


def problems() -> list[str]:
    """Every definition that should carry a docstring and does not."""
    found: list[str] = []
    for source in source_files():
        found.extend(_module_problems(source))
    for source in suite_files():
        if source.docstring() is None and not source.is_package_init:
            found.append(f"{source.module} has no module docstring")
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_docstrings", problems())


if __name__ == "__main__":
    sys.exit(main())
