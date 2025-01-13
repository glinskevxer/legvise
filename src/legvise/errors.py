"""Every refusal the package makes has a type here.

Two rules hold across the whole tree. A refusal always names the thing it
refused, so an operator reading a log does not have to guess which venue or
which symbol was involved. And a refusal never carries a formatted sentence
that the caller then has to parse back apart; the parts stay separate on the
exception and the message is assembled from them.
"""

from __future__ import annotations

__all__ = [
    "BadArgument",
    "Conflict",
    "LegviseError",
    "NotFound",
    "Refused",
    "StaleData",
]


class LegviseError(Exception):
    """Base for everything the package raises on purpose."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(LegviseError):
    """A record the caller named is not in the store."""

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"no {kind} with key {key!r}")
        self.kind = kind
        self.key = key


class Conflict(LegviseError):
    """A record the caller is creating is already there."""

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"{kind} {key!r} already exists")
        self.kind = kind
        self.key = key


class BadArgument(LegviseError):
    """A value handed in cannot be used at all, whatever the state of the desk."""

    def __init__(self, field: str, value: object, why: str) -> None:
        super().__init__(f"{field} {value!r} is not usable: {why}")
        self.field = field
        self.value = value
        self.why = why


class Refused(LegviseError):
    """The desk's own rules say no to something that is otherwise well formed."""

    def __init__(self, subject: str, why: str) -> None:
        super().__init__(f"refused {subject}: {why}")
        self.subject = subject
        self.why = why


class StaleData(LegviseError):
    """A book or a balance is older than the budget allows it to be."""

    def __init__(self, subject: str, age_ms: int, budget_ms: int) -> None:
        super().__init__(f"{subject} is {age_ms}ms old, budget is {budget_ms}ms")
        self.subject = subject
        self.age_ms = age_ms
        self.budget_ms = budget_ms
