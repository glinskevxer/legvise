"""Commands for balances and the bands that govern them."""

from __future__ import annotations

from decimal import Decimal

import click

from legvise.cli.options import app, bps_text, echo_rows
from legvise.ids import asset_code, venue_code
from legvise.ledger.reconcile import reconcile
from legvise.model.inventory import Band, Position
from legvise.money import dec
from legvise.risk.bands import room_for
from legvise.risk.concentration import (
    Concentration,
    ConcentrationLimits,
    measure,
    require_within,
)
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


@group.command("concentration")
@click.option(
    "--mark",
    "marks",
    multiple=True,
    required=True,
    help="What one unit of an asset is worth, as ASSET:PRICE.",
)
@click.option(
    "--max-asset-share",
    default="0.6",
    show_default=True,
    help="Most of the desk one asset may be.",
)
@click.option(
    "--max-venue-share",
    default="0.8",
    show_default=True,
    help="Most of one asset that may sit on one venue.",
)
@click.pass_context
def concentration(
    ctx: click.Context, marks: tuple[str, ...], max_asset_share: str, max_venue_share: str
) -> None:
    """Print how much of the desk is in one asset, and how much on one venue."""
    context = app(ctx)
    store = InventoryStore(context.db)
    positions = tuple(p for asset in store.assets_held() for p in store.positions_of(asset))
    priced = measure(positions, _marks(marks))
    click.echo(f"desk value  {priced.total_value}")
    rows = [
        (
            asset,
            str(priced.by_asset[asset]),
            bps_text(priced.asset_share(asset), "0.0001"),
            _venue_spread(priced, asset),
        )
        for asset in sorted(priced.by_asset)
    ]
    echo_rows(rows, ("asset", "value", "desk_share", "venues"))
    limits = ConcentrationLimits(
        most_of_desk_in_one_asset=dec(max_asset_share, field="max_asset_share"),
        most_of_an_asset_on_one_venue=dec(max_venue_share, field="max_venue_share"),
    )
    require_within(priced, limits)
    if not context.quiet:
        click.echo("inside both concentration limits")


def _marks(given: tuple[str, ...]) -> dict[str, Decimal]:
    found: dict[str, Decimal] = {}
    for entry in given:
        parts = entry.split(":")
        if len(parts) != 2:
            raise click.BadParameter(f"expected ASSET:PRICE, got {entry!r}")
        found[asset_code(parts[0])] = dec(parts[1], field="mark")
    return found


def _venue_spread(priced: Concentration, asset: str) -> str:
    """Each venue holding an asset and its share of it, biggest first."""
    venues = sorted(
        (venue for held, venue in priced.by_asset_venue if held == asset),
        key=lambda venue: (-priced.venue_share(asset, venue), venue),
    )
    return " ".join(
        f"{venue}={bps_text(priced.venue_share(asset, venue), '0.01')}" for venue in venues
    )


@group.command("reconcile")
@click.option(
    "--holds",
    "holds",
    multiple=True,
    required=True,
    help="What a venue says it holds, as VENUE:ASSET:AMOUNT.",
)
@click.option(
    "--tolerance",
    "tolerances",
    multiple=True,
    help="Dust to ignore for an asset, as ASSET:AMOUNT.",
)
@click.pass_context
def reconcile_balances(
    ctx: click.Context, holds: tuple[str, ...], tolerances: tuple[str, ...]
) -> None:
    """Compare what the desk records against what a venue snapshot says.

    Nothing is written. A reconciliation that overwrites the desk's record with
    the venue's is a reconciliation nobody ever reads, and the differences are
    the whole point.
    """
    context = app(ctx)
    store = InventoryStore(context.db)
    positions = tuple(p for asset in store.assets_held() for p in store.positions_of(asset))
    found = reconcile(positions, _holdings(holds), _tolerances(tolerances))
    rows = [
        (
            item.venue,
            item.asset,
            str(item.ours),
            str(item.theirs),
            str(item.drift),
            "yes" if item.is_material else "no",
            item.direction,
        )
        for item in found.differences
    ]
    echo_rows(rows, ("venue", "asset", "ours", "theirs", "drift", "material", "reads"))
    worst = found.worst()
    if worst is not None:
        raise click.ClickException(
            f"{len(found.material)} material differences, worst"
            f" {worst.venue} {worst.asset} at {worst.drift}"
        )
    if not context.quiet:
        click.echo("the desk and the venues agree")


def _holdings(given: tuple[str, ...]) -> dict[tuple[str, str], Decimal]:
    found: dict[tuple[str, str], Decimal] = {}
    for entry in given:
        parts = entry.split(":")
        if len(parts) != 3:
            raise click.BadParameter(f"expected VENUE:ASSET:AMOUNT, got {entry!r}")
        found[(venue_code(parts[0]), asset_code(parts[1]))] = dec(parts[2], field="amount")
    return found


def _tolerances(given: tuple[str, ...]) -> dict[str, Decimal]:
    found: dict[str, Decimal] = {}
    for entry in given:
        parts = entry.split(":")
        if len(parts) != 2:
            raise click.BadParameter(f"expected ASSET:AMOUNT, got {entry!r}")
        found[asset_code(parts[0])] = dec(parts[1], field="tolerance")
    return found
