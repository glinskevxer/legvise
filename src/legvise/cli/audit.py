"""Commands for reading the decision ledger a scan leaves behind."""

from __future__ import annotations

import click

from legvise.cli.options import app, echo_rows
from legvise.model.audit import Stage
from legvise.store.decisions import DecisionStore

__all__ = ["group"]


@click.group("audit")
def group() -> None:
    """Read what the scanner decided, including what it never priced."""


@group.command("session")
@click.argument("session")
@click.option(
    "--stage",
    type=click.Choice([stage.value for stage in Stage]),
    default=None,
    help="Only decisions taken at this stage.",
)
@click.option("--limit", type=int, default=50, show_default=True, help="Most rows to print.")
@click.pass_context
def session(ctx: click.Context, session: str, stage: str | None, limit: int) -> None:
    """List the decisions a session took, in the order it took them."""
    context = app(ctx)
    store = DecisionStore(context.db)
    taken = store.at_stage(session, Stage(stage)) if stage else store.for_session(session)
    rows = [
        (
            str(decision.sequence),
            decision.stage.value,
            decision.subject,
            decision.clause or "",
            decision.detail,
        )
        for decision in taken[:limit]
    ]
    echo_rows(rows, ("seq", "stage", "subject", "clause", "detail"))
    if len(taken) > limit and not context.quiet:
        click.echo(f"{len(taken) - limit} more not shown", err=True)


@group.command("stages")
@click.argument("session")
@click.pass_context
def stages(ctx: click.Context, session: str) -> None:
    """Count what each stage of a session decided, busiest first."""
    context = app(ctx)
    counts = DecisionStore(context.db).stage_counts(session)
    rows = [(name, str(hits)) for name, hits in counts.items()]
    echo_rows(rows, ("stage", "decisions"))
    if not counts and not context.quiet:
        click.echo(f"{session} took no decisions", err=True)


@group.command("shape")
@click.argument("session")
@click.pass_context
def shape(ctx: click.Context, session: str) -> None:
    """Print how much of a session was cheap screening and how much was pricing.

    A healthy scan is nearly all cheap stages. One where the expensive stages
    are a large share is one whose screen is letting through pairs that were
    never going to price, and that shows up as a scan that misses its window
    long before it shows up as a wrong number.
    """
    context = app(ctx)
    taken = DecisionStore(context.db).require_any(session)
    cheap = sum(1 for decision in taken if decision.stage.costs_nothing)
    negative = sum(1 for decision in taken if decision.is_negative)
    click.echo(f"decisions   {len(taken)}")
    click.echo(f"cheap       {cheap}")
    click.echo(f"expensive   {len(taken) - cheap}")
    click.echo(f"negative    {negative}")
    click.echo(f"cheap share {cheap * 100 // len(taken)}%")


@group.command("clauses")
@click.argument("session")
@click.pass_context
def clauses(ctx: click.Context, session: str) -> None:
    """Count the clauses the decision ledger recorded for a session."""
    context = app(ctx)
    refused = DecisionStore(context.db).at_stage(session, Stage.REFUSED)
    counts: dict[str, int] = {}
    for decision in refused:
        if decision.clause is not None:
            counts[decision.clause] = counts.get(decision.clause, 0) + 1
    rows = [
        (code, str(hits))
        for code, hits in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    echo_rows(rows, ("clause", "hits"))
