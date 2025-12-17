"""The rule book and the code agree, in both directions.

Two ways for a rule book to rot, and they look nothing alike.

A clause nobody raises is a rule the desk believes it enforces and does not.
That is the dangerous one: an operator reads BAND.01 in the rule book, assumes
the floor is a wall, and finds out otherwise.

A `refuse` call naming a clause that is not in the book raises a `BadArgument`
about the lookup instead of the refusal it meant, at the worst moment. The
runtime already catches that; this catches it before it ships.

Both directions are checked here, from the source rather than by importing,
because a clause raised inside a branch nothing has exercised still counts as
used, and coverage would not agree.
"""

from __future__ import annotations

import ast
import sys

from legvise.rules import clause_codes, clauses_for_stage, stages
from legvise.tools.walk import report, source_files

__all__ = ["main", "problems", "raised_codes", "unraised", "unknown_codes"]

EXEMPT_MODULES = ("legvise.tools",)


def _refuse_calls() -> list[tuple[str, str]]:
    """Every `refuse("CODE", ...)` in the package, as (module, code)."""
    found: list[tuple[str, str]] = []
    for source in source_files():
        if source.module.startswith(EXEMPT_MODULES):
            continue
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name != "refuse" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.append((source.module, first.value))
    return found


def raised_codes() -> tuple[str, ...]:
    """Every clause code the package actually raises, in order."""
    return tuple(sorted({code for _, code in _refuse_calls()}))


def unraised() -> tuple[str, ...]:
    """Clauses in the book that nothing raises."""
    return tuple(code for code in clause_codes() if code not in set(raised_codes()))


def unknown_codes() -> tuple[tuple[str, str], ...]:
    """Refusals naming a code the book does not have."""
    known = set(clause_codes())
    return tuple(sorted((module, code) for module, code in _refuse_calls() if code not in known))


def problems() -> list[str]:
    """Every clause nobody raises, and every refusal nobody wrote a clause for."""
    found = [f"{code} is in the rule book and nothing raises it" for code in unraised()]
    found.extend(
        f"{module} refuses on {code}, which is not in the rule book"
        for module, code in unknown_codes()
    )
    for stage in stages():
        owned = clauses_for_stage(stage)
        numbers = sorted(int(item.code.split(".")[1]) for item in owned)
        if numbers != list(range(1, len(numbers) + 1)):
            found.append(f"stage {stage} numbers its clauses {numbers}, which has a gap")
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_rules", problems())


if __name__ == "__main__":
    sys.exit(main())
