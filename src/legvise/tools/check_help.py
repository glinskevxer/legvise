"""Every line of `--help` reads like a sentence somebody wrote.

`check_cli` refuses a command with no help at all. This is the next rung: help
that exists and says nothing. Four rules, and each one is a shape that shows up
the moment a tree gets big enough that nobody reads the whole `--help` again.

- a summary starts with a capital and ends with a full stop, so the help output
  reads as prose rather than as a column of fragments
- a summary is a clause, not a label: `List` is not help, `List the venues on
  file` is
- an option's help says the same, and ends the same way
- a short summary does not simply repeat its own command name back at the
  reader, because "venue add: Add venue" is the shape help takes when it is
  written to satisfy a checker rather than a person

The last one is the reason this file exists rather than a line in `check_cli`.
"""

from __future__ import annotations

import sys
from typing import Final

import click

from legvise.cli.main import cli
from legvise.tools.walk import report

__all__ = ["LEAST_WORDS", "main", "problems", "summaries"]

LEAST_WORDS: Final = 3
LEAST_OPTION_WORDS: Final = 3


def _summary(command: click.Command) -> str:
    text = command.help or command.short_help or ""
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def summaries() -> dict[str, str]:
    """The first line of every command's help, keyed by its path."""
    found: dict[str, str] = {}
    for name, group in sorted(cli.commands.items()):
        found[name] = _summary(group)
        if isinstance(group, click.Group):
            for child, command in sorted(group.commands.items()):
                found[f"{name} {child}"] = _summary(command)
    return found


def _sentence_problems(where: str, text: str, least: int) -> list[str]:
    found: list[str] = []
    if not text:
        return [f"{where} has nothing to say"]
    if not text[0].isupper():
        found.append(f"{where} starts lower case: {text!r}")
    if not text.endswith("."):
        found.append(f"{where} does not end in a full stop: {text!r}")
    if len(text.split()) < least:
        found.append(f"{where} is {len(text.split())} words, wanted {least}")
    return found


ECHO_LIMIT: Final = 4


def _echoes_its_own_name(path: str, text: str) -> bool:
    """True when a short summary is made of the command's own words.

    "Add venue" for `venue add` is the shape to catch. "List the plans in a
    session, best net edge first" also contains the command's name and is
    perfectly good help, so the length bound is doing the work here and the
    word test on its own would be a rule that convicted half the tree.
    """
    words = {word.strip(".,").lower() for word in text.split()}
    if len(words) > ECHO_LIMIT:
        return False
    name = path.split()[-1].replace("-", " ").split()
    return all(part.lower() in words for part in name)


def problems() -> list[str]:
    """Every help line that is a label rather than a sentence."""
    found: list[str] = []
    for path, text in summaries().items():
        found.extend(_sentence_problems(path, text, LEAST_WORDS))
        if text and _echoes_its_own_name(path, text):
            found.append(f"{path} repeats its own name back: {text!r}")
    for name, group in sorted(cli.commands.items()):
        commands = group.commands.items() if isinstance(group, click.Group) else ()
        for child, command in sorted(commands):
            for param in command.params:
                if isinstance(param, click.Option) and param.help:
                    found.extend(
                        _sentence_problems(
                            f"{name} {child} --{param.name}", param.help, LEAST_OPTION_WORDS
                        )
                    )
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_help", problems())


if __name__ == "__main__":
    sys.exit(main())
