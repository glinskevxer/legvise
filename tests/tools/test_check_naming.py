"""Test names read as sentences about the desk."""

from __future__ import annotations

from legvise.tools.check_naming import LEAST_WORDS, VAGUE, named_tests, problems


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


def named_tests_are_unique_within_a_module() -> None:
    seen: set[tuple[str, str]] = set()
    for module, name in named_tests():
        assert (module, name) not in seen, f"{module}.{name}"
        seen.add((module, name))
