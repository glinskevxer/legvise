"""The generated command reference."""

from __future__ import annotations

from legvise.tools.build_commands import (
    OUTPUT,
    commands,
    is_current,
    main,
    render,
    target,
)
from legvise.tools.check_cli import command_paths, registered_groups


def test_the_reference_on_disk_is_current() -> None:
    assert is_current()


def test_the_reference_lives_under_docs() -> None:
    assert OUTPUT == "docs/commands.md"
    assert target().exists()


def test_the_reference_says_it_is_generated() -> None:
    assert "Do not edit" in render()


def test_every_group_gets_a_top_level_heading() -> None:
    body = render()
    for group in registered_groups():
        assert f"## `legvise {group}`" in body


def test_every_command_gets_a_heading_of_its_own() -> None:
    body = render()
    for path in command_paths():
        assert f"### `legvise {path}" in body


def test_the_reference_covers_the_whole_tree() -> None:
    listed = {path for path, _ in commands()}
    assert set(command_paths()) <= listed
    assert set(registered_groups()) <= listed


def test_a_command_with_arguments_shows_them_in_its_heading() -> None:
    assert "### `legvise venue show CODE`" in render()


def test_a_command_with_options_lists_them_with_defaults() -> None:
    body = render()
    assert "| `--min-edge-bps` | `2` |" in body


def test_a_flag_shows_no_default() -> None:
    body = render()
    assert "| `--dry-run` |  |" in body


def test_the_footer_counts_the_commands_and_the_groups() -> None:
    groups = len(registered_groups())
    assert f"across {groups} groups" in render()


def test_the_reference_has_no_carriage_returns() -> None:
    assert b"\r" not in target().read_bytes()


def test_the_check_mode_passes_while_it_is_current() -> None:
    assert main(("--check",)) == 0
