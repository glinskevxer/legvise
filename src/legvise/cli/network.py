"""Commands for transfer networks and which venues will use them."""

from __future__ import annotations

import click

from legvise.cli.options import app, bps_text, echo_rows
from legvise.model.network import TransferNetwork, VenueNetwork
from legvise.money import dec
from legvise.routing.pricer import StoreRebalancePricer
from legvise.routing.rebalance import CarryTerms
from legvise.store.networks import NetworkStore

__all__ = ["group"]


@click.group("network")
def group() -> None:
    """Declare transfer networks and say which venues support them."""


@group.command("add")
@click.argument("asset")
@click.argument("code")
@click.option("--fee", required=True, help="Flat withdrawal fee, in the asset being moved.")
@click.option("--min-withdraw", required=True, help="Smallest transfer the network takes.")
@click.option("--confirmations", type=int, required=True, help="Blocks before it is credited.")
@click.option("--block-minutes", required=True, help="How long one block takes.")
@click.pass_context
def add(
    ctx: click.Context,
    asset: str,
    code: str,
    fee: str,
    min_withdraw: str,
    confirmations: int,
    block_minutes: str,
) -> None:
    """Declare a way of moving an asset."""
    context = app(ctx)
    network = TransferNetwork.build(
        asset,
        code,
        withdraw_fee=fee,
        min_withdraw=min_withdraw,
        confirmations=confirmations,
        minutes_per_confirmation=block_minutes,
    )
    with context.db.tx():
        NetworkStore(context.db).put_network(network)
    if not context.quiet:
        click.echo(f"{network.asset} on {network.code} settles in {network.settle_minutes} min")


@group.command("support")
@click.argument("venue")
@click.argument("asset")
@click.argument("code")
@click.option("--no-deposit", is_flag=True, help="This venue will not credit deposits here.")
@click.option("--no-withdraw", is_flag=True, help="This venue will not send on this network.")
@click.pass_context
def support(
    ctx: click.Context, venue: str, asset: str, code: str, no_deposit: bool, no_withdraw: bool
) -> None:
    """Record whether a venue will send and receive on a network."""
    context = app(ctx)
    entry = VenueNetwork.build(
        venue,
        asset,
        code,
        deposit_enabled=not no_deposit,
        withdraw_enabled=not no_withdraw,
    )
    with context.db.tx():
        NetworkStore(context.db).put_support(entry)
    if not context.quiet:
        click.echo(
            f"{entry.venue} {entry.asset} on {entry.network}:"
            f" deposit {'on' if entry.deposit_enabled else 'off'},"
            f" withdraw {'on' if entry.withdraw_enabled else 'off'}"
        )


@group.command("list")
@click.argument("asset")
@click.pass_context
def list_networks(ctx: click.Context, asset: str) -> None:
    """List the networks that can move an asset."""
    context = app(ctx)
    rows = [
        (
            network.code,
            str(network.withdraw_fee),
            str(network.min_withdraw),
            str(network.confirmations),
            str(network.settle_minutes),
        )
        for network in NetworkStore(context.db).networks_for(asset)
    ]
    echo_rows(rows, ("network", "fee", "min", "confirms", "minutes"))


@group.command("routes")
@click.argument("asset")
@click.argument("sender")
@click.argument("receiver")
@click.option("--amount", default=None, help="Price the routes for this much of the asset.")
@click.option("--carry-bps-hour", default="6", show_default=True, help="Charge for capital.")
@click.option(
    "--cycles", type=int, default=10, show_default=True, help="Plans one transfer serves."
)
@click.pass_context
def routes(
    ctx: click.Context,
    asset: str,
    sender: str,
    receiver: str,
    amount: str | None,
    carry_bps_hour: str,
    cycles: int,
) -> None:
    """List the networks that can move an asset from one venue to another."""
    context = app(ctx)
    store = NetworkStore(context.db)
    open_routes = store.routes_between(asset, sender, receiver)
    if amount is None:
        for network in open_routes:
            click.echo(network.code)
        if not open_routes and not context.quiet:
            click.echo(f"no open route moves {asset} from {sender} to {receiver}", err=True)
        return
    pricer = StoreRebalancePricer(
        networks=store,
        terms=CarryTerms(
            carry_bps_per_hour=dec(carry_bps_hour, field="carry_bps_hour"),
            cycles_served=cycles,
        ),
        stranded_bps=dec("0"),
    )
    chosen = pricer.route_for(asset, sender, receiver, dec(amount, field="amount"))
    if chosen is None:
        raise click.ClickException(f"no open route can move {amount} {asset}")
    click.echo(chosen)


@group.command("cost")
@click.argument("asset")
@click.argument("sender")
@click.argument("receiver")
@click.argument("amount")
@click.option("--price", required=True, help="What one unit of the asset is worth in the quote.")
@click.option("--notional", required=True, help="The plan notional to charge against.")
@click.option("--carry-bps-hour", default="6", show_default=True, help="Charge for capital.")
@click.option(
    "--cycles", type=int, default=10, show_default=True, help="Plans one transfer serves."
)
@click.option("--stranded-bps", default="250", show_default=True, help="Charge with no route.")
@click.pass_context
def cost(
    ctx: click.Context,
    asset: str,
    sender: str,
    receiver: str,
    amount: str,
    price: str,
    notional: str,
    carry_bps_hour: str,
    cycles: int,
    stranded_bps: str,
) -> None:
    """Print what moving an excess would charge one plan, in basis points."""
    context = app(ctx)
    pricer = StoreRebalancePricer(
        networks=NetworkStore(context.db),
        terms=CarryTerms(
            carry_bps_per_hour=dec(carry_bps_hour, field="carry_bps_hour"),
            cycles_served=cycles,
        ),
        stranded_bps=dec(stranded_bps, field="stranded_bps"),
    )
    charged = pricer.charge_bps(
        asset=asset,
        sender=sender,
        receiver=receiver,
        excess=dec(amount, field="amount"),
        unit_price=dec(price, field="price"),
        notional=dec(notional, field="notional"),
    )
    click.echo(bps_text(charged, "0.0001"))
