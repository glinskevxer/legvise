"""The source walker the checks are built on, and the docstring check itself."""

from __future__ import annotations

import ast

from legvise.tools.check_docstrings import problems as docstring_problems
from legvise.tools.walk import (
    SourceFile,
    package_root,
    repo_root,
    report,
    source_files,
    suite_files,
)


def a_source(text: str, module: str = "legvise.thing") -> SourceFile:
    return SourceFile(
        path=package_root() / "thing.py",
        module=module,
        tree=ast.parse(text),
        text=text,
    )


def test_the_repo_root_holds_the_packaging_file() -> None:
    assert (repo_root() / "pyproject.toml").exists()


def test_the_package_root_is_the_legvise_directory() -> None:
    assert package_root().name == "legvise"
    assert (package_root() / "errors.py").exists()


def test_every_module_in_the_package_is_found() -> None:
    modules = {source.module for source in source_files()}
    assert "legvise.errors" in modules
    assert "legvise.store.db" in modules
    assert "legvise" in modules


def test_a_package_init_keeps_the_package_name() -> None:
    by_module = {source.module: source for source in source_files()}
    assert by_module["legvise.store"].is_package_init


def test_the_layer_is_the_subpackage() -> None:
    by_module = {source.module: source for source in source_files()}
    assert by_module["legvise.store.db"].layer == "store"
    assert by_module["legvise.errors"].layer == "legvise"


def test_every_test_module_is_found() -> None:
    modules = {source.module for source in suite_files()}
    assert "tests.test_money" in modules
    assert "tests.cli.test_venue_cli" in modules


def test_imports_are_read_from_both_forms() -> None:
    source = a_source("import legvise.errors\nfrom legvise.money import dec\nimport json\n")
    assert set(source.imports()) == {"legvise.errors", "legvise.money", "legvise.money.dec"}


def test_a_from_import_reports_the_dotted_candidate_as_well() -> None:
    # `book` here is a module and `dec` above is a function. The AST cannot tell
    # them apart, so both candidates are reported and the caller filters.
    source = a_source("from legvise.cli import book, fee\n")
    assert "legvise.cli.book" in source.imports()
    assert "legvise.cli.fee" in source.imports()


def test_a_module_with_no_package_imports_reports_none() -> None:
    assert a_source("import json\n").imports() == ()


def test_the_definitions_include_the_nested_ones() -> None:
    source = a_source("class A:\n    def b(self) -> None:\n        pass\n")
    assert {node.name for node in source.definitions()} == {"A", "b"}


def test_the_module_docstring_is_readable() -> None:
    assert a_source('"""Hello."""\n').docstring() == "Hello."
    assert a_source("x = 1\n").docstring() is None


def test_every_string_constant_is_collected() -> None:
    source = a_source('x = "one"\ny = "two"\n')
    assert set(source.string_constants()) == {"one", "two"}


def test_a_clean_report_returns_zero() -> None:
    assert report("thing", []) == 0


def test_a_report_with_problems_returns_one() -> None:
    assert report("thing", ["something is wrong"]) == 1


def test_the_package_has_no_missing_docstrings() -> None:
    assert docstring_problems() == []
