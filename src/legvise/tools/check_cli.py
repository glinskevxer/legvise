"""The command tree is complete, typed and documented.

Three things go wrong with a click tree and none of them is caught by the type
checker or the test suite:

- a group is written and never registered, so it exists, imports, has tests, and
  cannot be reached from `legvise --help`
- a command has no help text, so `--help` lists it as a blank line
- an option has no help text, which is the same problem one level down

This walks the real tree rather than the source, because the source is where a
group is defined and the tree is where it is reachable, and only the second one
is what a user sees.
"""

from __future__ import annotations

import sys

import click

from legvise.cli.main import cli
from legvise.tools.walk import package_root, report

__all__ = ["command_paths", "main", "problems", "registered_groups"]

EXEMPT_MODULES = frozenset({"main", "options", "parsers"})


def registered_groups() -> tuple[str, ...]:
    """Every group name hanging off the root, in order."""
    return tuple(sorted(cli.commands))


def _cli_modules() -> tuple[str, ...]:
    folder = package_root() / "cli"
    return tuple(
        sorted(
            path.stem
            for path in folder.glob("*.py")
            if path.stem not in EXEMPT_MODULES and not path.stem.startswith("__")
        )
    )


def command_paths() -> tuple[str, ...]:
    """Every `group command` pair the tree exposes, in order."""
    found: list[str] = []
    for name, group in sorted(cli.commands.items()):
        if isinstance(group, click.Group):
            found.extend(f"{name} {child}" for child in sorted(group.commands))
        else:
            found.append(name)
    return tuple(found)


def _walk_commands() -> list[tuple[str, click.Command]]:
    found: list[tuple[str, click.Command]] = []
    for name, group in sorted(cli.commands.items()):
        found.append((name, group))
        if isinstance(group, click.Group):
            found.extend((f"{name} {child}", cmd) for child, cmd in sorted(group.commands.items()))
    return found


def problems() -> list[str]:
    """Unregistered modules, and commands or options with nothing to say."""
    found: list[str] = []
    registered = set(registered_groups())
    for module in _cli_modules():
        if module not in registered:
            found.append(f"legvise.cli.{module} is not registered on the root group")
    for path, command in _walk_commands():
        if not (command.help or command.short_help):
            found.append(f"{path} has no help text")
        for param in command.params:
            if isinstance(param, click.Option) and not param.help:
                found.append(f"{path} option {param.name} has no help text")
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_cli", problems())


if __name__ == "__main__":
    sys.exit(main())
