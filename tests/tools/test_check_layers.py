"""The layering rule, and that the package obeys it."""

from __future__ import annotations

import pytest

from legvise.tools import check_layers
from legvise.tools.check_layers import LAYERS, layer_of, problems, summary
from tests.tools.conftest import Pointer, a_module


def test_the_package_imports_only_downwards() -> None:
    assert problems() == []


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("legvise.errors", "base"),
        ("legvise.money", "base"),
        ("legvise.model.venue", "model"),
        ("legvise.store.db", "store"),
        ("legvise.market.depth", "domain"),
        ("legvise.fees.quote", "domain"),
        ("legvise.risk.caps", "domain"),
        ("legvise.routing.rebalance", "domain"),
        ("legvise.scan.direct", "scan"),
        ("legvise.ledger.attribution", "scan"),
        ("legvise.report.export", "report"),
        ("legvise.cli.main", "cli"),
        ("legvise.tools.walk", "tools"),
    ],
)
def test_each_module_lands_in_its_layer(module: str, expected: str) -> None:
    assert layer_of(module) == expected


def test_the_package_root_has_no_layer() -> None:
    assert layer_of("legvise") is None


def test_a_module_nobody_declared_has_no_layer() -> None:
    assert layer_of("legvise.something.new") is None


def test_the_layers_are_listed_lowest_first() -> None:
    names = [name for name, _ in LAYERS]
    assert names[0] == "base"
    assert names[-1] == "tools"
    assert names.index("model") < names.index("store")
    assert names.index("store") < names.index("cli")


def test_no_subpackage_belongs_to_two_layers() -> None:
    seen: set[str] = set()
    for _, parts in LAYERS:
        for part in parts:
            assert part not in seen
            seen.add(part)


def test_every_layer_has_at_least_one_module() -> None:
    counts = summary()
    for name, count in counts.items():
        assert count > 0, f"{name} is empty"


def test_the_store_layer_is_not_the_biggest_thing_in_the_package() -> None:
    counts = summary()
    assert counts["store"] < counts["base"] + counts["model"] + counts["domain"]


# What the check says when an import points the wrong way. The package never
# does, so this branch only runs against a module written to break it.


def test_an_import_up_the_layers_is_named(reading: Pointer) -> None:
    reading(check_layers, a_module("import legvise.cli.options\n", "legvise.model.thing"))
    assert problems() == [
        "legvise.model.thing (model) imports legvise.cli.options (cli), which is higher"
    ]


def test_a_from_import_is_read_as_the_module_it_names(reading: Pointer) -> None:
    # `imports()` reports the package and the dotted candidate both, because
    # the AST cannot tell `from legvise.cli import options` naming a module
    # from it naming a function. Both point up, so both come back.
    reading(check_layers, a_module("from legvise.cli import options\n", "legvise.model.thing"))
    found = problems()
    assert len(found) == 2
    assert any("legvise.cli.options" in line for line in found)


def test_an_import_down_the_layers_is_allowed(reading: Pointer) -> None:
    reading(check_layers, a_module("import legvise.money\n", "legvise.cli.thing"))
    assert problems() == []


def test_an_import_inside_one_layer_is_allowed(reading: Pointer) -> None:
    reading(check_layers, a_module("import legvise.model.book\n", "legvise.model.leg"))
    assert problems() == []


def test_a_module_in_the_tools_layer_may_import_anything(reading: Pointer) -> None:
    reading(check_layers, a_module("import legvise.cli.main\n", "legvise.tools.thing"))
    assert problems() == []


def test_an_import_of_something_outside_the_package_is_ignored(reading: Pointer) -> None:
    reading(check_layers, a_module("import json\n", "legvise.model.thing"))
    assert problems() == []


def test_the_package_root_belongs_to_no_layer() -> None:
    assert layer_of("legvise") is None


def test_a_module_can_break_the_rule_more_than_once(reading: Pointer) -> None:
    body = "import legvise.cli.options\nimport legvise.report.export\n"
    reading(check_layers, a_module(body, "legvise.model.thing"))
    assert len(problems()) == 2


def test_the_summary_counts_the_modules_it_was_given(reading: Pointer) -> None:
    reading(
        check_layers,
        a_module("x = 1\n", "legvise.model.one"),
        a_module("x = 1\n", "legvise.model.two"),
        a_module("x = 1\n", "legvise.cli.three"),
    )
    counted = summary()
    assert counted["model"] == 2
    assert counted["cli"] == 1
    assert counted["store"] == 0
