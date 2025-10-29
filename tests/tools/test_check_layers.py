"""The layering rule, and that the package obeys it."""

from __future__ import annotations

import pytest

from legvise.tools.check_layers import LAYERS, layer_of, problems, summary


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
