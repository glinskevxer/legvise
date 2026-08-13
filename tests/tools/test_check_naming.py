"""Test names read as sentences about the desk."""

from __future__ import annotations

import pytest

from legvise.tools import check_naming
from legvise.tools.check_naming import LEAST_WORDS, VAGUE, named_tests, problems
from tests.tools.conftest import Pointer, a_test_module


def test_every_name_in_the_suite_reads_as_a_sentence() -> None:
    assert problems() == []


def test_the_floor_is_five_words_after_the_prefix() -> None:
    assert LEAST_WORDS == 5


def test_the_suite_is_big_enough_for_the_check_to_mean_something() -> None:
    assert len(named_tests()) > 500


def test_every_name_starts_with_the_prefix() -> None:
    for _, name in named_tests():
        assert name.startswith("test_")


def test_no_name_uses_a_word_from_the_vague_list() -> None:
    for module, name in named_tests():
        words = set(name.removeprefix("test_").split("_"))
        assert not (words & VAGUE), f"{module}.{name}"


def test_the_vague_list_holds_only_lower_case_words() -> None:
    for word in VAGUE:
        assert word.islower()
        assert "_" not in word


def test_no_name_ends_in_a_number() -> None:
    for _, name in named_tests():
        assert not name[-1].isdigit(), name


def test_no_name_is_used_twice_in_one_module() -> None:
    seen: set[tuple[str, str]] = set()
    for module, name in named_tests():
        assert (module, name) not in seen, f"{module}.{name}"
        seen.add((module, name))


# The sentence each check produces when it finds something. Against the real
# tree every check comes back clean, which is the point of having them and also
# means the branch that writes the message never runs. These point the check at
# a made up tree that is wrong in exactly one way.


# The suite's own names, which nothing else in the tree reads.


def test_a_name_shorter_than_the_floor_is_named(reading: Pointer) -> None:
    body = '"""Fine."""\n\n\ndef test_it_adds() -> None:\n    pass\n'
    reading(check_naming, suite=(a_test_module(body),))
    assert check_naming.problems() == [
        f"tests.test_made_up.test_it_adds is 2 words, wanted {LEAST_WORDS}"
    ]


def test_a_name_long_enough_is_left_alone(reading: Pointer) -> None:
    body = '"""Fine."""\n\n\ndef test_the_sum_of_two_prices_is_exact() -> None:\n    pass\n'
    reading(check_naming, suite=(a_test_module(body),))
    assert check_naming.problems() == []


@pytest.mark.parametrize("word", sorted(VAGUE))
def test_a_vague_word_in_a_name_is_named(reading: Pointer, word: str) -> None:
    body = f'"""Fine."""\n\n\ndef test_the_whole_thing_reads_{word}_here() -> None:\n    pass\n'
    reading(check_naming, suite=(a_test_module(body),))
    assert f"says {word}, which says nothing" in check_naming.problems()[0]


def test_a_name_ending_in_a_number_is_named(reading: Pointer) -> None:
    body = '"""Fine."""\n\n\ndef test_the_sum_of_two_prices_2() -> None:\n    pass\n'
    reading(check_naming, suite=(a_test_module(body),))
    assert "ends in a number, so it was copied" in check_naming.problems()[0]


def test_a_helper_in_the_suite_is_not_a_test_name(reading: Pointer) -> None:
    body = '"""Fine."""\n\n\ndef a_plan() -> None:\n    pass\n'
    reading(check_naming, suite=(a_test_module(body),))
    assert check_naming.problems() == []
