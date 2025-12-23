"""Every module has a test module, and every test module has a module."""

from __future__ import annotations

import pytest

from legvise.tools.check_tests import expected_test_module, problems, stranded, untested


def test_the_package_has_a_test_module_for_everything() -> None:
    assert untested() == ()


def test_no_test_module_is_stranded() -> None:
    assert stranded() == ()


def test_the_check_reports_nothing_on_this_package() -> None:
    assert problems() == []


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("legvise.money", "tests.test_money"),
        ("legvise.model.venue", "tests.model.test_venue"),
        ("legvise.store.db", "tests.store.test_db"),
        ("legvise.scan.direct", "tests.scan.test_direct"),
    ],
)
def test_the_expected_name_mirrors_the_module_path(module: str, expected: str) -> None:
    assert expected_test_module(module) == expected


def test_the_package_root_maps_to_a_package_test() -> None:
    assert expected_test_module("legvise") == "tests.test_package"


def test_a_cli_module_is_allowed_the_cli_suffix() -> None:
    assert expected_test_module("legvise.cli.venue") == "tests.cli.test_venue"
