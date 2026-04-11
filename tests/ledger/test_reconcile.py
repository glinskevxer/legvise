"""What the desk records against what the venue reports."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.ledger.reconcile import reconcile
from legvise.model.inventory import Position
from legvise.money import dec

AS_OF = "2026-04-14T09:00:00+00:00"


def holding(venue: str, asset: str, free: str, locked: str = "0") -> Position:
    return Position.build(venue, asset, free=free, locked=locked, as_of=AS_OF)


def ours() -> tuple[Position, ...]:
    return (holding("kraken", "BTC", "5"), holding("kraken", "USD", "400000"))


def test_two_sides_that_agree_report_no_material_difference() -> None:
    found = reconcile(ours(), {("kraken", "BTC"): dec("5"), ("kraken", "USD"): dec("400000")})
    assert found.agrees
    assert found.worst() is None


def test_every_key_appears_even_when_it_agrees() -> None:
    found = reconcile(ours(), {("kraken", "BTC"): dec("5"), ("kraken", "USD"): dec("400000")})
    assert len(found.differences) == 2


def test_a_drift_the_venue_is_ahead_on_reads_as_more() -> None:
    found = reconcile(ours(), {("kraken", "BTC"): dec("5.5"), ("kraken", "USD"): dec("400000")})
    difference = next(item for item in found.differences if item.asset == "BTC")
    assert difference.drift == dec("0.5")
    assert difference.direction == "venue holds more"


def test_a_drift_the_desk_is_ahead_on_reads_as_less() -> None:
    found = reconcile(ours(), {("kraken", "BTC"): dec("4"), ("kraken", "USD"): dec("400000")})
    difference = next(item for item in found.differences if item.asset == "BTC")
    assert difference.direction == "venue holds less"


def test_an_exact_match_reads_as_agreed() -> None:
    found = reconcile(ours(), {("kraken", "BTC"): dec("5"), ("kraken", "USD"): dec("400000")})
    assert all(item.direction == "agreed" for item in found.differences)


def test_locked_balance_counts_toward_the_desk_side() -> None:
    with_locked = (holding("kraken", "BTC", "2", "3"),)
    found = reconcile(with_locked, {("kraken", "BTC"): dec("5")})
    assert found.agrees


def test_a_balance_only_the_venue_knows_about_is_reported() -> None:
    found = reconcile(ours(), {("kraken", "SOL"): dec("100")})
    missing = found.missing_from_ours
    assert len(missing) == 1
    assert missing[0].asset == "SOL"


def test_a_balance_only_the_desk_knows_about_is_reported() -> None:
    found = reconcile(ours(), {})
    assert len(found.missing_from_theirs) == 2


def test_a_drift_inside_the_tolerance_is_not_material() -> None:
    found = reconcile(
        ours(),
        {("kraken", "BTC"): dec("5.0000001"), ("kraken", "USD"): dec("400000")},
        {"BTC": dec("0.000001")},
    )
    assert found.agrees


def test_a_drift_outside_the_tolerance_is_material() -> None:
    found = reconcile(
        ours(),
        {("kraken", "BTC"): dec("5.01"), ("kraken", "USD"): dec("400000")},
        {"BTC": dec("0.000001")},
    )
    assert not found.agrees
    assert len(found.material) == 1


def test_the_tolerance_is_per_asset() -> None:
    found = reconcile(
        ours(),
        {("kraken", "BTC"): dec("5.0001"), ("kraken", "USD"): dec("400001")},
        {"BTC": dec("0.001"), "USD": dec("0.5")},
    )
    assert len(found.material) == 1
    assert found.material[0].asset == "USD"


def test_the_worst_difference_is_the_biggest_drift() -> None:
    found = reconcile(
        ours(),
        {("kraken", "BTC"): dec("6"), ("kraken", "USD"): dec("400010")},
    )
    worst = found.worst()
    assert worst is not None
    assert worst.asset == "USD"


def test_a_negative_tolerance_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        reconcile(ours(), {}, {"BTC": dec("-1")})
    assert caught.value.field == "tolerances"


def test_the_differences_come_back_in_a_stable_order() -> None:
    first = reconcile(ours(), {("okx", "ETH"): dec("1")})
    second = reconcile(ours(), {("okx", "ETH"): dec("1")})
    assert [item.asset for item in first.differences] == [item.asset for item in second.differences]


def test_reconciling_nothing_against_nothing_agrees() -> None:
    found = reconcile((), {})
    assert found.agrees
    assert found.differences == ()
