"""Commands for the book of record itself."""

from __future__ import annotations

import click

from legvise.cli.options import app, echo_rows
from legvise.clock import parse_instant
from legvise.store.retention import Retention
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


@group.command("prune")
@click.option("--before", default=None, help="Drop what is older than this instant.")
@click.option("--keep-days", type=int, default=None, help="Drop what is older than this many days.")
@click.option("--dry-run", is_flag=True, help="Count what would go and change nothing.")
@click.pass_context
def prune(ctx: click.Context, before: str | None, keep_days: int | None, dry_run: bool) -> None:
    """Drop old snapshots and untraded sessions, keeping what is load bearing.

    Two things survive their age. The newest snapshot of a market stays, or the
    market leaves the rotation without saying so. A session with a fill against
    it stays, because that pair is the record of a trade.

    Give one of `--before` or `--keep-days`. `--keep-days` counts back from the
    clock, so the same command in a nightly job means a rolling window rather
    than a date somebody has to remember to move.
    """
    context = app(ctx)
    if (before is None) == (keep_days is None):
        raise click.UsageError("give one of --before or --keep-days")
    policy = Retention(context.db)
    at = (
        parse_instant(before, field="before")
        if before is not None
        else policy.cutoff_from(context.clock.now(), keep_days or 0)
    )
    found = policy.survey(at) if dry_run else policy.sweep(at)
    click.echo(f"cutoff     {at.isoformat()}")
    for line in found.lines():
        click.echo(line)
    if dry_run:
        click.echo("dry run    nothing was removed")
    elif not context.quiet:
        click.echo(f"removed    {found.rows} rows")
