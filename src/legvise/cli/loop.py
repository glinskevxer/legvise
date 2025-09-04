"""Commands for the triangular pass."""

from __future__ import annotations

import click

from legvise.cli.options import app, bps_text, echo_rows
from legvise.market.spread import raw_cross_bps
from legvise.model.book import Book
from legvise.money import dec
from legvise.scan.loop_session import LoopScanner
from legvise.scan.triangular import build_graph, profitable_cycles, starting_assets
from legvise.store.books import BookStore
from legvise.store.instruments import InstrumentStore

__all__ = ["group"]


@click.group("loop")
def group() -> None:
    """Search one venue at a time for conversion loops."""


@group.command("run")
@click.option("--start", default="USD", show_default=True, help="Asset the loop begins with.")
@click.option("--amount", default="10000", show_default=True, help="How much to start with.")
@click.option("--min-edge-bps", default="2", show_default=True, help="Floor for the net edge.")
@click.option("--screen-bps", default="0", show_default=True, help="Touch edge to bother pricing.")
@click.option("--max-hops", type=int, default=3, show_default=True, help="Longest loop to search.")
@click.option("--counter", type=int, default=0, show_default=True, help="Session number.")
@click.pass_context
def run(
    ctx: click.Context,
    start: str,
    amount: str,
    min_edge_bps: str,
    screen_bps: str,
    max_hops: int,
    counter: int,
) -> None:
    """Search every venue for loops and write the ones that pay."""
    context = app(ctx)
    scanner = LoopScanner(
        db=context.db,
        clock=context.clock,
        start_asset=start,
        start_amount=dec(amount, field="amount"),
        min_edge_bps=dec(min_edge_bps, field="min_edge_bps"),
        screen_bps=dec(screen_bps, field="screen_bps"),
        max_length=max_hops,
    )
    report = scanner.run(counter=counter)
    click.echo(f"session   {report.session}")
    click.echo(f"venues    {report.venues_searched}")
    click.echo(f"screened  {report.cycles_screened}")
    click.echo(f"written   {report.plans_written}")
    for note in report.skipped:
        click.echo(f"skipped   {note}", err=True)


@group.command("screen")
@click.argument("venue")
@click.option("--start", default="USD", show_default=True, help="Asset the loop begins with.")
@click.option("--min-bps", default="0", show_default=True, help="Touch edge to report.")
@click.option("--max-hops", type=int, default=3, show_default=True, help="Longest loop to search.")
@click.pass_context
def screen(ctx: click.Context, venue: str, start: str, min_bps: str, max_hops: int) -> None:
    """List the loops on one venue at the touch, without pricing them.

    This is the screen, not a price. The numbers it prints ignore depth and
    every fee, so a loop that looks like eight basis points here is a candidate
    and not an opportunity.
    """
    context = app(ctx)
    books = _books_on(ctx, venue)
    cycles = profitable_cycles(
        venue,
        books,
        start=start,
        min_bps=dec(min_bps, field="min_bps"),
        max_length=max_hops,
    )
    rows = [
        (" -> ".join((*cycle.assets, cycle.start)), str(cycle.length), bps_text(cycle.gross_bps))
        for cycle in cycles
    ]
    echo_rows(rows, ("loop", "hops", "touch_bps"))
    if not cycles and not context.quiet:
        click.echo(f"no loop from {start} on {venue} clears {min_bps} bps", err=True)


@group.command("graph")
@click.argument("venue")
@click.pass_context
def graph(ctx: click.Context, venue: str) -> None:
    """Print the conversion graph one venue's books make up."""
    built = build_graph(_books_on(ctx, venue))
    rows = [
        (asset, edge.to_asset, str(edge.symbol), str(edge.price))
        for asset in starting_assets(built)
        for edge in built[asset]
    ]
    echo_rows(rows, ("from", "to", "market", "price"))


def _books_on(ctx: click.Context, venue: str) -> tuple[Book, ...]:
    context = app(ctx)
    instruments = InstrumentStore(context.db)
    store = BookStore(context.db)
    found: list[Book] = []
    for symbol in instruments.symbols_on(venue):
        book = store.latest(venue, symbol)
        if book is not None:
            found.append(book)
    return tuple(found)


@group.command("cross")
@click.argument("symbol")
@click.pass_context
def cross(ctx: click.Context, symbol: str) -> None:
    """Print the touch edge between every ordered pair of venues for a market.

    The cheap screen the cross-venue scanner runs first, exposed so an operator
    can see what it saw without running a whole scan.
    """
    context = app(ctx)
    books = BookStore(context.db).latest_across(symbol)
    rows = []
    for buy in books:
        for sell in books:
            if buy.venue == sell.venue or not (buy.is_two_sided() and sell.is_two_sided()):
                continue
            rows.append((buy.venue, sell.venue, bps_text(raw_cross_bps(buy, sell))))
    echo_rows(rows, ("buy_on", "sell_on", "touch_bps"))
