"""SQL is written out in full, parameterised, and lives only in the store.

Three rules, and each one is here because breaking it is cheap and finding out
later is not.

**No `SELECT *`.** A star means the row a repository reads depends on the order
the columns were added to the table, which makes adding a column a change to
every read path. Every query names its columns.

**No value interpolated into a statement.** A statement may be built from a
module level constant -- the column lists are, and that is fine because they are
written by the same file and nothing from outside can reach them -- but anything
else goes in as a placeholder. The constants are found by reading the module
rather than listed here. They were listed here once, all eleven of them, which
made adding a column list to the store a change in two files and meant the check
went quiet for anyone who only made the first one.

**SQL only in `legvise.store`.** A `SELECT` in a CLI module is a repository
somebody did not write, and it will not be the one the tests cover.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import Final

from legvise.tools.walk import SourceFile, report, source_files

__all__ = ["main", "module_constants", "problems", "statements_in"]

# Case sensitive on purpose. Every statement in this package spells its keywords
# in upper case, and matching case-insensitively turns the word "select" in an
# error message into a SQL statement.
_SQL: Final = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|CREATE\s+INDEX)\b"
)
_STAR: Final = re.compile(r"SELECT\s+\*")

# Fragments a repository chooses between two literals, never values. These
# are locals rather than constants, so reading the module cannot find them.
ALLOWED_INTERPOLATIONS: Final = frozenset({"where", "join", "name"})

SQL_LAYERS: Final = ("legvise.store",)

# The checks themselves are exempt from all three rules. This module quotes SQL
# in the messages it prints, and a check that fails on its own error text is a
# check nobody keeps.
EXEMPT_MODULES: Final = ("legvise.tools",)


def _is_sql(text: str) -> bool:
    return bool(_SQL.search(text))


def statements_in(source: SourceFile) -> tuple[str, ...]:
    """Every string literal in a module that looks like SQL."""
    return tuple(text for text in source.code_strings() if _is_sql(text))


def module_constants(source: SourceFile) -> frozenset[str]:
    """Every module level name bound to a literal, or to other such names.

    Read in source order, so a constant assembled from the ones above it counts
    as one too. A name bound to anything else -- a call, an argument, a value
    read at import time -- is not a constant and does not get in.
    """
    found: set[str] = set()
    for node in source.tree.body:
        target = _assigned_name(node)
        value = getattr(node, "value", None)
        if target and value is not None and _is_static(value, found):
            found.add(target)
    return frozenset(found)


def _assigned_name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        first = node.targets[0]
        return first.id if isinstance(first, ast.Name) else None
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _is_static(node: ast.expr, known: set[str]) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.JoinedStr):
        return all(_is_static_part(part, known) for part in node.values)
    return False


def _is_static_part(part: ast.expr, known: set[str]) -> bool:
    if isinstance(part, ast.Constant):
        return True
    return isinstance(part, ast.FormattedValue) and _name_of(part.value) in known


def _interpolated_names(source: SourceFile) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        literal = "".join(part.value for part in node.values if isinstance(part, ast.Constant))
        if not _is_sql(literal):
            continue
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                found.append((literal, _name_of(part.value)))
    return found


def _name_of(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    return ast.dump(node)[:40]


def problems() -> list[str]:
    """Every star, every interpolated value, and every stray statement."""
    found: list[str] = []
    for source in source_files():
        if source.module.startswith(EXEMPT_MODULES):
            continue
        statements = statements_in(source)
        if statements and not source.module.startswith(SQL_LAYERS):
            found.append(f"{source.module} holds SQL outside the store layer")
        for statement in statements:
            if _STAR.search(statement):
                found.append(f"{source.module} uses SELECT * in {_first_words(statement)}")
        allowed = ALLOWED_INTERPOLATIONS | module_constants(source)
        for statement, name in _interpolated_names(source):
            if name not in allowed:
                found.append(f"{source.module} interpolates {name} into {_first_words(statement)}")
    return found


def _first_words(statement: str, count: int = 6) -> str:
    return " ".join(statement.split()[:count])


def main() -> int:
    """Run the check and report."""
    return report("check_sql", problems())


if __name__ == "__main__":
    sys.exit(main())
