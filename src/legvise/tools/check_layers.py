"""Imports point down the layers, never up.

The layering is not decoration. `model` knowing nothing about `store` is what
lets a record be built and validated in a test with no database; `market`
knowing nothing about `cli` is what lets the pricing path be exercised without
click. Every one of those properties is worth something, and every one of them
is lost the first time an import goes the wrong way, quietly, in a hurry.

So the direction is written down here and checked. The layers, lowest first:

    base    errors, money, ids, clock, rows, rules
    model   the records
    store   persistence
    domain  market, fees, risk, routing
    scan    scan, ledger
    report  report
    cli     the command tree
    tools   these checks

A module may import from its own layer or any lower one. `tools` may import
anything, because a check has to be able to read what it checks.
"""

from __future__ import annotations

import sys
from typing import Final

from legvise.tools.walk import report, source_files

__all__ = ["LAYERS", "layer_of", "main", "problems"]

LAYERS: Final = (
    ("base", ("errors", "money", "ids", "clock", "rows", "rules", "settings")),
    ("model", ("model",)),
    ("store", ("store",)),
    ("domain", ("market", "fees", "risk", "routing")),
    ("scan", ("scan", "ledger")),
    ("report", ("report",)),
    ("cli", ("cli",)),
    ("tools", ("tools",)),
)

_RANK: Final = {name: index for index, (name, _) in enumerate(LAYERS)}
_BY_PART: Final = {part: name for name, parts in LAYERS for part in parts}


def layer_of(module: str) -> str | None:
    """Which layer a module belongs to, or nothing for the package root."""
    parts = module.split(".")
    if len(parts) < 2:
        return None
    return _BY_PART.get(parts[1])


def problems() -> list[str]:
    """Every import that points up the layers."""
    found: list[str] = []
    for source in source_files():
        here = layer_of(source.module)
        if here is None or here == "tools":
            continue
        for imported in source.imports():
            there = layer_of(imported)
            if there is None:
                continue
            if _RANK[there] > _RANK[here]:
                found.append(
                    f"{source.module} ({here}) imports {imported} ({there}), which is higher"
                )
    return found


def summary() -> dict[str, int]:
    """How many modules sit in each layer."""
    counts = {name: 0 for name, _ in LAYERS}
    for source in source_files():
        here = layer_of(source.module)
        if here is not None:
            counts[here] += 1
    return counts


def main() -> int:
    """Run the check and report."""
    return report("check_layers", problems())


if __name__ == "__main__":
    sys.exit(main())
