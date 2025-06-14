"""Commands for balances and the bands that govern them."""

from __future__ import annotations

import click

from legvise.cli.options import app, echo_rows
from legvise.model.inventory import Band, Position
from legvise.risk.bands import room_for
from legvise.store.inventory import InventoryStore

__all__ = ["group"]


@click.group("inventory")
def group() -> None:
    """Record balances, set bands, and see where the desk is sitting."""


@group.command("set-balance")
@click.argument("venue")
@click.argument("asset")
@click.argument("free")
@click.option("--locked", default="0", show_default=True, help="Balance tied up in open orders.")
@click.pass_context
def set_balance(ctx: click.Context, venue: str, asset: str, free: str, locked: str) -> None:
    """Record what the desk holds of an asset on a venue."""
    context = app(ctx)
    position = Position.build(venue, asset, free=free, locked=locked, as_of=context.now_text())
    with context.db.tx():
        InventoryStore(context.db).put_position(position)
    if not context.quiet:
        click.echo(f"{position.venue} holds {position.total} {position.asset}")


@group.command("set-band")
@click.argument("venue")
@click.argument("asset")
@click.option("--floor", required=True, help="Hard stop. A leg may not take the holding below it.")
@click.option("--target", required=True, help="Where the rebalancer aims to put it back.")
@click.option("--ceiling", required=True, help="Soft. Crossing it books a rebalancing cost.")
@click.pass_context
def set_band(
    ctx: click.Context, venue: str, asset: str, floor: str, target: str, ceiling: str
) -> None:
    """Set the floor, target and ceiling for an asset on a venue."""
    context = app(ctx)
    band = Band.build(venue, asset, floor=floor, target=target, ceiling=ceiling)
    with context.db.tx():
        InventoryStore(context.db).put_band(band)
    if not context.quiet:
        click.echo(f"{band.venue} {band.asset} band is {band.floor}/{band.target}/{band.ceiling}")


@group.command("show")
@click.option("--venue", default=None, help="Only this venue.")
@click.option("--asset", default=None, help="Only this asset, across every venue.")
@click.pass_context
def show(ctx: click.Context, venue: str | None, asset: str | None) -> None:
    """Print balances against their bands."""
    context = app(ctx)
    store = InventoryStore(context.db)
    if venue and asset:
        raise click.UsageError("pass --venue or --asset, not both")
    if venue:
        positions = store.positions_on(venue)
    elif asset:
        positions = store.positions_of(asset)
    else:
        positions = tuple(p for a in store.assets_held() for p in store.positions_of(a))
    rows = []
    for position in sorted(positions, key=lambda p: p.key):
        band = store.band(position.venue, position.asset)
        if band is None:
            rows.append(
                (position.venue, position.asset, str(position.total), "-", "-", "-", "no band")
            )
            continue
        room = room_for(position, band)
        rows.append(
            (
                position.venue,
                position.asset,
                str(position.total),
                str(band.floor),
                str(band.target),
                str(band.ceiling),
                _state(room.is_below_floor, room.is_above_ceiling),
            )
        )
    echo_rows(rows, ("venue", "asset", "held", "floor", "target", "ceiling", "state"))


def _state(below: bool, above: bool) -> str:
    if below:
        return "under floor"
    if above:
        return "over ceiling"
    return "in band"


@group.command("room")
@click.argument("venue")
@click.argument("asset")
@click.pass_context
def room(ctx: click.Context, venue: str, asset: str) -> None:
    """Print how much room a leg has in each direction."""
    context = app(ctx)
    store = InventoryStore(context.db)
    measured = room_for(store.require_position(venue, asset), store.require_band(venue, asset))
    click.echo(f"held        {measured.holding}")
    click.echo(f"spendable   {measured.spendable}")
    click.echo(f"receivable  {measured.receivable}")
    click.echo(f"target_gap  {measured.target_gap}")


@group.command("clear-band")
@click.argument("venue")
@click.argument("asset")
@click.pass_context
def clear_band(ctx: click.Context, venue: str, asset: str) -> None:
    """Remove a band, which stops the scanner sizing anything on that asset."""
    context = app(ctx)
    with context.db.tx():
        InventoryStore(context.db).remove_band(venue, asset)
    if not context.quiet:
        click.echo(f"{venue} {asset} has no band")
