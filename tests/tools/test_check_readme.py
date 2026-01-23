"""The README describes the program that exists."""

from __future__ import annotations

from legvise.tools.check_cli import command_paths, registered_groups
from legvise.tools.check_readme import (
    README_NAME,
    cited_commands,
    problems,
    readme_text,
    target,
    unknown,
    unmentioned_groups,
)


def test_the_readme_describes_the_real_command_tree() -> None:
    assert problems() == []


def test_the_readme_is_in_the_repository_root() -> None:
    assert README_NAME == "README.md"
    assert target().exists()


def test_no_command_the_readme_shows_is_invented() -> None:
    assert unknown() == ()


def test_every_group_is_mentioned_somewhere() -> None:
    assert unmentioned_groups() == ()


def test_the_readme_shows_a_worthwhile_number_of_commands() -> None:
    assert len(cited_commands()) >= 20


def test_every_cited_command_is_in_the_tree() -> None:
    known = set(command_paths()) | set(registered_groups())
    for command in cited_commands():
        assert command in known


def test_the_readme_explains_the_edge_decomposition() -> None:
    text = readme_text()
    assert "net = gross - fees - slippage - rebalance" in text


def test_the_readme_names_the_two_kinds_of_opportunity() -> None:
    text = readme_text().lower()
    assert "cross venue" in text
    assert "triangular" in text


def test_the_readme_lists_every_check_the_repository_runs() -> None:
    text = readme_text()
    for check in (
        "check_layers",
        "check_wiring",
        "check_tests",
        "check_cli",
        "check_sql",
        "check_indexes",
        "check_migrations",
        "check_naming",
        "check_rules",
        "check_errors",
        "check_package",
        "check_readme",
    ):
        assert check in text


def test_the_readme_describes_every_subpackage() -> None:
    text = readme_text()
    for folder in ("model", "store", "market", "fees", "risk", "routing", "scan", "cli"):
        assert f"src/legvise/{folder}" in text


def test_the_readme_says_the_desk_is_prefunded() -> None:
    assert "prefunded" in readme_text().lower()


def test_the_readme_has_no_carriage_returns() -> None:
    assert b"\r" not in target().read_bytes()
