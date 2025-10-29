"""Reachability from the command tree."""

from __future__ import annotations

from legvise.tools.check_wiring import ENTRY_POINTS, orphans, problems, reachable


def test_nothing_in_the_package_is_orphaned() -> None:
    assert problems() == []
    assert orphans() == ()


def test_the_entry_point_is_the_command_tree() -> None:
    assert ENTRY_POINTS == ("legvise.cli.main",)


def test_the_walk_reaches_the_command_groups() -> None:
    live = reachable()
    for group in ("book", "fee", "instrument", "inventory", "loop", "plan", "scan", "venue"):
        assert f"legvise.cli.{group}" in live


def test_the_walk_reaches_the_pricing_path() -> None:
    live = reachable()
    for module in (
        "legvise.market.depth",
        "legvise.market.staleness",
        "legvise.fees.quote",
        "legvise.risk.caps",
        "legvise.scan.direct",
        "legvise.scan.sizer",
    ):
        assert module in live


def test_the_walk_reaches_the_store() -> None:
    live = reachable()
    for module in ("legvise.store.db", "legvise.store.plans", "legvise.store.fills"):
        assert module in live


def test_the_walk_reaches_the_base_layer() -> None:
    live = reachable()
    for module in ("legvise.errors", "legvise.money", "legvise.ids", "legvise.rules"):
        assert module in live


def test_an_entry_point_nobody_wrote_reaches_nothing() -> None:
    assert reachable(("legvise.nowhere",)) == set()


def test_starting_from_one_module_reaches_only_what_it_needs() -> None:
    live = reachable(("legvise.money",))
    assert "legvise.money" in live
    assert "legvise.errors" in live
    assert "legvise.store.db" not in live


def test_the_checks_themselves_are_not_expected_to_be_reachable() -> None:
    assert "legvise.tools.check_wiring" not in reachable()
    assert "legvise.tools.check_wiring" not in orphans()
