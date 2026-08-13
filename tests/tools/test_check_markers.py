"""No unfinished work left behind, and no test quietly switched off."""

from __future__ import annotations

import ast

from legvise.tools import check_markers
from legvise.tools.check_markers import (
    MARKERS,
    SKIP_DECORATORS,
    coverage_pragmas,
    problems,
    skipped_tests,
)
from legvise.tools.walk import SourceFile, package_root, source_files, suite_files
from tests.tools.conftest import Pointer, a_decorated_test, a_module, a_test_module


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


# The sentence each check produces when it finds something. Against the real
# tree every check comes back clean, which is the point of having them and also
# means the branch that writes the message never runs. These point the check at
# a made up tree that is wrong in exactly one way.


# A leftover marker that shipped, and a test nobody is running.


def test_a_leftover_marker_names_its_line(reading: Pointer) -> None:
    reading(check_markers, a_module('"""Fine."""\n\n# TODO: come back to this\n'))
    assert check_markers.problems() == ["legvise.made_up:3 still says TODO"]


def test_a_marker_in_the_suite_is_found_too(reading: Pointer) -> None:
    reading(check_markers, suite=(a_test_module('"""Fine."""\n\n# FIXME later\n'),))
    assert check_markers.problems() == ["tests.test_made_up:3 still says FIXME"]


def test_a_word_that_only_contains_a_marker_is_left_alone(reading: Pointer) -> None:
    reading(check_markers, a_module('"""Fine."""\n\nvalue = "TODOS"\n'))
    assert check_markers.problems() == []


def test_a_skipped_test_is_named_as_a_pass_that_is_not_one(reading: Pointer) -> None:
    reading(check_markers, suite=(a_decorated_test("skip"),))
    assert check_markers.problems() == [
        "tests.test_made_up.test_a_thing_that_never_runs is marked skip and counts as a pass"
    ]


def test_an_expected_failure_counts_the_same_way(reading: Pointer) -> None:
    reading(check_markers, suite=(a_decorated_test('xfail(reason="later")'),))
    assert "is marked xfail" in check_markers.problems()[0]


def test_a_condition_on_the_skip_does_not_excuse_it(reading: Pointer) -> None:
    reading(check_markers, suite=(a_decorated_test('skipif(True, reason="later")'),))
    assert "is marked skipif" in check_markers.problems()[0]


def test_a_test_with_an_ordinary_decorator_is_left_alone(reading: Pointer) -> None:
    running = a_decorated_test('parametrize("x", [1])', "test_a_thing_that_runs_as_it_should")
    reading(check_markers, suite=(running,))
    assert check_markers.problems() == []


def test_a_coverage_pragma_is_counted_but_not_a_problem(reading: Pointer) -> None:
    reading(check_markers, a_module('"""Fine."""\n\nvalue = 1  # pragma: no cover\n'))
    assert check_markers.coverage_pragmas() == (("legvise.made_up", 3),)
    assert check_markers.problems() == []
