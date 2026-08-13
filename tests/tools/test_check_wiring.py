"""Reachability from the command tree."""

from __future__ import annotations

from legvise.tools import check_wiring
from legvise.tools.check_wiring import ENTRY_POINTS, orphans, problems, reachable
from tests.tools.conftest import Pointer, a_module


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


# The sentence each check produces when it finds something. Against the real
# tree every check comes back clean, which is the point of having them and also
# means the branch that writes the message never runs. These point the check at
# a made up tree that is wrong in exactly one way.


ENTRY = ENTRY_POINTS[0]


def an_entry(imports: str = "") -> str:
    """The body of a command tree root that imports whatever it is given."""
    return '"""The root."""\n\n' + imports + "\n"


# A module nothing imports is dead code that passes its own tests, which makes
# it the quietest failure in the tree.


def test_a_module_nothing_imports_is_named(reading: Pointer) -> None:
    reading(
        check_wiring,
        a_module(an_entry(), ENTRY),
        a_module('"""Alone."""\n', "legvise.scan.stranded"),
    )
    assert check_wiring.problems() == [
        "legvise.scan.stranded is not reachable from the command tree"
    ]


def test_a_module_the_root_imports_is_reachable(reading: Pointer) -> None:
    reading(
        check_wiring,
        a_module(an_entry("import legvise.scan.wired\n"), ENTRY),
        a_module('"""Wired."""\n', "legvise.scan.wired"),
    )
    assert check_wiring.problems() == []


def test_reachability_follows_more_than_one_hop(reading: Pointer) -> None:
    reading(
        check_wiring,
        a_module(an_entry("import legvise.cli.middle\n"), ENTRY),
        a_module('"""Middle."""\n\nimport legvise.scan.deep\n', "legvise.cli.middle"),
        a_module('"""Deep."""\n', "legvise.scan.deep"),
    )
    assert check_wiring.problems() == []


def test_a_module_reached_only_by_a_dead_one_is_still_dead(reading: Pointer) -> None:
    reading(
        check_wiring,
        a_module(an_entry(), ENTRY),
        a_module('"""Dead."""\n\nimport legvise.scan.deeper\n', "legvise.cli.dead"),
        a_module('"""Deeper."""\n', "legvise.scan.deeper"),
    )
    assert len(check_wiring.problems()) == 2


def test_the_tools_are_exempt_from_the_wiring_rule(reading: Pointer) -> None:
    reading(
        check_wiring,
        a_module(an_entry(), ENTRY),
        a_module('"""A check."""\n', "legvise.tools.check_made_up"),
    )
    assert check_wiring.problems() == []


def test_the_orphans_come_back_in_name_order(reading: Pointer) -> None:
    reading(
        check_wiring,
        a_module(an_entry(), ENTRY),
        a_module('"""B."""\n', "legvise.scan.beta"),
        a_module('"""A."""\n', "legvise.scan.alpha"),
    )
    assert orphans() == ("legvise.scan.alpha", "legvise.scan.beta")


def test_an_entry_point_that_is_not_there_reaches_nothing(reading: Pointer) -> None:
    reading(check_wiring, a_module('"""Alone."""\n', "legvise.scan.stranded"))
    assert reachable() == set()
