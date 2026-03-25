"""Commands for loading and reading order book snapshots.

Snapshots arrive from a feed handler this package does not own, so the loader
takes them the plainest way there is: `price:size` pairs on the command line, or
the same thing on standard input one level per line. Anything more structured
would be a format nobody else writes.
"""

from __future__ import annotations

import sys

import click

from legvise.cli.options import app, bps_text, echo_rows
from legvise.clock import parse_instant
from legvise.market.decay import confidence_in
from legvise.market.imbalance import disagreement, imbalance_at, leans_toward
from legvise.market.spread import mid, spread_bps
from legvise.model.book import Book, Side
from legvise.money import dec
from legvise.store.books import BookStore
from legvise.store.venues import VenueStore

__all__ = ["group"]


@click.group("book")
def group() -> None:
    """Load snapshots and read the ones on file."""


@group.command("load")
@click.argument("venue")
@click.argument("symbol")
@click.option("--bid", "bids", multiple=True, help="A bid level as price:size, best first.")
@click.option("--ask", "asks", multiple=True, help="An ask level as price:size, best first.")
@click.option("--observed-at", default=None, help="When the feed stamped it. Defaults to now.")
@click.option("--sequence", type=int, default=0, show_default=True, help="Feed sequence number.")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read side:price:size lines instead.")
@click.pass_context
def load(
    ctx: click.Context,
    venue: str,
    symbol: str,
    bids: tuple[str, ...],
    asks: tuple[str, ...],
    observed_at: str | None,
    sequence: int,
    from_stdin: bool,
) -> None:
    """Store one snapshot of a market."""
    context = app(ctx)
    if from_stdin:
        bids, asks = _read_levels(sys.stdin.read())
    at = parse_instant(observed_at) if observed_at else context.clock.now()
    book = Book.build(
        venue,
        symbol,
        observed_at=at,
        bids=tuple(_split(level) for level in bids),
        asks=tuple(_split(level) for level in asks),
        sequence=sequence,
    )
    with context.db.tx():
        BookStore(context.db).add(book)
    if not context.quiet:
        click.echo(f"{book.venue} {book.symbol} {len(book.bids)}x{len(book.asks)} levels")


def _split(level: str) -> tuple[str, str]:
    parts = level.split(":")
    if len(parts) != 2:
        raise click.BadParameter(f"expected price:size, got {level!r}")
    return (parts[0], parts[1])


def _read_levels(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    bids: list[str] = []
    asks: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(":")
        if len(parts) != 3:
            raise click.BadParameter(f"expected side:price:size, got {line!r}")
        side, price, size = parts
        target = bids if side.strip().lower() == "bid" else asks
        target.append(f"{price}:{size}")
    return (tuple(bids), tuple(asks))


@group.command("show")
@click.argument("venue")
@click.argument("symbol")
@click.option("--depth", type=int, default=5, show_default=True, help="Levels a side to print.")
@click.pass_context
def show(ctx: click.Context, venue: str, symbol: str, depth: int) -> None:
    """Print the newest snapshot for a market on a venue."""
    context = app(ctx)
    book = BookStore(context.db).require_latest(venue, symbol)
    rows = []
    for rank in range(depth):
        bid = book.bids[rank] if rank < len(book.bids) else None
        ask = book.asks[rank] if rank < len(book.asks) else None
        rows.append(
            (
                str(bid.size) if bid else "",
                str(bid.price) if bid else "",
                str(ask.price) if ask else "",
                str(ask.size) if ask else "",
            )
        )
    echo_rows(rows, ("bid_size", "bid", "ask", "ask_size"))
    if book.is_two_sided():
        click.echo(
            f"mid {bps_text(mid(book), '0.00000001')}  spread {bps_text(spread_bps(book))} bps"
        )
    click.echo(f"observed {book.observed_at.isoformat()}  sequence {book.sequence}")


@group.command("touch")
@click.argument("symbol")
@click.pass_context
def touch(ctx: click.Context, symbol: str) -> None:
    """Print the touch on every venue that has a book for a market."""
    context = app(ctx)
    books = BookStore(context.db).latest_across(symbol)
    rows = []
    for book in books:
        best_bid = book.best_bid
        best_ask = book.best_ask
        rows.append(
            (
                book.venue,
                str(best_bid.price) if best_bid else "-",
                str(best_ask.price) if best_ask else "-",
                book.observed_at.isoformat(),
            )
        )
    echo_rows(rows, ("venue", "bid", "ask", "observed"))


@group.command("prune")
@click.argument("before")
@click.pass_context
def prune(ctx: click.Context, before: str) -> None:
    """Drop every snapshot observed before an instant."""
    context = app(ctx)
    at = parse_instant(before, field="before")
    with context.db.tx():
        gone = BookStore(context.db).prune_before(at)
    if not context.quiet:
        click.echo(f"dropped {gone} snapshots")


@group.command("levels")
@click.argument("venue")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["bid", "ask"]))
@click.pass_context
def levels(ctx: click.Context, venue: str, symbol: str, side: str) -> None:
    """Print one side of the newest snapshot, one level per line."""
    context = app(ctx)
    book = BookStore(context.db).require_latest(venue, symbol)
    for level in book.side(Side(side)):
        click.echo(f"{level.price}:{level.size}")


@group.command("imbalance")
@click.argument("venue")
@click.argument("symbol")
@click.option("--depth-bps", default="50", show_default=True, help="Band the depth is read over.")
@click.pass_context
def imbalance(ctx: click.Context, venue: str, symbol: str, depth_bps: str) -> None:
    """Print which way the newest book leans, at the touch and deeper.

    The two disagreeing is the interesting case. It usually means somebody is
    working a large order, and it is a reason to size smaller rather than a
    reason to trade.
    """
    context = app(ctx)
    book = BookStore(context.db).require_latest(venue, symbol)
    limit = dec(depth_bps, field="depth_bps")
    touch, depth = imbalance_at(book, limit)
    click.echo(f"touch   {bps_text(touch.ratio, '0.0001')}  {touch.bid_size} / {touch.ask_size}")
    click.echo(f"depth   {bps_text(depth.ratio, '0.0001')}  {depth.bid_size} / {depth.ask_size}")
    click.echo(f"apart   {bps_text(disagreement(book, limit), '0.0001')}")
    side = leans_toward(book, limit)
    click.echo(f"leans   {side.value if side else 'neither, the two measures disagree'}")


@group.command("confidence")
@click.argument("venue")
@click.argument("symbol")
@click.pass_context
def confidence(ctx: click.Context, venue: str, symbol: str) -> None:
    """Print how far through its staleness budget the newest book is.

    The budget is a cliff and this is the slope up to it. A book halfway through
    is still tradable and is worth sizing smaller, which the cliff on its own
    cannot express.
    """
    context = app(ctx)
    book = BookStore(context.db).require_latest(venue, symbol)
    record = VenueStore(context.db).get(venue)
    found = confidence_in(book, record, context.clock.now())
    click.echo(f"age      {found.age_ms} ms")
    click.echo(f"budget   {found.budget_ms} ms")
    click.echo(f"believe  {bps_text(found.factor, '0.0001')}")
    state = "fresh" if found.is_fresh else ("spent" if found.is_spent else "decaying")
    click.echo(f"state    {state}")
