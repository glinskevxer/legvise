"""Commands that run a scan and read the sessions it produced."""

from __future__ import annotations

import click

from legvise.cli.options import app, echo_rows
from legvise.money import dec
from legvise.risk.caps import CapSet
from legvise.routing.pricer import StoreRebalancePricer
from legvise.routing.rebalance import CarryTerms
from legvise.scan.direct import ScanTerms
from legvise.scan.session import Scanner
from legvise.store.networks import NetworkStore
from legvise.store.plans import PlanStore

__all__ = ["group"]


@click.group("scan")
def group() -> None:
    """Run the scanner and read what it found."""


@group.command("run")
@click.option("--min-edge-bps", default="2", show_default=True, help="Floor for the net edge.")
@click.option("--window-ms", type=int, default=250, show_default=True, help="Pairing window.")
@click.option("--size", default="1", show_default=True, help="Base size the desk wants per leg.")
@click.option("--venue-cap", default="250000", show_default=True, help="Notional cap per venue.")
@click.option("--asset-cap", default="400000", show_default=True, help="Net cap per asset.")
@click.option("--gross-cap", default="1000000", show_default=True, help="Desk wide hard stop.")
@click.option(
    "--carry-bps-hour", default="6", show_default=True, help="Charge for capital in flight."
)
@click.option(
    "--cycles", type=int, default=10, show_default=True, help="Plans one transfer serves."
)
@click.option(
    "--stranded-bps", default="250", show_default=True, help="Charge when no route is open."
)
@click.option(
    "--counter", type=int, default=0, show_default=True, help="Session number for the day."
)
@click.pass_context
def run(
    ctx: click.Context,
    min_edge_bps: str,
    window_ms: int,
    size: str,
    venue_cap: str,
    asset_cap: str,
    gross_cap: str,
    carry_bps_hour: str,
    cycles: int,
    stranded_bps: str,
    counter: int,
) -> None:
    """Scan every market that is live on two or more venues."""
    context = app(ctx)
    scanner = Scanner(
        db=context.db,
        clock=context.clock,
        terms=ScanTerms(
            min_edge_bps=dec(min_edge_bps, field="min_edge_bps"),
            pairing_window_ms=window_ms,
            wanted_size=dec(size, field="size"),
        ),
        caps=CapSet(
            venue_cap=dec(venue_cap, field="venue_cap"),
            venue_used=dec("0"),
            asset_cap=dec(asset_cap, field="asset_cap"),
            asset_used=dec("0"),
            gross_cap=dec(gross_cap, field="gross_cap"),
            gross_used=dec("0"),
        ),
        pricer=StoreRebalancePricer(
            networks=NetworkStore(context.db),
            terms=CarryTerms(
                carry_bps_per_hour=dec(carry_bps_hour, field="carry_bps_hour"),
                cycles_served=cycles,
            ),
            stranded_bps=dec(stranded_bps, field="stranded_bps"),
        ),
    )
    report = scanner.run(counter=counter)
    click.echo(f"session     {report.session}")
    click.echo(f"symbols     {report.symbols_considered}")
    click.echo(f"priced      {report.pairs_priced}")
    click.echo(f"actionable  {report.actionable}")
    for clause, hits in report.refusals.items():
        click.echo(f"refused     {clause} x{hits}")
    for note in report.skipped:
        click.echo(f"skipped     {note}", err=True)


@group.command("sessions")
@click.option("--limit", type=int, default=20, show_default=True, help="How many to list.")
@click.pass_context
def sessions(ctx: click.Context, limit: int) -> None:
    """List recent scan sessions, newest first."""
    context = app(ctx)
    store = PlanStore(context.db)
    rows = [
        (
            row.ref,
            row.started_at,
            str(row.min_edge_bps),
            str(row.pairing_window_ms),
            str(len(store.for_session(row.ref))),
            str(len(store.actionable(row.ref))),
        )
        for row in store.sessions(limit=limit)
    ]
    echo_rows(rows, ("session", "started", "min_edge", "window_ms", "plans", "actionable"))


@group.command("refusals")
@click.option("--session", "session_ref", default=None, help="One session, or every one.")
@click.pass_context
def refusals(ctx: click.Context, session_ref: str | None) -> None:
    """Count how often each clause turned a plan down."""
    context = app(ctx)
    counts = PlanStore(context.db).refusal_counts(session_ref)
    rows = [(clause, str(hits)) for clause, hits in counts.items()]
    echo_rows(rows, ("clause", "hits"))
