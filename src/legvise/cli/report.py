"""Commands that print and export the reports."""

from __future__ import annotations

from pathlib import Path

import click

from legvise.cli.options import app, bps_text, echo_json, echo_rows, out_option, writing_to
from legvise.ids import asset_code
from legvise.report.desk_report import build_desk_status
from legvise.report.edge_report import build_edge_report
from legvise.report.export import (
    LEG_FIELDS,
    PLAN_FIELDS,
    desk_payload,
    edge_payload,
    leg_rows,
    plan_rows,
    session_payload,
    write_csv,
    write_edge_json,
    write_session_json,
)
from legvise.report.inventory_report import build_inventory_report
from legvise.report.session_report import summarise
from legvise.report.venue_report import build_venue_report
from legvise.store.fills import FillStore
from legvise.store.inventory import InventoryStore
from legvise.store.plans import PlanStore

__all__ = ["group"]


@click.group("report")
def group() -> None:
    """Print and export what the scanner and the fills came to."""


@group.command("session")
@click.argument("session")
@click.option("--json", "as_json", is_flag=True, help="Print one object instead of a table.")
@click.pass_context
def session(ctx: click.Context, session: str, as_json: bool) -> None:
    """Print one session's summary."""
    context = app(ctx)
    found = summarise(PlanStore(context.db), session)
    if as_json:
        echo_json(session_payload(found))
        return
    click.echo(f"session     {found.session}")
    click.echo(f"started     {found.started_at}")
    click.echo(f"min edge    {bps_text(found.min_edge_bps)} bps")
    click.echo(f"plans       {found.plans}")
    click.echo(f"actionable  {found.actionable}")
    click.echo(f"trimmed     {found.trimmed}")
    click.echo(f"refused     {found.refused}")
    click.echo(f"hit rate    {bps_text(found.hit_rate, '0.0001')}")
    click.echo(f"notional    {found.total_notional}")
    if found.best_net_bps is not None:
        click.echo(f"best        {bps_text(found.best_net_bps)} bps")
    if found.clauses:
        echo_rows(
            [(line.code, str(line.hits), line.text) for line in found.clauses],
            ("clause", "hits", "says"),
        )


@group.command("edge")
@click.option("--session", "session_ref", default=None, help="One session, or every plan.")
@click.option("--json", "as_json", is_flag=True, help="Print one object instead of a table.")
@click.pass_context
def edge(ctx: click.Context, session_ref: str | None, as_json: bool) -> None:
    """Print expected against realised, weighted by notional."""
    context = app(ctx)
    report = build_edge_report(
        PlanStore(context.db), FillStore(context.db), session_ref=session_ref
    )
    if as_json:
        echo_json(edge_payload(report))
        return
    click.echo(f"plans        {report.plans}")
    click.echo(f"notional     {report.total_notional}")
    click.echo(f"expected     {bps_text(report.expected_bps)} bps")
    click.echo(f"realised     {bps_text(report.realised_bps)} bps")
    click.echo(f"gap          {bps_text(report.gap_bps)} bps")
    click.echo(f"price drift  {bps_text(report.price_drift_bps)} bps")
    click.echo(f"fee drift    {bps_text(report.fee_drift_bps)} bps")
    click.echo(f"made         {bps_text(report.realised_amount, '0.00000001')}")
    for ref in report.leg_risk_plans:
        click.echo(f"LEG RISK     {ref}", err=True)


@group.command("export")
@click.argument("session")
@click.option(
    "--format",
    "shape",
    type=click.Choice(["csv", "json"]),
    default="csv",
    show_default=True,
    help="CSV for the spreadsheet, JSON for the dashboard.",
)
@out_option
@click.pass_context
def export(ctx: click.Context, session: str, shape: str, target: Path | None) -> None:
    """Write one session's plans out for the risk spreadsheet."""
    context = app(ctx)
    store = PlanStore(context.db)
    with writing_to(target) as handle:
        if shape == "csv":
            count = write_csv(handle, plan_rows(store.for_session(session)), PLAN_FIELDS)
        else:
            count = write_session_json(handle, summarise(store, session))["plans"]
    if target is not None and not context.quiet:
        click.echo(f"wrote {count} plans to {target}")


@group.command("export-edge")
@click.option("--session", "session_ref", default=None, help="One session, or every plan.")
@out_option
@click.pass_context
def export_edge(ctx: click.Context, session_ref: str | None, target: Path | None) -> None:
    """Export the edge report as JSON."""
    context = app(ctx)
    report = build_edge_report(
        PlanStore(context.db), FillStore(context.db), session_ref=session_ref
    )
    with writing_to(target) as handle:
        write_edge_json(handle, report)
    if target is not None and not context.quiet:
        click.echo(f"wrote {report.plans} plans to {target}")


