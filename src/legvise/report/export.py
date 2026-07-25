"""Writing reports out in the two formats the desk's other tools read.

CSV goes to the spreadsheet the risk team keeps. JSON goes to the dashboard.
Neither is negotiable and neither is interesting, so the only decisions here are
the ones that stop the files being wrong:

- decimals are written as their exact text, never through `float`, because a
  size that round-trips through IEEE 754 on the way to a spreadsheet is a size
  the spreadsheet cannot reconcile against the venue
- every row has the same keys in the same order, so a `diff` between two days'
  exports is readable
- the writer takes an open text handle rather than a path, so a caller can
  write to a string, a pipe or a file without this module knowing which
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import IO, Any

from legvise.errors import BadArgument
from legvise.model.plan import Plan
from legvise.report.desk_report import DeskStatus
from legvise.report.edge_report import EdgeReport
from legvise.report.session_report import SessionSummary

__all__ = [
    "LEG_FIELDS",
    "PLAN_FIELDS",
    "desk_payload",
    "edge_payload",
    "leg_rows",
    "plan_rows",
    "session_payload",
    "write_csv",
    "write_edge_json",
    "write_session_json",
]

PLAN_FIELDS = (
    "ref",
    "kind",
    "symbol",
    "status",
    "clause",
    "venues",
    "notional",
    "gross_bps",
    "fee_bps",
    "slippage_bps",
    "rebalance_bps",
    "net_bps",
)


LEG_FIELDS = (
    "plan_ref",
    "leg_index",
    "venue",
    "symbol",
    "side",
    "price",
    "size",
    "notional",
    "fee_bps",
    "fee_amount",
    "levels_swept",
    "slippage_bps",
)


def _text(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None:
        return ""
    return str(value)


def plan_rows(plans: Iterable[Plan]) -> list[dict[str, str]]:
    """Every plan as a flat row, keys in `PLAN_FIELDS` order."""
    return [
        {
            "ref": plan.ref,
            "kind": plan.kind.value,
            "symbol": str(plan.symbol),
            "status": plan.status.value,
            "clause": _text(plan.clause),
            "venues": "/".join(plan.venues),
            "notional": _text(plan.notional),
            "gross_bps": _text(plan.gross_bps),
            "fee_bps": _text(plan.fee_bps),
            "slippage_bps": _text(plan.slippage_bps),
            "rebalance_bps": _text(plan.rebalance_bps),
            "net_bps": _text(plan.net_bps),
        }
        for plan in plans
    ]


def leg_rows(plans: Iterable[Plan]) -> list[dict[str, str]]:
    """Every leg of every plan as a flat row, keys in `LEG_FIELDS` order.

    The plan export is what a risk team reconciles against; this is what a
    trader reconciles against, because a venue's own statement is per order and
    a plan is two of them.
    """
    return [
        {
            "plan_ref": plan.ref,
            "leg_index": str(index),
            "venue": leg.venue,
            "symbol": str(leg.symbol),
            "side": "buy" if leg.is_buy else "sell",
            "price": _text(leg.price),
            "size": _text(leg.size),
            "notional": _text(leg.notional),
            "fee_bps": _text(leg.fee_bps),
            "fee_amount": _text(leg.fee_amount),
            "levels_swept": str(leg.levels_swept),
            "slippage_bps": _text(leg.slippage_bps),
        }
        for plan in plans
        for index, leg in enumerate(plan.legs)
    ]


def write_csv(handle: IO[str], rows: list[dict[str, str]], fields: tuple[str, ...]) -> int:
    """Write rows as CSV and return how many went out."""
    missing = [name for row in rows for name in fields if name not in row]
    if missing:
        raise BadArgument("rows", missing[0], "every row needs every field")
    writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row[name] for name in fields})
    return len(rows)


def session_payload(summary: SessionSummary) -> dict[str, Any]:
    """One session summary as the shape every reader of it gets.

    The terminal and the exported file are the same bytes. They were two
    dictionaries once, written months apart, and they had already drifted: the
    printed one dropped the symbols and the venues and spelled the clauses as
    an object rather than a list. Anyone reconciling a dashboard against a
    saved export would have found the two disagreeing about a session that had
    not changed.
    """
    return {
        "session": summary.session,
        "started_at": summary.started_at,
        "min_edge_bps": _text(summary.min_edge_bps),
        "plans": summary.plans,
        "actionable": summary.actionable,
        "trimmed": summary.trimmed,
        "refused": summary.refused,
        "hit_rate": _text(summary.hit_rate),
        "total_notional": _text(summary.total_notional),
        "best_net_bps": _text(summary.best_net_bps),
        "symbols": [str(symbol) for symbol in summary.symbols],
        "venues": list(summary.venues),
        "clauses": [
            {"code": line.code, "hits": line.hits, "text": line.text} for line in summary.clauses
        ],
    }


def write_session_json(handle: IO[str], summary: SessionSummary) -> Mapping[str, Any]:
    """Write one session summary as JSON and return what was written."""
    payload = session_payload(summary)
    json.dump(payload, handle, indent=2, sort_keys=False)
    handle.write("\n")
    return payload


def edge_payload(report: EdgeReport) -> dict[str, Any]:
    """One edge report as the shape every reader of it gets."""
    return {
        "plans": report.plans,
        "total_notional": _text(report.total_notional),
        "expected_bps": _text(report.expected_bps),
        "realised_bps": _text(report.realised_bps),
        "gap_bps": _text(report.gap_bps),
        "price_drift_bps": _text(report.price_drift_bps),
        "fee_drift_bps": _text(report.fee_drift_bps),
        "realised_amount": _text(report.realised_amount),
        "leg_risk_plans": list(report.leg_risk_plans),
        "lines": [
            {
                "ref": line.plan.ref,
                "notional": _text(line.weight),
                "expected_bps": _text(line.attribution.expected_bps),
                "realised_bps": _text(line.attribution.realised_bps),
                "price_drift_bps": _text(line.attribution.price_drift_bps),
                "fee_drift_bps": _text(line.attribution.fee_drift_bps),
                "fill_ratio": _text(line.attribution.shortfall_ratio),
            }
            for line in report.lines
        ],
    }


def write_edge_json(handle: IO[str], report: EdgeReport) -> Mapping[str, Any]:
    """Write an edge report as JSON and return what was written."""
    payload = edge_payload(report)
    json.dump(payload, handle, indent=2, sort_keys=False)
    handle.write("\n")
    return payload


def desk_payload(status: DeskStatus) -> dict[str, Any]:
    """The desk readiness page as an object.

    `can_scan` is the field to branch on. The gaps say what is missing and the
    venue rows say where, but a caller that reads the rows and works out the
    verdict for itself will get a different answer from the one the tool acts
    on, which is the whole reason the verdict is a field.
    """
    return {
        "can_scan": status.can_scan,
        "venues": [
            {
                "venue": venue.code,
                "active": venue.active,
                "markets": venue.markets,
                "books": venue.books,
                "ready": venue.is_ready,
                "gaps": list(venue.gaps),
            }
            for venue in status.venues
        ],
        "shared_markets": [str(symbol) for symbol in status.shared_symbols],
        "sessions": status.sessions,
        "last_session": status.last_session,
        "gaps": list(status.gaps),
    }
