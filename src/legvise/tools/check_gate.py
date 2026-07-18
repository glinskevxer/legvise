"""What exists, what CI runs and what `check.sh` runs are the same three sets.

A check that exists and nothing runs is worse than no check. It passes whenever
somebody remembers to type it, which is never, and it rots without anyone
noticing because nothing ever goes red.

Three lists have to agree, and none of them is written down twice:

- every `check_*` module in `legvise.tools`
- every check the CI workflow invokes
- every gate `release_check` collects

`check.sh` finds the checks with a glob rather than listing them, which is the
right way for it to work, so it is compared by shape: the glob is still there
and the three outer tools still run. Its generator list is spelled out though,
and a spelled out list drifts, so that one is compared name by name.

`release_check` is imported inside the function rather than at the top of the
file. It imports this module, and a check that watches the gate has to be in
the gate like every other check, so the cycle is broken at the later end.

This is the check that watches the other checks. It exists because a
verification step which does not name exactly what runs is not a verification
step.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final

from legvise.tools.walk import package_root, repo_root, report

__all__ = ["ci_invocations", "gate_names", "generator_names", "main", "on_disk", "problems"]

WORKFLOW: Final = ".github/workflows/ci.yml"
GATE_SCRIPT: Final = "check.sh"
GLOB: Final = "src/legvise/tools/check_*.py"
OUTER: Final = ("ruff", "mypy", "pytest")
_INVOCATION: Final = re.compile(r"python -m legvise\.tools\.([a-z_]+)")


def on_disk() -> tuple[str, ...]:
    """Every check module that exists, in name order."""
    return tuple(sorted(path.stem for path in (package_root() / "tools").glob("check_*.py")))


def ci_invocations() -> tuple[str, ...]:
    """Every `legvise.tools` module the workflow invokes, in name order."""
    path = repo_root() / WORKFLOW
    if not path.exists():
        return ()
    return tuple(sorted(set(_INVOCATION.findall(path.read_text(encoding="utf-8")))))


def gate_names() -> tuple[str, ...]:
    """Every check the release gate collects, in name order."""
    from legvise.tools.release_check import GATES

    return tuple(sorted(name for name, _ in GATES))


def generator_names() -> tuple[str, ...]:
    """Every document generator the release gate checks, in name order."""
    from legvise.tools.release_check import GENERATED

    return tuple(sorted(name for name, _ in GENERATED))


def gate_script() -> Path:
    """Where the local gate script lives."""
    return repo_root() / GATE_SCRIPT


def _script_problems(text: str) -> list[str]:
    found: list[str] = []
    if GLOB not in text:
        found.append(f"{GATE_SCRIPT} no longer finds the checks with {GLOB}")
    for name in OUTER:
        if name not in text:
            found.append(f"{GATE_SCRIPT} no longer runs {name}")
    for name in generator_names():
        if name not in text:
            found.append(f"{GATE_SCRIPT} does not check {name} output")
    return found


def problems() -> list[str]:
    """Every check that is missing from one of the places that should run it."""
    found: list[str] = []
    existing = set(on_disk())
    in_ci = set(ci_invocations())
    in_gate = set(gate_names())

    found.extend(f"{name} exists and CI does not run it" for name in sorted(existing - in_ci))
    found.extend(
        f"{name} exists and release_check does not collect it"
        for name in sorted(existing - in_gate)
    )
    found.extend(
        f"CI runs {name}, which is not a module"
        for name in sorted(in_ci - existing)
        if name.startswith("check_")
    )
    found.extend(
        f"release_check collects {name}, which is not a module"
        for name in sorted(in_gate - existing)
    )
    for name in generator_names():
        if name not in in_ci:
            found.append(f"{name} is in the release gate and CI does not run it")

    script = gate_script()
    if not script.exists():
        found.append(f"{GATE_SCRIPT} is missing")
        return found
    found.extend(_script_problems(script.read_text(encoding="utf-8")))
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_gate", problems())


if __name__ == "__main__":
    sys.exit(main())