@group.command("inventory")
@click.option("--asset", default=None, help="Only this asset.")
@click.pass_context
def inventory(ctx: click.Context, asset: str | None) -> None:
    """Print how far each holding is from its target, and what would square it.

    The net move is the number to read. Per venue gaps mostly cancel, and what
    is left is what actually has to be bought or sold rather than transferred.
    """
    context = app(ctx)
    store = InventoryStore(context.db)
    assets = (asset_code(asset),) if asset else store.assets_held()
    positions = tuple(p for held in assets for p in store.positions_of(held))
    bands = {
        position.key: band
        for position in positions
        if (band := store.band(position.venue, position.asset)) is not None
    }
    found = build_inventory_report(positions, bands)
    rows = [
        (
            gap.venue,
            gap.asset,
            str(gap.held),
            str(gap.target),
            str(gap.gap),
            gap.state,
        )
        for plan in found.plans
        for gap in plan.gaps
    ]
    echo_rows(rows, ("venue", "asset", "held", "target", "gap", "state"))
    for plan in found.plans:
        if plan.is_square:
            continue
        click.echo(
            f"{plan.asset}: transfer {plan.transferable}, then"
            f" {'sell' if plan.net_move > 0 else 'buy'} {abs(plan.net_move)}"
        )


@group.command("desk")
@click.option("--json", "as_json", is_flag=True, help="Print one object instead of a table.")
@click.pass_context
def desk(ctx: click.Context, as_json: bool) -> None:
    """Say whether the desk is set up well enough to scan, and what is missing.

    The gaps are the point. A scan that silently uses four of five venues looks
    exactly like one that used all five, and this is the command that would have
    said otherwise.
    """
    context = app(ctx)
    status = build_desk_status(context.db)
    if as_json:
        echo_json(desk_payload(status))
        if not status.can_scan:
            raise click.ClickException("the desk is not ready to scan")
        return
    rows = [
        (
            venue.code,
            "on" if venue.active else "off",
            str(venue.markets),
            str(venue.books),
            "ready" if venue.is_ready else "not ready",
        )
        for venue in status.venues
    ]
    echo_rows(rows, ("venue", "state", "markets", "books", "verdict"))
    click.echo(f"shared markets  {len(status.shared_symbols)}")
    click.echo(f"sessions        {status.sessions}")
    click.echo(f"last session    {status.last_session or 'none yet'}")
    for gap in status.gaps:
        click.echo(f"missing         {gap}", err=True)
    if not status.can_scan:
        raise click.ClickException("the desk is not ready to scan")
    if not context.quiet:
        click.echo("the desk is ready to scan")


@group.command("export-legs")
@click.argument("session")
@click.option(
    "--out",
    "target",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Where to write it. Standard output if not given.",
)
@click.option("--actionable", is_flag=True, help="Skip the legs of refused plans.")
@click.pass_context
def export_legs(ctx: click.Context, session: str, target: Path | None, actionable: bool) -> None:
    """Export one session's legs, one row per order.

    A venue statement is per order and a plan is two of them, so reconciling a
    plan export against one means doing the pairing by hand.
    """
    context = app(ctx)
    store = PlanStore(context.db)
    plans = store.actionable(session) if actionable else store.for_session(session)
    with writing_to(target) as handle:
        count = write_csv(handle, leg_rows(plans), LEG_FIELDS)
    if target is not None and not context.quiet:
        click.echo(f"wrote {count} legs to {target}")


@group.command("venues")
@click.option("--sessions", type=int, default=20, show_default=True, help="How far back to look.")
@click.pass_context
def venues(ctx: click.Context, sessions: int) -> None:
    """Say which venues are earning their place over recent sessions.

    The clause column is the one to read. A venue refused on STALE.01 has a feed
    problem; one refused on DEPTH.02 is simply too thin for the size the desk
    trades, and those want different answers.
    """
    context = app(ctx)
    report = build_venue_report(PlanStore(context.db), sessions=sessions)
    rows = [
        (
            line.venue,
            str(line.plans),
            str(line.actionable),
            str(line.refused),
            str(line.notional),
            bps_text(line.hit_rate, "0.0001"),
            line.worst_clause or "",
        )
        for line in report.lines
    ]
    echo_rows(rows, ("venue", "plans", "sendable", "refused", "notional", "hit_rate", "worst"))
    for venue in report.idle:
        click.echo(f"{venue} never reached a sendable plan", err=True)
