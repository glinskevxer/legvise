"""The command tree is complete, and every command says what it does."""

from __future__ import annotations

import click
from click.testing import CliRunner

from legvise.cli.main import cli
from legvise.tools.check_cli import command_paths, problems, registered_groups


def test_the_tree_is_complete_and_documented() -> None:
    assert problems() == []


def test_every_group_the_desk_uses_is_registered() -> None:
    groups = set(registered_groups())
    assert groups == {
        "book",
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
