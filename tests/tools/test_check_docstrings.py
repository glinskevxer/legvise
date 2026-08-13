"""What the docstring check says when it finds something.

The package is documented, so `problems()` against the real tree is an empty
list and always will be. These point it at modules that are not.
"""

from __future__ import annotations

import pytest

from legvise.tools import check_docstrings
from legvise.tools.check_docstrings import EXEMPT_NAMES, problems
from tests.tools.conftest import Pointer, a_module, a_test_module


def test_the_package_documents_everything_it_should() -> None:
    assert problems() == []


def test_a_module_with_no_docstring_is_named(reading: Pointer) -> None:
    reading(check_docstrings, a_module("value = 1\n"))
    assert problems() == ["legvise.made_up has no module docstring"]


def test_a_module_that_says_what_it_is_passes(reading: Pointer) -> None:
    reading(check_docstrings, a_module('"""Says what it is."""\n'))
    assert problems() == []


def test_a_function_with_no_docstring_is_named(reading: Pointer) -> None:
    reading(check_docstrings, a_module('"""Fine."""\n\n\ndef work() -> None:\n    pass\n'))
    assert problems() == ["legvise.made_up.work has no docstring"]


def test_a_private_function_needs_no_docstring(reading: Pointer) -> None:
    reading(check_docstrings, a_module('"""Fine."""\n\n\ndef _work() -> None:\n    pass\n'))
    assert problems() == []


def test_a_class_with_no_docstring_is_named(reading: Pointer) -> None:
    reading(check_docstrings, a_module('"""Fine."""\n\n\nclass Thing:\n    pass\n'))
    assert problems() == ["legvise.made_up.Thing has no docstring"]


def test_a_dunder_on_the_exempt_list_needs_no_docstring(reading: Pointer) -> None:
    body = (
        '"""Fine."""\n\n\nclass Thing:\n    """A thing."""\n\n'
        '    def __str__(self) -> str:\n        return ""\n'
    )
    reading(check_docstrings, a_module(body))
    assert problems() == []


def test_the_exempt_list_covers_the_dunders_that_repeat() -> None:
    assert "__post_init__" in EXEMPT_NAMES
    assert "__str__" in EXEMPT_NAMES


def test_a_test_module_with_no_docstring_is_named(reading: Pointer) -> None:
    reading(check_docstrings, suite=(a_test_module("value = 1\n"),))
    assert problems() == ["tests.test_made_up has no module docstring"]


def test_a_test_function_needs_no_docstring(reading: Pointer) -> None:
    body = '"""Fine."""\n\n\ndef test_a_thing_happens_when_asked() -> None:\n    pass\n'
    reading(check_docstrings, suite=(a_test_module(body),))
    assert problems() == []


def test_several_gaps_in_one_module_are_all_named(reading: Pointer) -> None:
    body = "def one() -> None:\n    pass\n\n\ndef two() -> None:\n    pass\n"
    reading(check_docstrings, a_module(body))
    assert len(problems()) == 3


def test_the_check_reports_what_it_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_docstrings.main() == 0
    assert "check_docstrings: clean" in capsys.readouterr().out
