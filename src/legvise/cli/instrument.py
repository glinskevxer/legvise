"""Commands for the markets the desk lists on each venue."""

from __future__ import annotations

from dataclasses import replace

import click

from legvise.cli.options import app, echo_rows
from legvise.model.instrument import Instrument
from legvise.store.instruments import InstrumentStore
from legvise.store.venues import VenueStore

__all__ = ["group"]


@click.group("instrument")
def group() -> None:
    """Add, list and adjust the markets the desk trades."""


@group.command("add")
@click.argument("venue")
@click.argument("symbol")
@click.option("--venue-symbol", default=None, help="How the venue spells it, if not BASE-QUOTE.")
@click.option("--tick", required=True, help="Price increment the venue enforces.")
@click.option("--lot", required=True, help="Size increment the venue enforces.")
@click.option("--min-notional", required=True, help="Smallest order the venue accepts.")
@click.option("--max-notional", required=True, help="Largest order the venue accepts.")
@click.pass_context
def add(
    ctx: click.Context,
    venue: str,
    symbol: str,
    venue_symbol: str | None,
    tick: str,
    lot: str,
    min_notional: str,
    max_notional: str,
) -> None:
    """Add a market on a venue."""
    context = app(ctx)
    instrument = Instrument.build(
        venue,
        symbol,
        venue_symbol=venue_symbol,
        tick_size=tick,
        lot_step=lot,
        min_notional=min_notional,
        max_notional=max_notional,
    )
    with context.db.tx():
        InstrumentStore(context.db).add(instrument)
    if not context.quiet:
        click.echo(f"added {instrument.symbol} on {instrument.venue}")


@group.command("list")
@click.option("--venue", default=None, help="Only this venue.")
@click.option("--symbol", default=None, help="Only this market, across every venue.")
@click.option("--active-only", is_flag=True, help="Skip the markets that are switched off.")
@click.pass_context
def list_instruments(
    ctx: click.Context, venue: str | None, symbol: str | None, active_only: bool
) -> None:
    """List the markets on file."""
    context = app(ctx)
    store = InstrumentStore(context.db)
    if venue and symbol:
        raise click.UsageError("pass --venue or --symbol, not both")
    if venue:
        found = store.for_venue(venue, active_only=active_only)
    elif symbol:
        found = store.for_symbol(symbol, active_only=active_only)
    else:
        found = tuple(
            i
            for v in VenueStore(context.db).codes()
            for i in store.for_venue(v, active_only=active_only)
        )
    rows = [
        (
            i.venue,
            str(i.symbol),
            i.venue_symbol,
            str(i.tick_size),
            str(i.lot_step),
            str(i.min_notional),
            str(i.max_notional),
            "on" if i.active else "off",
        )
        for i in found
    ]
    echo_rows(rows, ("venue", "symbol", "their_symbol", "tick", "lot", "min", "max", "state"))


@group.command("shared")
@click.option(
    "--min-venues", type=int, default=2, show_default=True, help="How many venues have to list it."
)
@click.pass_context
def shared(ctx: click.Context, min_venues: int) -> None:
    """List the markets that are live on enough venues to be worth scanning."""
    context = app(ctx)
    found = InstrumentStore(context.db).shared_symbols(minimum_venues=min_venues)
    for symbol in found:
        click.echo(str(symbol))
    if not found and not context.quiet:
        click.echo(f"no market is live on {min_venues} venues", err=True)


@group.command("disable")
@click.argument("venue")
@click.argument("symbol")
@click.pass_context
def disable(ctx: click.Context, venue: str, symbol: str) -> None:
    """Switch a market off on one venue."""
    context = app(ctx)
    store = InstrumentStore(context.db)
    current = store.get(venue, symbol)
    with context.db.tx():
        store.save(replace(current, active=False))
    if not context.quiet:
        click.echo(f"{symbol} on {venue} is off")
