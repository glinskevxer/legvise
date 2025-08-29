"""Finding profitable conversion loops inside one venue.

The textbook answer is Bellman-Ford over negative log rates, and it is the wrong
one here for two reasons. It finds *a* negative cycle rather than all of them,
and the desk wants every loop it could take ranked, not one. And it needs
logarithms, which on `Decimal` means either dropping to float -- reintroducing
exactly the precision the rest of this package refuses -- or carrying a log
implementation nobody wants to own.

So this walks the graph exhaustively instead, bounded by `max_length`. That is
only reasonable because the bound is real: a desk does not send five leg loops,
because each leg is another chance for the book to move underneath it, and the
edge that survives five sets of fees is not there. At three and four hops the
search is small enough to run inside the pairing window on every venue.

Cycles are deduplicated by their rotation. USD to BTC to ETH to USD and BTC to
ETH to USD to BTC are the same loop entered at different points, and reporting
both would triple the operator's reading for no information.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from legvise.errors import BadArgument
from legvise.ids import Symbol
from legvise.model.book import Book
from legvise.model.cycle import Cycle, Hop
from legvise.money import ZERO

__all__ = ["Edge", "build_graph", "find_cycles", "profitable_cycles"]

MAX_SUPPORTED_LENGTH = 5


class Edge(tuple[str, Symbol, Decimal]):
    """One directed conversion available at the touch: to asset, market, price."""

    __slots__ = ()

    @property
    def to_asset(self) -> str:
        """Where the hop lands."""
        return self[0]

    @property
    def symbol(self) -> Symbol:
        """The market the hop trades on."""
        return self[1]

    @property
    def price(self) -> Decimal:
        """The touch price the hop would pay."""
        return self[2]


Graph = dict[str, list[Edge]]


def build_graph(books: tuple[Book, ...]) -> Graph:
    """Turn a venue's two sided books into a directed conversion graph.

    Each market contributes two edges: sell the base at the bid, buy the base at
    the ask. A one sided book contributes only the direction it can support.
    """
    graph: Graph = defaultdict(list)
    for book in books:
        best_bid = book.best_bid
        best_ask = book.best_ask
        if best_bid is not None:
            graph[book.symbol.base].append(Edge((book.symbol.quote, book.symbol, best_bid.price)))
        if best_ask is not None:
            graph[book.symbol.quote].append(Edge((book.symbol.base, book.symbol, best_ask.price)))
    return {
        asset: sorted(edges, key=lambda e: (e.to_asset, str(e.symbol)))
        for asset, edges in graph.items()
    }


def find_cycles(graph: Graph, venue: str, *, start: str, max_length: int = 3) -> tuple[Cycle, ...]:
    """Every simple loop from `start` back to `start`, up to `max_length` hops."""
    if max_length < 3:
        raise BadArgument("max_length", max_length, "a cycle is three hops or more")
    if max_length > MAX_SUPPORTED_LENGTH:
        raise BadArgument(
            "max_length", max_length, f"the search is bounded at {MAX_SUPPORTED_LENGTH} hops"
        )
    found: list[Cycle] = []
    _walk(graph, venue, start, start, (), set(), max_length, found)
    return tuple(found)


def _walk(
    graph: Graph,
    venue: str,
    start: str,
    here: str,
    hops: tuple[Hop, ...],
    seen: set[str],
    budget: int,
    out: list[Cycle],
) -> None:
    if len(hops) >= budget:
        return
    for edge in graph.get(here, []):
        if edge.to_asset == start and len(hops) + 1 >= 3:
            out.append(Cycle(venue=venue, hops=(*hops, Hop(here, start, edge.symbol, edge.price))))
            continue
        if edge.to_asset in seen or edge.to_asset == start:
            continue
        _walk(
            graph,
            venue,
            start,
            edge.to_asset,
            (*hops, Hop(here, edge.to_asset, edge.symbol, edge.price)),
            seen | {edge.to_asset},
            budget,
            out,
        )


def profitable_cycles(
    venue: str,
    books: tuple[Book, ...],
    *,
    start: str,
    min_bps: Decimal = ZERO,
    max_length: int = 3,
) -> tuple[Cycle, ...]:
    """Loops from `start` whose gross edge clears `min_bps`, best first."""
    graph = build_graph(books)
    candidates = find_cycles(graph, venue, start=start, max_length=max_length)
    keepers = [cycle for cycle in candidates if cycle.gross_bps >= min_bps]
    return tuple(sorted(keepers, key=lambda c: (-c.gross_bps, c.length, c.assets)))


def starting_assets(graph: Graph) -> tuple[str, ...]:
    """Every asset the graph can leave from, in order."""
    return tuple(sorted(graph))
