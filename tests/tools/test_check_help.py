"""Every line of `--help` reads like a sentence somebody wrote."""

from __future__ import annotations

import pytest

from legvise.tools.check_cli import command_paths
from legvise.tools.check_help import (
    ECHO_LIMIT,
    LEAST_WORDS,
    problems,
    summaries,
)


def test_every_help_line_reads_as_a_sentence() -> None:
    assert problems() == []


def test_every_command_in_the_tree_has_a_summary() -> None:
    found = summaries()
    for path in command_paths():
        assert found.get(path), path


def test_every_summary_starts_with_a_capital() -> None:
    for path, text in summaries().items():
        assert text[0].isupper(), path


def test_every_summary_ends_with_a_full_stop() -> None:
    for path, text in summaries().items():
        assert text.endswith("."), path


def test_every_summary_is_a_clause_rather_than_a_label() -> None:
    for path, text in summaries().items():
        assert len(text.split()) >= LEAST_WORDS, path


def test_no_short_summary_simply_repeats_its_command_name() -> None:
    for path, text in summaries().items():
        words = {word.strip(".,").lower() for word in text.split()}
        if len(words) > ECHO_LIMIT:
            continue
        name = path.split()[-1].replace("-", " ").split()
        assert not all(part.lower() in words for part in name), path


def test_the_echo_rule_only_looks_at_short_summaries() -> None:
    assert ECHO_LIMIT >= 3


@pytest.mark.parametrize("path", ["venue", "scan run", "report desk", "plan rank"])
def test_a_named_command_carries_help_worth_reading(path: str) -> None:
    text = summaries()[path]
    assert len(text.split()) >= LEAST_WORDS
