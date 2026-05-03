"""No unfinished work left behind, and no test quietly switched off."""

from __future__ import annotations

import ast

from legvise.tools.check_markers import (
    MARKERS,
    SKIP_DECORATORS,
    coverage_pragmas,
    problems,
    skipped_tests,
)
from legvise.tools.walk import SourceFile, package_root, source_files, suite_files


def a_source(text: str, module: str = "tests.thing") -> SourceFile:
    return SourceFile(
        path=package_root() / "thing.py",
        module=module,
        tree=ast.parse(text),
        text=text,
    )


def test_the_tree_carries_no_unfinished_work() -> None:
    assert problems() == []


def test_no_test_in_the_suite_is_skipped() -> None:
    assert skipped_tests() == ()


def test_the_markers_are_the_ones_worth_catching() -> None:
    assert "TODO" in MARKERS
    assert "FIXME" in MARKERS
    assert "WIP" in MARKERS


def test_both_skip_forms_and_xfail_are_watched_for() -> None:
    assert {"skip", "skipif", "xfail"} == SKIP_DECORATORS


def test_a_coverage_pragma_is_allowed_and_counted() -> None:
    found = coverage_pragmas()
    assert all(module.startswith("legvise") for module, _ in found)
    assert len(found) < 10


def test_no_source_module_carries_a_marker() -> None:
    for source in source_files():
        if source.module == "legvise.tools.check_markers":
            continue
        assert "TODO" not in source.text, source.module


def test_no_test_module_carries_a_marker() -> None:
    for source in suite_files():
        if source.module == "tests.tools.test_check_markers":
            continue
        assert "FIXME" not in source.text, source.module


def test_a_skipped_test_would_be_found() -> None:
    made = a_source(
        "import pytest\n\n\n@pytest.mark.skip\ndef test_one_two_three_four_five() -> None:\n"
        "    pass\n"
    )
    names = {node.name for node in ast.walk(made.tree) if isinstance(node, ast.FunctionDef)}
    assert names == {"test_one_two_three_four_five"}


def test_the_check_does_not_convict_itself() -> None:
    listed = [line for line in problems() if "check_markers" in line]
    assert listed == []
