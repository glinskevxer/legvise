"""Commands for the venues the desk trades on."""

from __future__ import annotations

import click

from legvise.cli.options import app, echo_rows
from legvise.model.venue import Venue
from legvise.store.venues import VenueStore

__all__ = ["group"]


@click.group("venue")
def group() -> None:
    """Add, list and adjust the venues the desk trades on."""


@group.command("add")
@click.argument("code")
@click.argument("display_name")
@click.option("--staleness-ms", type=int, required=True, help="Quote age budget, milliseconds.")
@click.option("--depth-bps", required=True, help="How far off the touch the desk will sweep.")
@click.option("--cap", required=True, help="Most notional the desk will hold working here.")
@click.option("--maker-rebate", is_flag=True, help="This venue pays for resting liquidity.")
@click.pass_context
def add(
    ctx: click.Context,
    code: str,
    display_name: str,
    staleness_ms: int,
    depth_bps: str,
    cap: str,
    maker_rebate: bool,
) -> None:
    """Put a new venue on file with its budgets and its cap."""
    context = app(ctx)
    venue = Venue.build(
        code,
        display_name,
        staleness_budget_ms=staleness_ms,
        depth_limit_bps=depth_bps,
        notional_cap=cap,
        pays_maker_rebate=maker_rebate,
    )
    with context.db.tx():
        VenueStore(context.db).add(venue)
    if not context.quiet:
        click.echo(f"added venue {venue.code}")


@group.command("list")
@click.option("--active-only", is_flag=True, help="Skip the venues that are switched off.")
@click.pass_context
def list_venues(ctx: click.Context, active_only: bool) -> None:
    """List the venues on file."""
    context = app(ctx)
    venues = VenueStore(context.db).list(active_only=active_only)
    rows = [
        (
            v.code,
            v.display_name,
            str(v.staleness_budget_ms),
            str(v.depth_limit_bps),
            str(v.notional_cap),
            "yes" if v.pays_maker_rebate else "no",
            "on" if v.active else "off",
        )
        for v in venues
    ]
    echo_rows(rows, ("code", "name", "stale_ms", "depth_bps", "cap", "rebate", "state"))


@group.command("show")
@click.argument("code")
@click.pass_context
def show(ctx: click.Context, code: str) -> None:
    """Print one venue."""
    context = app(ctx)
    venue = VenueStore(context.db).get(code)
    click.echo(f"code           {venue.code}")
    click.echo(f"name           {venue.display_name}")
    click.echo(f"staleness_ms   {venue.staleness_budget_ms}")
    click.echo(f"depth_limit    {venue.depth_limit_bps} bps")
    click.echo(f"notional_cap   {venue.notional_cap}")
    click.echo(f"maker_rebate   {'yes' if venue.pays_maker_rebate else 'no'}")
    click.echo(f"state          {'on' if venue.active else 'off'}")


@group.command("disable")
@click.argument("code")
@click.pass_context
def disable(ctx: click.Context, code: str) -> None:
    """Switch a venue off without deleting anything."""
    context = app(ctx)
    store = VenueStore(context.db)
    with context.db.tx():
        store.save(store.get(code).deactivated())
    if not context.quiet:
        click.echo(f"venue {code} is off")


@group.command("enable")
@click.argument("code")
@click.pass_context
def enable(ctx: click.Context, code: str) -> None:
    """Switch a venue back on."""
    context = app(ctx)
    store = VenueStore(context.db)
    with context.db.tx():
        store.save(store.get(code).replacing(active=True))
    if not context.quiet:
        click.echo(f"venue {code} is on")
