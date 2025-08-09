"""Commands for reading the plans a scan produced."""

from __future__ import annotations

import click

from legvise.cli.options import app, bps_text, echo_rows
from legvise.model.plan import Plan
from legvise.store.plans import PlanStore

__all__ = ["group"]


@click.group("plan")
def group() -> None:
    """Read the plans on file."""


@group.command("list")
@click.argument("session")
@click.option("--actionable", is_flag=True, help="Skip the ones that were refused.")
@click.pass_context
def list_plans(ctx: click.Context, session: str, actionable: bool) -> None:
    """List the plans in a session, best net edge first."""
    context = app(ctx)
    store = PlanStore(context.db)
    plans = store.actionable(session) if actionable else store.for_session(session)
    rows = [
        (
            plan.ref.split("/")[-1],
            str(plan.symbol),
            "/".join(plan.venues),
            bps_text(plan.gross_bps),
            bps_text(plan.total_cost_bps),
            bps_text(plan.net_bps),
            plan.status.value,
            plan.clause or "",
        )
        for plan in plans
    ]
    echo_rows(rows, ("plan", "symbol", "venues", "gross", "cost", "net", "status", "clause"))


@group.command("show")
@click.argument("ref")
@click.pass_context
def show(ctx: click.Context, ref: str) -> None:
    """Print one plan and both of its legs."""
    context = app(ctx)
    plan = PlanStore(context.db).get(ref)
    _echo_plan(plan)
    rows = [
        (
            str(index),
            leg.venue,
            "buy" if leg.is_buy else "sell",
            str(leg.price),
            str(leg.size),
            bps_text(leg.fee_bps),
            str(leg.fee_amount),
            str(leg.levels_swept),
            bps_text(leg.slippage_bps),
        )
        for index, leg in enumerate(plan.legs)
    ]
    echo_rows(
        rows,
        ("leg", "venue", "side", "price", "size", "fee_bps", "fee", "levels", "slip"),
    )


def _echo_plan(plan: Plan) -> None:
    click.echo(f"ref        {plan.ref}")
    click.echo(f"kind       {plan.kind.value}")
    click.echo(f"symbol     {plan.symbol}")
    click.echo(f"notional   {plan.notional}")
    click.echo(f"gross      {bps_text(plan.gross_bps)} bps")
    click.echo(f"fees       {bps_text(plan.fee_bps)} bps")
    click.echo(f"slippage   {bps_text(plan.slippage_bps)} bps")
    click.echo(f"rebalance  {bps_text(plan.rebalance_bps)} bps")
    click.echo(f"net        {bps_text(plan.net_bps)} bps")
    click.echo(f"status     {plan.status.value}")
    if plan.clause:
        click.echo(f"clause     {plan.clause}")


@group.command("best")
@click.argument("session")
@click.option("--count", type=int, default=5, show_default=True, help="How many to print.")
@click.pass_context
def best(ctx: click.Context, session: str, count: int) -> None:
    """Print the best few plans in a session, one reference per line."""
    context = app(ctx)
    plans = PlanStore(context.db).actionable(session)[:count]
    for plan in plans:
        click.echo(f"{plan.ref} {bps_text(plan.net_bps)}")
    if not plans and not context.quiet:
        click.echo("nothing was actionable in that session", err=True)


@group.command("check")
@click.argument("session")
@click.pass_context
def check(ctx: click.Context, session: str) -> None:
    """Re-add every plan's edge components and report any that do not match.

    Stored arithmetic is not re-derived on read, so this is the only thing that
    would notice a plan written by an older version whose decomposition has
    since drifted.
    """
    context = app(ctx)
    broken = [p for p in PlanStore(context.db).for_session(session) if not p.arithmetic_holds()]
    for plan in broken:
        click.echo(
            f"{plan.ref} net {plan.net_bps} against {plan.gross_bps} less {plan.total_cost_bps}"
        )
    if broken:
        raise click.ClickException(f"{len(broken)} plans do not add up")
    if not context.quiet:
        click.echo("every plan adds up")
