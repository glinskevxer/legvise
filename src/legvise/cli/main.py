"""The command tree root.

Every subcommand group is registered here and nowhere else, so `legvise --help`
is the whole surface of the program. There is a check that keeps this file and
the `cli` package in step.
"""

from __future__ import annotations

from pathlib import Path

import click

from legvise import __version__
from legvise.cli import (
    book,
    db,
    fee,
    fill,
    instrument,
    inventory,
    loop,
    network,
    plan,
    report,
    scan,
    venue,
)
from legvise.cli.options import DEFAULT_DB, Context, DeskGroup, open_context
from legvise.errors import LegviseError

__all__ = ["cli", "main"]


@click.group(cls=DeskGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="legvise")
@click.option(
    "--db",
    "db_path",
    default=DEFAULT_DB,
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to the book of record.",
)
@click.option("--quiet", is_flag=True, help="Print results only, no commentary.")
@click.pass_context
def cli(ctx: click.Context, db_path: Path, quiet: bool) -> None:
    """Scan for cross-venue arbitrage against books the desk already has."""
    ctx.obj = open_context(db_path, quiet=quiet)
    ctx.call_on_close(_close)


@click.pass_obj
def _close(obj: Context) -> None:
    obj.db.close()


cli.add_command(book.group)
cli.add_command(db.group)
cli.add_command(fee.group)
cli.add_command(fill.group)
cli.add_command(instrument.group)
cli.add_command(inventory.group)
cli.add_command(loop.group)
cli.add_command(network.group)
cli.add_command(plan.group)
cli.add_command(report.group)
cli.add_command(scan.group)
cli.add_command(venue.group)


def main() -> int:
    """Console script entry point. Domain errors print, they do not traceback."""
    try:
        cli.main(standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except click.Abort:
        click.echo("aborted", err=True)
        return 130
    except LegviseError as exc:
        click.echo(f"error: {exc.message}", err=True)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
