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
from legvise.settings import resolve, settled
from legvise.store.db import copy_into_memory
from legvise.store.networks import NetworkStore
from legvise.store.plans import PlanStore

__all__ = ["group"]


@click.group("scan")
def group() -> None:
    """Run the scanner and read what it found."""


@group.command("run")
@click.option("--min-edge-bps", default=None, help="Floor for the net edge.")
@click.option("--window-ms", type=int, default=None, help="How far apart two books may be.")
@click.option("--size", default=None, help="Base size the desk wants per leg.")
@click.option("--venue-cap", default=None, help="Notional cap per venue.")
@click.option("--asset-cap", default=None, help="Net cap per asset.")
@click.option("--gross-cap", default=None, help="Desk wide hard stop.")
@click.option("--carry-bps-hour", default=None, help="Charge for capital in flight.")
@click.option("--cycles", type=int, default=None, help="Plans one transfer serves.")
@click.option("--stranded-bps", default=None, help="Charge when no route is open.")
@click.option(
    "--counter", type=int, default=0, show_default=True, help="Session number for the day."
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Price everything against a throwaway copy and write nothing.",
)
@click.pass_context
def run(
    ctx: click.Context,
    min_edge_bps: str | None,
    window_ms: int | None,
    size: str | None,
    venue_cap: str | None,
    asset_cap: str | None,
    gross_cap: str | None,
    carry_bps_hour: str | None,
    cycles: int | None,
    stranded_bps: str | None,
    counter: int,
    dry_run: bool,
) -> None:
    """Scan every market that is live on two or more venues.

    Every number here comes from the settings file when `--config` named one,
    and from what the tool ships with otherwise. A flag beats both, for this
    run only. `legvise config show` says which level each one came from.

    With `--dry-run` the whole scan runs against a throwaway copy of the book,
    so an operator can try a different edge floor or a different size without
    leaving a session behind. The numbers are the same; nothing is written.
    """
    context = app(ctx)
    chosen = settled(
        resolve(
            from_file=context.settings,
            from_flags={
                "min_edge_bps": min_edge_bps,
                "window_ms": window_ms,
                "size": size,
                "venue_cap": venue_cap,
                "asset_cap": asset_cap,
                "gross_cap": gross_cap,
                "carry_bps_hour": carry_bps_hour,
                "cycles": cycles,
                "stranded_bps": stranded_bps,
            },
        )
    )
    target = context.db
    if dry_run:
        # Closed when the command finishes rather than left to the garbage
        # collector. An unclosed sqlite3 handle is a warning on 3.13 and a held
        # file handle on every version, and the copy is opened per invocation,
        # so a scheduler polling with `--dry-run` leaks one each time.
        target = copy_into_memory(context.db)
        ctx.call_on_close(target.close)
    scanner = Scanner(
        db=target,
        clock=context.clock,
        terms=ScanTerms(
            min_edge_bps=dec(str(chosen.min_edge_bps), field="min_edge_bps"),
            pairing_window_ms=chosen.window_ms,
            wanted_size=dec(str(chosen.size), field="size"),
        ),
        caps=CapSet(
            venue_cap=dec(str(chosen.venue_cap), field="venue_cap"),
            venue_used=dec("0"),
            asset_cap=dec(str(chosen.asset_cap), field="asset_cap"),
            asset_used=dec("0"),
            gross_cap=dec(str(chosen.gross_cap), field="gross_cap"),
            gross_used=dec("0"),
        ),
        pricer=StoreRebalancePricer(
            networks=NetworkStore(target),
            terms=CarryTerms(
                carry_bps_per_hour=dec(str(chosen.carry_bps_hour), field="carry_bps_hour"),
                cycles_served=chosen.cycles,
            ),
            stranded_bps=dec(str(chosen.stranded_bps), field="stranded_bps"),
        ),
    )
    report = scanner.run(counter=counter)
    if dry_run:
        click.echo("dry run     nothing was written")
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
