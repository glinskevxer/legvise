"""The packaging metadata against the code it describes."""

from __future__ import annotations

from legvise import __version__
from legvise.tools.check_package import (
    ENTRY_POINT,
    PYTHON_FLOOR,
    constraints,
    problems,
    project,
    source_root,
    wheel_packages,
)


def test_the_metadata_agrees_with_the_code() -> None:
    assert problems() == []


def test_the_version_in_the_metadata_is_the_code_version() -> None:
    assert project()["version"] == __version__


def test_the_package_is_named_after_itself() -> None:
    assert project()["name"] == "legvise"


def test_the_description_says_what_the_package_does() -> None:
    text = project()["description"].lower()
    assert "arbitrage" in text
    assert len(text.split()) >= 5


def test_the_python_floor_is_the_one_ci_runs() -> None:
    assert project()["requires-python"] == PYTHON_FLOOR


def test_the_console_script_points_at_the_command_tree() -> None:
    assert project()["scripts"]["legvise"] == ENTRY_POINT


def test_every_runtime_dependency_is_pinned() -> None:
    for requirement in project()["dependencies"]:
        assert "==" in requirement, requirement


def test_every_development_dependency_is_pinned() -> None:
    for extra in project()["optional-dependencies"].values():
        for requirement in extra:
            assert "==" in requirement, requirement


def test_the_constraints_file_covers_every_dependency() -> None:
    pins = constraints()
    names = [requirement.partition("==")[0].lower() for requirement in project()["dependencies"]]
    for name in names:
        assert name in pins


def test_the_constraints_file_pins_the_test_tooling_too() -> None:
    pins = constraints()
    for name in ("pytest", "ruff", "mypy", "coverage"):
        assert name in pins


def test_the_wheel_ships_the_package_from_the_source_tree() -> None:
    assert wheel_packages() == ["src/legvise"]
    assert source_root().is_dir()


def test_the_runtime_depends_on_one_thing_only() -> None:
    assert len(project()["dependencies"]) == 1
