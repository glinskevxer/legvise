"""Commands for fee ladders and the trailing volume that resolves them."""

from __future__ import annotations

import click

from legvise.cli.options import app, echo_rows
from legvise.fees.balance import cycles_funded, funding_for, require_funded
from legvise.fees.ladder import resolve, rung_index
from legvise.fees.quote import FeeContext, charge_for
from legvise.ids import asset_code
from legvise.model.fee import FeeLadder
from legvise.money import dec
from legvise.store.fees import FeeStore
from legvise.store.inventory import InventoryStore

__all__ = ["group"]


@click.group("fee")
def group() -> None:
    """Load fee ladders and record what the desk has traded."""


@group.command("set-ladder")
@click.argument("venue")
@click.argument("rungs", nargs=-1, required=True)
@click.pass_context
def set_ladder(ctx: click.Context, venue: str, rungs: tuple[str, ...]) -> None:
    """Replace a venue's ladder.

    Each rung is `volume:maker_bps:taker_bps`, lowest volume first, and the
    first one has to start at zero. Passing them all at once is deliberate: a
    ladder is replaced whole, never edited a rung at a time.
    """
    context = app(ctx)
    parsed = tuple(_split_rung(rung) for rung in rungs)
    ladder = FeeLadder.build(venue, parsed)
    with context.db.tx():
        FeeStore(context.db).put_ladder(ladder)
    if not context.quiet:
        click.echo(f"{ladder.venue} ladder has {ladder.depth()} rungs")


def _split_rung(text: str) -> tuple[str, str, str]:
    parts = text.split(":")
    if len(parts) != 3:
        raise click.BadParameter(f"expected volume:maker:taker, got {text!r}")
    return (parts[0], parts[1], parts[2])


@group.command("show-ladder")
@click.argument("venue")
@click.pass_context
def show_ladder(ctx: click.Context, venue: str) -> None:
    """Print a venue's ladder and mark the rung the desk is on."""
    context = app(ctx)
    store = FeeStore(context.db)
    ladder = store.ladder(venue)
    volume = store.volume(venue)
    standing = None if volume is None else rung_index(ladder, volume)
    rows = [
        (
            "*" if standing == index else "",
            str(index),
            str(tier.min_volume_30d),
            str(tier.maker_bps),
            str(tier.taker_bps),
        )
        for index, tier in enumerate(ladder.tiers)
    ]
    echo_rows(rows, ("", "rung", "from_volume", "maker_bps", "taker_bps"))
    if volume is None and not context.quiet:
        click.echo("no trailing volume on file, so no rung is marked", err=True)


@group.command("record-volume")
@click.argument("venue")
@click.argument("volume")
@click.pass_context
def record_volume(ctx: click.Context, venue: str, volume: str) -> None:
    """Record the desk's trailing thirty day volume on a venue."""
    context = app(ctx)
    amount = dec(volume, field="volume")
    with context.db.tx():
        FeeStore(context.db).record_volume(venue, amount, as_of=context.now_text())
    if not context.quiet:
        click.echo(f"{venue} trailing volume is {amount}")


@group.command("rate")
@click.argument("venue")
@click.option("--resting", is_flag=True, help="Price the maker side instead of the taker side.")
@click.pass_context
def rate(ctx: click.Context, venue: str, resting: bool) -> None:
    """Print the rate the desk pays on a venue right now."""
    context = app(ctx)
    store = FeeStore(context.db)
    tier = resolve(store.ladder(venue), store.volume(venue))
    click.echo(str(tier.maker_bps if resting else tier.taker_bps))


@group.command("clear-volume")
@click.argument("venue")
@click.pass_context
def clear_volume(ctx: click.Context, venue: str) -> None:
    """Forget a venue's trailing volume so pricing refuses until it is set again."""
    context = app(ctx)
    with context.db.tx():
        FeeStore(context.db).clear_volume(venue)
    if not context.quiet:
        click.echo(f"{venue} has no trailing volume on file")


@group.command("funding")
@click.argument("venue")
@click.argument("notional")
@click.option("--fee-asset", required=True, help="Asset this venue bills the fee in.")
@click.option("--fee-asset-price", required=True, help="What one unit of it is worth in quote.")
@click.option("--discount-bps", default="0", show_default=True, help="Discount for paying in it.")
@click.pass_context
def funding(
    ctx: click.Context,
    venue: str,
    notional: str,
    fee_asset: str,
    fee_asset_price: str,
    discount_bps: str,
) -> None:
    """Say whether the desk can pay a fee in the asset the venue bills it in.

    A venue that runs the desk out of its own token stops applying the discount
    and charges the full rate in the quote asset instead, silently. This is the
    check that would have noticed.
    """
    context = app(ctx)
    store = FeeStore(context.db)
    tier = resolve(store.ladder(venue), store.volume(venue))
    charge = charge_for(
        FeeContext(
            venue=venue,
            tier=tier,
            pays_maker_rebate=False,
            fee_asset=asset_code(fee_asset),
            fee_asset_rate=dec(fee_asset_price, field="fee_asset_price"),
            fee_asset_discount_bps=dec(discount_bps, field="discount_bps"),
        ),
        dec(notional, field="notional"),
        resting=False,
    )
    held = InventoryStore(context.db).position(venue, fee_asset)
    found = funding_for(charge, held)
    click.echo(f"rate       {charge.rate_bps} bps")
    click.echo(f"needed     {found.needed} {found.asset}")
    click.echo(f"available  {found.available} {found.asset}")
    click.echo(f"cycles     {cycles_funded(charge, held)}")
    require_funded(charge, held)
    if not context.quiet:
        click.echo("the discount is safe to price")
