"""Only package errors leave the package, and each one carries its parts."""

from __future__ import annotations

from legvise.errors import (
    BadArgument,
    Conflict,
    LegviseError,
    NotFound,
    Refused,
    StaleData,
)
from legvise.tools.check_errors import (
    ALLOWED_BUILTINS,
    ALLOWED_FACTORIES,
    ARITY,
    problems,
    raises_in,
)


def test_nothing_raises_an_exception_the_package_does_not_own() -> None:
    assert problems() == []


def test_the_arity_table_covers_every_package_error() -> None:
    classes = {NotFound, Conflict, BadArgument, Refused, StaleData, LegviseError}
    assert {cls.__name__ for cls in classes} == set(ARITY)


def test_the_arity_matches_what_each_error_actually_takes() -> None:
    assert ARITY["NotFound"] == 2
    assert ARITY["BadArgument"] == 3
    assert ARITY["StaleData"] == 3


def test_the_domain_raises_something_worth_counting() -> None:
    domain = [row for row in raises_in() if row[0].startswith("legvise.model")]
    assert len(domain) > 20


def test_the_refusal_factory_is_allowed_as_a_raise() -> None:
    assert "refuse" in ALLOWED_FACTORIES


def test_an_assertion_is_allowed_because_it_means_a_bug() -> None:
    assert "AssertionError" in ALLOWED_BUILTINS


def test_the_store_raises_only_package_errors() -> None:
    for module, name, _ in raises_in("legvise.store"):
        assert name in set(ARITY) | ALLOWED_BUILTINS | ALLOWED_FACTORIES, f"{module}:{name}"


def test_the_pricing_path_raises_only_package_errors() -> None:
    for module, name, _ in raises_in("legvise.scan"):
        assert name in set(ARITY) | ALLOWED_BUILTINS | ALLOWED_FACTORIES, f"{module}:{name}"


def test_every_not_found_names_both_the_kind_and_the_key() -> None:
    for module, name, arity in raises_in():
        if name == "NotFound" and arity >= 0:
            assert arity >= 2, module


def test_every_bad_argument_names_the_field_value_and_reason() -> None:
    for module, name, arity in raises_in():
        if name == "BadArgument" and arity >= 0:
            assert arity >= 3, module
