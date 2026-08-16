"""Commands for the settings file the desk keeps beside its book."""

from __future__ import annotations

from pathlib import Path

import click

from legvise.cli.options import app, echo_rows
from legvise.settings import DEFAULTS, SECTION, load, resolve

__all__ = ["group"]


@click.group("config")
def group() -> None:
    """Read the settings file and see which numbers it is deciding."""


@group.command("show")
@click.option("--changed-only", is_flag=True, help="Skip the ones nobody has set.")
@click.pass_context
def show(ctx: click.Context, changed_only: bool) -> None:
    """Print every setting, its value, and the level that decided it.

    The source column is the one to read. A number that says `default` is one
    nobody has set, which is a different thing from one the file happens to
    agree with, and in a plain list of numbers those look the same.
    """
    context = app(ctx)
    found = resolve(from_file=context.settings)
    rows = [
        (item.name, str(item.value), item.source)
        for item in found
        if not (changed_only and item.is_default)
    ]
    echo_rows(rows, ("setting", "value", "from"))
    if not context.quiet:
        click.echo(f"file        {context.config_path or 'none loaded'}")


@group.command("defaults")
@click.pass_context
def defaults(ctx: click.Context) -> None:
    """Print what the tool ships with, ignoring any file."""
    context = app(ctx)
    rows = [(name, str(DEFAULTS.value_of(name))) for name in DEFAULTS.names()]
    echo_rows(rows, ("setting", "value"))
    if not context.quiet:
        click.echo(f"section     [{SECTION}]")


@group.command("check")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@click.pass_context
def check(ctx: click.Context, path: Path) -> None:
    """Read a settings file and say what it sets, without running anything.

    Worth doing in the change that edits the file rather than in the scan that
    picks it up. A typo in a key name is refused here and silently ignored by
    anything that reads a file the lazy way.
    """
    context = app(ctx)
    found = load(path)
    rows = [(name, str(value)) for name, value in sorted(found.items())]
    echo_rows(rows, ("setting", "value"))
    if not context.quiet:
        click.echo(f"{path} sets {len(found)} of {len(DEFAULTS.names())} settings")
