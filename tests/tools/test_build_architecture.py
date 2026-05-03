"""The generated layer map, and that it matches the imports."""

from __future__ import annotations

from legvise.tools.build_architecture import (
    OUTPUT,
    edges,
    is_current,
    main,
    modules_by_layer,
    render,
    target,
)
from legvise.tools.check_layers import LAYERS


def test_the_map_on_disk_is_current() -> None:
    assert is_current()


def test_the_map_lives_under_docs() -> None:
    assert OUTPUT == "docs/architecture.md"
    assert target().exists()


def test_the_map_says_it_is_generated() -> None:
    assert "Do not edit" in render()


def test_every_layer_gets_a_row_and_a_section() -> None:
    body = render()
    for name, _ in LAYERS:
        assert f"| `{name}` |" in body
        assert f"## `{name}`" in body


def test_every_module_appears_in_its_layer_section() -> None:
    body = render()
    for members in modules_by_layer().values():
        for module in members:
            assert f"- `{module}`" in body


def test_the_base_layer_depends_on_nothing() -> None:
    assert edges()["base"] == set()


def test_the_model_layer_depends_only_on_the_base() -> None:
    assert edges()["model"] == {"base"}


def test_the_store_layer_does_not_reach_up_into_the_domain() -> None:
    assert "domain" not in edges()["store"]


def test_the_command_tree_depends_on_everything_below_it() -> None:
    depends = edges()["cli"]
    assert {"base", "model", "store", "domain", "scan", "report"} <= depends


def test_no_layer_lists_itself_as_a_dependency() -> None:
    for name, dependencies in edges().items():
        assert name not in dependencies


def test_every_layer_holds_at_least_one_module() -> None:
    for name, members in modules_by_layer().items():
        assert members, name


def test_the_footer_counts_every_module() -> None:
    total = sum(len(items) for items in modules_by_layer().values())
    assert f"{total} modules" in render()


def test_the_map_has_no_carriage_returns() -> None:
    assert b"\r" not in target().read_bytes()


def test_the_check_mode_passes_while_it_is_current() -> None:
    assert main(("--check",)) == 0
