"""Identifiers the desk uses in its own records, and the rules they obey.

Venues, assets and instruments are named by the desk, not by the venue. Every
exchange spells the same pair differently -- `BTCUSD`, `BTC-USD`, `XBT/USD`,
`btcusdt` -- and letting those spellings loose in the store means two rows for
one market. The desk's spelling is the canonical one and the venue's own string
lives beside it as an alias.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple

from legvise.errors import BadArgument

__all__ = [
    "Symbol",
    "asset_code",
    "parse_symbol",
    "plan_ref",
    "session_ref",
    "symbol_text",
    "venue_code",
]

_VENUE_RE: Final = re.compile(r"^[a-z][a-z0-9_]{2,23}$")
_ASSET_RE: Final = re.compile(r"^[A-Z0-9]{2,12}$")
_SEP: Final = "-"


class Symbol(NamedTuple):
    """A market, spelled the desk's way: base first, quote second, hyphen between."""

    base: str
    quote: str

    def __str__(self) -> str:
        return f"{self.base}{_SEP}{self.quote}"

    def inverted(self) -> Symbol:
        """The same pair seen from the other side."""
        return Symbol(self.quote, self.base)


def venue_code(text: str) -> str:
    """Normalise a venue code, or refuse it.

    Lower case, starts with a letter, and long enough that `b` cannot be a
    venue. The store keys on this, so a typo has to fail loudly here.
    """
    out = text.strip().lower()
    if not _VENUE_RE.match(out):
        raise BadArgument("venue", text, "expected 3 to 24 characters of a-z, 0-9 and _")
    return out


def asset_code(text: str) -> str:
    """Normalise an asset code, or refuse it."""
    out = text.strip().upper()
    if not _ASSET_RE.match(out):
        raise BadArgument("asset", text, "expected 2 to 12 characters of A-Z and 0-9")
    return out


def parse_symbol(text: str) -> Symbol:
    """Read `BASE-QUOTE` into a `Symbol`, refusing anything else."""
    raw = text.strip()
    if raw.count(_SEP) != 1:
        raise BadArgument("symbol", text, f"expected exactly one {_SEP!r}")
    base, quote = raw.split(_SEP)
    base = asset_code(base)
    quote = asset_code(quote)
    if base == quote:
        raise BadArgument("symbol", text, "a market cannot quote an asset in itself")
    return Symbol(base, quote)


def symbol_text(symbol: Symbol) -> str:
    """The canonical spelling of a symbol, for a key or a log line."""
    return str(symbol)


def session_ref(started_at: str, counter: int) -> str:
    """A readable handle for one scan session, unique within a day."""
    if counter < 0:
        raise BadArgument("counter", counter, "a session counter starts at zero")
    day = started_at[:10].replace("-", "")
    if len(day) != 8 or not day.isdigit():
        raise BadArgument("started_at", started_at, "expected an ISO timestamp")
    return f"S{day}.{counter:04d}"


def plan_ref(session: str, index: int) -> str:
    """A readable handle for one plan inside a session."""
    if index < 0:
        raise BadArgument("index", index, "a plan index starts at zero")
    if not session.startswith("S"):
        raise BadArgument("session", session, "expected a session reference")
    return f"{session}/P{index:03d}"
