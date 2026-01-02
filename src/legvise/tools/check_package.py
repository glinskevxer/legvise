"""The packaging metadata says what the code says.

`pyproject.toml` is the file nobody reads after the first week, and it is the
file that decides whether the wheel a user installs works. Four things drift:

- the version in `pyproject.toml` against `legvise.__version__`
- the console script against the function it names
- every pinned dependency against `constraints.txt`
- the Python floor against what the code actually uses

The first three are compared here. The fourth is not checkable from the source
without a type checker's worth of work, so `requires-python` is compared against
a constant this file owns and CI runs on that version.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any, Final

from legvise import __version__
from legvise.tools.walk import repo_root, report

__all__ = ["PYTHON_FLOOR", "constraints", "main", "problems", "project"]

PYTHON_FLOOR: Final = ">=3.12"
ENTRY_POINT: Final = "legvise.cli.main:main"


def _pyproject() -> dict[str, Any]:
    path = repo_root() / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def project() -> dict[str, Any]:
    """The `[project]` table."""
    table = _pyproject().get("project", {})
    return dict(table)


def constraints() -> dict[str, str]:
    """Every pin in `constraints.txt`, normalised to lower case names."""
    path = repo_root() / "constraints.txt"
    found: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        found[name.strip().lower().replace("_", "-")] = version.strip()
    return found


def _requirements() -> list[str]:
    table = project()
    found = list(table.get("dependencies", []))
    for extra in table.get("optional-dependencies", {}).values():
        found.extend(extra)
    return found


def _split(requirement: str) -> tuple[str, str] | None:
    if "==" not in requirement:
        return None
    name, _, version = requirement.partition("==")
    return (name.strip().lower().replace("_", "-"), version.strip())


def problems() -> list[str]:
    """Every disagreement between the metadata and the code."""
    table = project()
    found: list[str] = []
    if table.get("version") != __version__:
        found.append(f"pyproject says version {table.get('version')}, code says {__version__}")
    if table.get("requires-python") != PYTHON_FLOOR:
        found.append(f"requires-python is {table.get('requires-python')}, wanted {PYTHON_FLOOR}")
    scripts = table.get("scripts", {})
    if scripts.get("legvise") != ENTRY_POINT:
        found.append(f"console script points at {scripts.get('legvise')}, wanted {ENTRY_POINT}")
    pins = constraints()
    for requirement in _requirements():
        split = _split(requirement)
        if split is None:
            found.append(f"{requirement} is not pinned with ==")
            continue
        name, version = split
        if name not in pins:
            found.append(f"{name} is a dependency and is not in constraints.txt")
        elif pins[name] != version:
            found.append(f"{name} is {version} in pyproject and {pins[name]} in constraints.txt")
    return found


def wheel_packages() -> list[str]:
    """What the wheel is told to include."""
    table = _pyproject().get("tool", {}).get("hatch", {}).get("build", {})
    return list(table.get("targets", {}).get("wheel", {}).get("packages", []))


def source_root() -> Path:
    """Where the package is expected to be on disk."""
    return repo_root() / "src" / "legvise"


def main() -> int:
    """Run the check and report."""
    return report("check_package", problems())


if __name__ == "__main__":
    sys.exit(main())
