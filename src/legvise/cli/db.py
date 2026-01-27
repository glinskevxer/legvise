"""Commands for the book of record itself."""

from __future__ import annotations

import click

from legvise.cli.options import app, echo_rows
from legvise.store.schema import MIGRATIONS, install
from legvise.store.stats import (
    applied_steps,
    approximate_bytes,
    compact,
    counts,
    oldest_snapshot,
    schema_version,
    total_rows,
)

__all__ = ["group"]


@click.group("db")
def group() -> None:
    """Look after the SQLite file the desk keeps everything in."""


@group.command("status")
@click.pass_context
def status(ctx: click.Context) -> None:
    """Print the schema version, the row counts and the size."""
    context = app(ctx)
    click.echo(f"schema      {schema_version(context.db)} of {len(MIGRATIONS)}")
    click.echo(f"rows        {total_rows(context.db)}")
    click.echo(f"size        {approximate_bytes(context.db)} bytes")
    oldest = oldest_snapshot(context.db)
    click.echo(f"oldest book {oldest or 'none on file'}")


@group.command("tables")
@click.pass_context
def tables(ctx: click.Context) -> None:
    """List every table and how many rows it holds, biggest first."""
    context = app(ctx)
    rows = [(item.table, str(item.rows)) for item in counts(context.db)]
    echo_rows(rows, ("table", "rows"))


@group.command("migrate")
@click.pass_context
def migrate(ctx: click.Context) -> None:
    """Bring the book up to the current schema and say what ran.

    The command tree migrates on open, so this is only ever a no-op in normal
    use. It exists so a migration can be run and reported on deliberately,
    rather than as a side effect of whatever command somebody happened to type.
    """
    context = app(ctx)
    ran = install(context.db, applied_at=context.now_text())
    if not ran:
        click.echo("already at the current schema")
        return
    for version in ran:
        click.echo(f"applied migration {version:04d}")


@group.command("applied")
@click.pass_context
def applied(ctx: click.Context) -> None:
    """List the migrations this book has applied, and when."""
    context = app(ctx)
    echo_rows(
        [
            (f"{step.version:04d}", step.name, step.digest, step.applied_at)
            for step in applied_steps(context.db)
        ],
        ("version", "name", "digest", "applied"),
    )


@group.command("vacuum")
@click.pass_context
def vacuum(ctx: click.Context) -> None:
    """Rebuild the file, giving back the space pruning left behind.

    Worth running after a large prune and not otherwise: it rewrites the whole
    file, which on a book with a few million level rows takes a while and needs
    room for a second copy.
    """
    context = app(ctx)
    before, after = compact(context.db)
    if not context.quiet:
        click.echo(f"{before} bytes before, {after} after")
