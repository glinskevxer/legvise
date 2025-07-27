"""The context the command tree carries, and the options every command shares.

Click's `obj` is untyped by design, which is fine for a script and not fine for
a program with fourteen command groups. `Context` here is the typed thing that
actually gets passed around, and `app` pulls it back out with the cast in one
place instead of in every command.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import click

from legvise.clock import Clock, SystemClock
from legvise.errors import LegviseError
from legvise.store.db import Database
from legvise.store.schema import install

__all__ = [
    "Context",
    "DeskGroup",
    "app",
    "bps_text",
    "db_option",
    "echo_rows",
    "open_context",
]

DEFAULT_DB = "legvise.sqlite3"


@dataclass(slots=True)
class Context:
    """Everything a command needs that it did not get from its own arguments."""

    db: Database
    clock: Clock
    quiet: bool = False

    def now_text(self) -> str:
        """The current instant as the store spells it."""
        return self.clock.now().isoformat()


def open_context(path: str | Path, *, clock: Clock | None = None, quiet: bool = False) -> Context:
    """Open the book of record and bring it up to the current schema."""
    handle = Database.open(path)
    ticker = clock or SystemClock()
    install(handle, applied_at=ticker.now().isoformat())
    return Context(db=handle, clock=ticker, quiet=quiet)


def app(ctx: click.Context) -> Context:
    """The typed context, from wherever click stashed it."""
    found = ctx.find_object(Context)
    if found is None:  # pragma: no cover - click builds this in the root group
        raise click.ClickException("the command tree was not started from its root")
    return found


def db_option(fn: click.decorators.FC) -> click.decorators.FC:
    """The `--db` option, spelled once."""
    return click.option(
        "--db",
        "db_path",
        default=DEFAULT_DB,
        show_default=True,
        type=click.Path(dir_okay=False, path_type=Path),
        help="Path to the book of record.",
    )(fn)


class DeskGroup(click.Group):
    """A group that turns a domain refusal into an ordinary command failure.

    Without this the console script and the test runner disagree: `main` catches
    `LegviseError` and prints it, `CliRunner` lets it escape as a traceback. The
    behaviour a user sees should not depend on who invoked the tree, so the
    translation happens where the tree is, not where the process is.
    """

    def invoke(self, ctx: click.Context) -> Any:
        """Run the chosen command, restating a domain error as a click one."""
        try:
            return super().invoke(ctx)
        except LegviseError as exc:
            raise click.ClickException(exc.message) from exc


def bps_text(value: Decimal, places: str = "0.01") -> str:
    """A basis point figure at a readable scale.

    Division on `Decimal` runs to the context precision, so an honest spread
    calculation can print twenty eight significant figures. That is right in
    the arithmetic and useless on a terminal, so display rounds and storage
    does not.
    """
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_EVEN))


def echo_rows(rows: Sequence[Sequence[str]], headers: Sequence[str]) -> None:
    """Print a table with the columns padded to their widest cell.

    Deliberately not a dependency. The desk pipes this into grep and awk, and a
    box-drawing table would break both.
    """
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    click.echo("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip())
    click.echo("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        click.echo("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
