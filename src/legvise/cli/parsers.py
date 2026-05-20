"""Reading the colon separated options the command tree takes.

Six commands take a repeated option of the form `A:B` or `A:B:C` -- a fee rung,
a mark price, a venue weight, a holding, a tolerance, a book level. Each one had
its own three line splitter with its own error message, which meant six places
to fix when the message was wrong and six chances to spell the shape
differently in the help text.

They are one function now, and the shape it was given is what the error quotes.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import click

from legvise.errors import LegviseError
from legvise.ids import asset_code, venue_code
from legvise.money import dec

__all__ = [
    "decimal_map",
    "pair_map",
    "split_on_colons",
    "triple",
    "triple_map",
    "venue_map",
]


def split_on_colons(entry: str, shape: str) -> tuple[str, ...]:
    """Split an option value, refusing anything that is not the named shape.

    `shape` is the spelling the help text uses, so the error and the help agree
    without either of them having to know about the other.
    """
    wanted = shape.count(":") + 1
    parts = entry.split(":")
    if len(parts) != wanted or not all(part.strip() for part in parts):
        raise click.BadParameter(f"expected {shape}, got {entry!r}")
    return tuple(part.strip() for part in parts)


def _convert(value: str, field: str) -> Decimal:
    try:
        return dec(value, field=field)
    except LegviseError as exc:
        raise click.BadParameter(exc.message) from exc


def decimal_map(
    given: tuple[str, ...],
    *,
    shape: str,
    key: Callable[[str], str],
    field: str,
) -> dict[str, Decimal]:
    """Read repeated `KEY:AMOUNT` options into one mapping.

    `key` normalises the left hand side, so a mark quoted as `btc` and one
    quoted as `BTC` land on the same entry rather than on two.
    """
    found: dict[str, Decimal] = {}
    for entry in given:
        left, right = split_on_colons(entry, shape)
        found[_normalise(key, left)] = _convert(right, field)
    return found


def _normalise(key: Callable[[str], str], value: str) -> str:
    try:
        return key(value)
    except LegviseError as exc:
        raise click.BadParameter(exc.message) from exc


def pair_map(given: tuple[str, ...], *, shape: str, field: str) -> dict[str, Decimal]:
    """Repeated `ASSET:AMOUNT` options, keyed by normalised asset code."""
    return decimal_map(given, shape=shape, key=asset_code, field=field)


def venue_map(given: tuple[str, ...], *, shape: str, field: str) -> dict[str, Decimal]:
    """Repeated `VENUE:AMOUNT` options, keyed by normalised venue code."""
    return decimal_map(given, shape=shape, key=venue_code, field=field)


def triple_map(given: tuple[str, ...], *, shape: str, field: str) -> dict[tuple[str, str], Decimal]:
    """Repeated `VENUE:ASSET:AMOUNT` options, keyed by both normalised codes."""
    found: dict[tuple[str, str], Decimal] = {}
    for entry in given:
        venue, asset, amount = split_on_colons(entry, shape)
        found[(_normalise(venue_code, venue), _normalise(asset_code, asset))] = _convert(
            amount, field
        )
    return found


def triple(entry: str, shape: str) -> tuple[str, str, str]:
    """One three part option value, typed as three rather than as many.

    `split_on_colons` cannot promise a length to the type checker, and a caller
    that needs exactly three gets this instead of an unpack the checker has to
    take on trust.
    """
    left, middle, right = split_on_colons(entry, shape)
    return (left, middle, right)
