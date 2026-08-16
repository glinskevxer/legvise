"""The context the command tree carries, and the options every command shares.

Click's `obj` is untyped by design, which is fine for a script and not fine for
a program with fourteen command groups. `Context` here is the typed thing that
actually gets passed around, and `app` pulls it back out with the cast in one
place instead of in every command.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import IO, Any

import click

from legvise.clock import Clock, SystemClock
from legvise.errors import LegviseError
from legvise.settings import load
from legvise.store.db import Database
from legvise.store.schema import install

__all__ = [
    "Context",
    "echo_json",
    "DeskGroup",
    "app",
    "bps_text",
    "db_option",
    "echo_rows",
    "open_context",
    "out_option",
    "writing_to",
]

DEFAULT_DB = "legvise.sqlite3"


@dataclass(slots=True)
class Context:
    """Everything a command needs that it did not get from its own arguments."""

    db: Database
    clock: Clock
    quiet: bool = False
    settings: dict[str, str | int] = field(default_factory=dict)
    config_path: Path | None = None

    def now_text(self) -> str:
        """The current instant as the store spells it."""
        return self.clock.now().isoformat()


def open_context(
    path: str | Path,
    *,
    clock: Clock | None = None,
    quiet: bool = False,
    read_only: bool = False,
    config: Path | None = None,
) -> Context:
    """Open the book of record and bring it up to the current schema.

    A read only context skips the migration, because it could not run one, and
    because a reader that quietly migrated the file it was asked to read would
    be doing the one thing read only is for preventing.
    """
    ticker = clock or SystemClock()
    settings = load(config) if config is not None else {}
    if read_only:
        return Context(
            db=Database.open_read_only(path),
            clock=ticker,
            quiet=quiet,
            settings=settings,
            config_path=config,
        )
    handle = Database.open(path)
    install(handle, applied_at=ticker.now().isoformat())
    return Context(db=handle, clock=ticker, quiet=quiet, settings=settings, config_path=config)


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


def out_option(fn: click.decorators.FC) -> click.decorators.FC:
    """The `--out` option, spelled once."""
    return click.option(
        "--out",
        "target",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Where to write it. Standard output if not given.",
    )(fn)


@contextmanager
def writing_to(target: Path | None) -> Iterator[IO[str]]:
    """Yield somewhere to write, which is standard output when no path is given.

    Standard output is deliberately not closed on the way out. Every export
    command used to open and close its own handle, and closing `sys.stdout` in
    a `finally` is the kind of thing that works until two commands run in one
    process, which is exactly what the test runner does.

    Newline translation is off, because the CSV writer picks its own line
    ending and a file that goes out with both would not load.
    """
    if target is None:
        yield sys.stdout
        return
    handle = target.open("w", encoding="utf-8", newline="")
    try:
        yield handle
    finally:
        handle.close()


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


def echo_json(payload: Mapping[str, object]) -> None:
    """Print one object as JSON, decimals and all.

    Every value goes out as text rather than as a JSON number. A size with eight
    decimal places read back through a JSON parser's float is not the size that
    was written, and the desk reconciles these against a venue.
    """
    click.echo(json.dumps({key: _jsonable(value) for key, value in payload.items()}, indent=2))


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple) and hasattr(value, "_fields"):
        # A named tuple is a record with a spelling of its own -- `Symbol` is
        # `BTC-USD`, not `["BTC", "USD"]` -- so it goes out as its text.
        return str(value)
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return str(value)
