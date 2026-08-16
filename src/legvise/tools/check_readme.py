"""The README describes the program that exists.

A README goes stale in exactly two ways and both are mechanical. A command is
renamed and the README still shows the old one, which sends a new operator down
a path that errors. Or a command is added and the README never learns about it,
which is quieter and worse, because the feature is there and nobody uses it.

So the command tree in the README is compared against the real tree. Every
`legvise ...` line in a fenced block has to name a command that exists, and every
group has to be mentioned somewhere.

What is deliberately not checked is the prose. A README that has to be generated
is a README nobody reads.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final

from legvise.tools.check_cli import command_paths, registered_groups, value_options
from legvise.tools.walk import repo_root, report

__all__ = ["README_NAME", "cited_commands", "main", "problems", "readme_text"]

README_NAME = "README.md"
_FENCE: Final = re.compile(r"```.*?```", re.DOTALL)
_INVOCATION: Final = re.compile(r"^\s*(?:\$\s*)?legvise\s+(.*)$", re.MULTILINE)
_OPTION_START: Final = "-"


def readme_text() -> str:
    """The whole README."""
    return (repo_root() / README_NAME).read_text(encoding="utf-8")


def _fenced_blocks(text: str) -> list[str]:
    return _FENCE.findall(text)


def _command_of(tail: str) -> str | None:
    words = _without_options(tail.split())
    if not words:
        return None
    if words[0] in {"--help", "--version"}:
        return None
    if len(words) == 1:
        return words[0]
    return f"{words[0]} {words[1]}"


def _without_options(words: list[str]) -> list[str]:
    """The words that name a command, with the options and their values dropped.

    An option's value is a bare word and reads exactly like a command name, so
    dropping only the words that start with a dash left `--config legvise.toml`
    looking like a command called `legvise.toml`. Which options take a value is
    a question for the tree, not for the text: `--quiet db verify` is a flag and
    two words, and eating the word after it loses the command.

    A value written as `--x=y` is one word and needs no such handling.
    """
    takes_value = value_options()
    kept: list[str] = []
    skip = False
    for word in words:
        if skip:
            skip = False
            continue
        if word.startswith(_OPTION_START):
            skip = word in takes_value
            continue
        kept.append(word)
    return kept


def cited_commands() -> tuple[str, ...]:
    """Every command the README shows in a fenced block, in order and once each."""
    found: list[str] = []
    for block in _fenced_blocks(readme_text()):
        for tail in _INVOCATION.findall(block):
            command = _command_of(tail)
            if command is not None and command not in found:
                found.append(command)
    return tuple(found)


def unknown() -> tuple[str, ...]:
    """Commands the README shows that the tree does not have."""
    known = set(command_paths()) | set(registered_groups())
    return tuple(command for command in cited_commands() if command not in known)


def unmentioned_groups() -> tuple[str, ...]:
    """Groups the README never names."""
    text = readme_text()
    return tuple(group for group in registered_groups() if f"legvise {group}" not in text)


def problems() -> list[str]:
    """Every command the README invents, and every group it forgets."""
    path = repo_root() / README_NAME
    if not path.exists():
        return [f"{README_NAME} is missing"]
    found = [
        f"{README_NAME} shows `legvise {command}`, which does not exist" for command in unknown()
    ]
    found.extend(
        f"{README_NAME} never mentions the {group} group" for group in unmentioned_groups()
    )
    return found


def target() -> Path:
    """Where the README lives."""
    return repo_root() / README_NAME


def main() -> int:
    """Run the check and report."""
    return report("check_readme", problems())


if __name__ == "__main__":
    sys.exit(main())
