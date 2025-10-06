"""Commands for recording fills and reading what a plan actually made."""

from __future__ import annotations

import click

from legvise.cli.options import app, bps_text, echo_rows
from legvise.ledger.attribution import attribute
from legvise.model.book import Side
from legvise.model.fill import Fill
from legvise.store.fills import FillStore
from legvise.store.plans import PlanStore

__all__ = ["group"]


@click.group("fill")
def group() -> None:
    """Record fills against a plan and read the outcome."""


@group.command("record")
@click.argument("plan_ref")
@click.argument("leg_index", type=int)
@click.argument("trade_id")
@click.option("--price", required=True, help="Price the venue reported.")
@click.option("--size", required=True, help="Size the venue reported.")
@click.option("--fee", default="0", show_default=True, help="Fee the venue charged.")
@click.option("--at", "filled_at", default=None, help="When it filled. Defaults to now.")
@click.pass_context
def record(
    ctx: click.Context,
    plan_ref: str,
    leg_index: int,
    trade_id: str,
    price: str,
    size: str,
    fee: str,
    filled_at: str | None,
) -> None:
    """Append one fill against a leg of a plan."""
    context = app(ctx)
    plan = PlanStore(context.db).get(plan_ref)
    if leg_index >= len(plan.legs):
        raise click.BadParameter(f"plan {plan_ref} has {len(plan.legs)} legs")
    leg = plan.legs[leg_index]
    fill = Fill.build(
        plan_ref,
        leg_index,
        leg.venue,
        leg.takes,
        price=price,
        size=size,
        fee_amount=fee,
        filled_at=filled_at or context.now_text(),
    )
    with context.db.tx():
        FillStore(context.db).add(fill, venue_trade_id=trade_id)
    if not context.quiet:
        click.echo(f"{plan_ref} leg {leg_index}: {fill.size} at {fill.price}")


@group.command("list")
@click.argument("plan_ref")
@click.pass_context
def list_fills(ctx: click.Context, plan_ref: str) -> None:
    """List every fill against a plan."""
    context = app(ctx)
    rows = [
        (
            str(fill.leg_index),
            fill.venue,
            "buy" if fill.takes is Side.ASK else "sell",
            str(fill.price),
            str(fill.size),
            str(fill.fee_amount),
            fill.filled_at,
        )
        for fill in FillStore(context.db).for_plan(plan_ref)
    ]
    echo_rows(rows, ("leg", "venue", "side", "price", "size", "fee", "at"))


@group.command("outcome")
@click.argument("plan_ref")
@click.pass_context
def outcome(ctx: click.Context, plan_ref: str) -> None:
    """Print what each leg of a plan achieved."""
    context = app(ctx)
    plan = PlanStore(context.db).get(plan_ref)
    results = FillStore(context.db).results_for(plan)
    rows = []
    for result in results:
        traded = result.filled_size > 0
        rows.append(
            (
                str(result.leg_index),
                result.outcome.value,
                str(result.expected_size),
                str(result.filled_size),
                str(result.expected_price),
                str(result.realised_price) if traded else "-",
                str(result.fees_paid),
            )
        )
    echo_rows(rows, ("leg", "outcome", "wanted", "filled", "planned", "realised", "fees"))


@group.command("attribution")
@click.argument("plan_ref")
@click.pass_context
def attribution(ctx: click.Context, plan_ref: str) -> None:
    """Print why a plan made more or less than it said it would."""
    context = app(ctx)
    plan = PlanStore(context.db).get(plan_ref)
    found = attribute(plan, FillStore(context.db).results_for(plan))
    click.echo(f"plan         {found.plan_ref}")
    click.echo(f"expected     {bps_text(found.expected_bps)} bps")
    click.echo(f"realised     {bps_text(found.realised_bps)} bps")
    click.echo(f"gap          {bps_text(found.gap_bps)} bps")
    click.echo(f"price drift  {bps_text(found.price_drift_bps)} bps")
    click.echo(f"fee drift    {bps_text(found.fee_drift_bps)} bps")
    click.echo(f"unexplained  {bps_text(found.unexplained_bps)} bps")
    click.echo(f"fill ratio   {bps_text(found.shortfall_ratio, '0.0001')}")
    if found.has_leg_risk:
        legs = ", ".join(str(index) for index in found.naked_legs)
        click.echo(f"LEG RISK     legs {legs} did not fill", err=True)
