"""Cross-venue arbitrage scanning for a desk that keeps inventory on every venue.

The package is deliberately small at the edges and thick in the middle. Nothing
here talks to an exchange. Books, fee ladders and balances are handed in, the
scanner prices what it is given, and the caller decides whether to send orders.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
