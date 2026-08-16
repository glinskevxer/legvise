"""The command tree is complete, and every command says what it does."""

from __future__ import annotations

import click
from click.testing import CliRunner

from legvise.cli.main import cli
from legvise.tools.check_cli import command_paths, problems, registered_groups, value_options


def test_the_tree_is_complete_and_documented() -> None:
    assert problems() == []


def test_every_group_the_desk_uses_is_registered() -> None:
    groups = set(registered_groups())
    assert groups == {
        "audit",
        "book",
        "config",
        "db",
        "fee",
        "fill",
        "instrument",
        "inventory",
        "loop",
        "network",
        "plan",
        "report",
        "scan",
        "venue",
    }


def test_the_command_paths_cover_the_whole_surface() -> None:
    paths = set(command_paths())
    assert "venue add" in paths
    assert "scan run" in paths
    assert "loop screen" in paths
    assert "report export-edge" in paths


def test_every_path_appears_in_the_help_of_its_group() -> None:
    runner = CliRunner()
    for path in command_paths():
        group, _, command = path.partition(" ")
        result = runner.invoke(cli, [group, "--help"])
        assert result.exit_code == 0
        assert command in result.output


def test_the_root_help_lists_every_group() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    for group in registered_groups():
        assert group in result.output


def test_every_group_is_a_group_rather_than_a_bare_command() -> None:
    for name in registered_groups():
        assert isinstance(cli.commands[name], click.Group), name


def test_the_tree_has_more_than_thirty_commands() -> None:
    assert len(command_paths()) > 30


# Which options take a value. A flag stands alone and an option is followed by
# its value, and anything reading a written command line has to know which.


def test_an_option_that_takes_a_path_is_named() -> None:
    assert "--db" in value_options()
    assert "--config" in value_options()


def test_a_flag_is_not_one_of_them() -> None:
    assert "--quiet" not in value_options()
    assert "--dry-run" not in value_options()
    assert "--read-only" not in value_options()


def test_an_option_on_a_subcommand_is_found_too() -> None:
    assert "--min-edge-bps" in value_options()
    assert "--keep-days" in value_options()


def test_every_spelling_of_an_option_is_listed() -> None:
    assert "--session" in value_options()


def test_the_help_flag_is_not_an_option_that_takes_a_value() -> None:
    assert "-h" not in value_options()
