"""The README describes the program that exists."""

from __future__ import annotations

from legvise.tools.check_cli import command_paths, registered_groups
from legvise.tools.check_readme import (
    README_NAME,
    _command_of,
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


# An option's value is a bare word and reads like a command name. Dropping only
# the dashed words left `--config legvise.toml` looking like a command.


def test_a_command_with_no_options_reads_as_itself() -> None:
    assert _command_of("scan run") == "scan run"


def test_a_group_on_its_own_reads_as_the_group() -> None:
    assert _command_of("scan") == "scan"


def test_an_option_after_the_command_is_dropped() -> None:
    assert _command_of("scan run --size 2") == "scan run"


def test_an_option_before_the_command_is_dropped_with_its_value() -> None:
    assert _command_of("--config legvise.toml config show") == "config show"


def test_an_option_written_with_an_equals_takes_no_second_word() -> None:
    assert _command_of("--config=legvise.toml config show") == "config show"


def test_a_flag_with_no_value_still_leaves_the_command() -> None:
    assert _command_of("--quiet db verify") == "db verify"


def test_an_argument_that_looks_like_a_file_is_kept() -> None:
    assert _command_of("config check legvise.toml") == "config check"


def test_a_line_of_nothing_but_options_names_no_command() -> None:
    assert _command_of("--quiet --read-only") is None


def test_the_version_flag_is_not_a_command() -> None:
    assert _command_of("--version") is None


def test_every_command_the_readme_shows_is_real() -> None:
    assert problems() == []
