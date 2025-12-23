"""Where SQL may live, and what a statement may be built from."""

from __future__ import annotations

import ast

from legvise.tools.check_sql import (
    ALLOWED_INTERPOLATIONS,
    SQL_LAYERS,
    problems,
    statements_in,
)
from legvise.tools.walk import SourceFile, package_root, source_files


def a_source(text: str, module: str = "legvise.store.thing") -> SourceFile:
    return SourceFile(
        path=package_root() / "store" / "thing.py",
        module=module,
        tree=ast.parse(text),
        text=text,
    )


def test_the_package_obeys_all_three_rules() -> None:
    assert problems() == []


def test_the_store_layer_is_where_sql_lives() -> None:
    assert SQL_LAYERS == ("legvise.store",)


def test_a_statement_in_the_code_is_recognised() -> None:
    source = a_source('X = "SELECT code FROM venue"\n')
    assert source.module.startswith(SQL_LAYERS)
    assert statements_in(source) == ("SELECT code FROM venue",)


def test_a_docstring_that_mentions_sql_is_not_a_statement() -> None:
    source = a_source('"""We never write SELECT * here."""\nX = 1\n')
    assert statements_in(source) == ()


def test_the_word_select_in_a_sentence_is_not_a_statement() -> None:
    source = a_source('X = "the query did not select it"\n')
    assert statements_in(source) == ()


def test_every_repository_names_its_columns() -> None:
    for source in source_files():
        if not source.module.startswith("legvise.store"):
            continue
        for statement in statements_in(source):
            assert "SELECT *" not in statement, source.module


def test_the_allowed_interpolations_are_all_column_lists_or_fragments() -> None:
    for name in ALLOWED_INTERPOLATIONS:
        assert name.isupper() or name in {"where", "join", "name"}


def test_every_column_constant_the_store_uses_is_allowed() -> None:
    for source in source_files():
        if not source.module.startswith("legvise.store"):
            continue
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith("_COLUMNS"):
                        assert target.id in ALLOWED_INTERPOLATIONS, target.id


def test_every_statement_that_takes_a_value_uses_a_placeholder() -> None:
    # `sqlite_master` is queried with a literal on purpose: 'table' there is a
    # SQLite keyword, not a value the desk supplied.
    for source in source_files():
        if not source.module.startswith("legvise.store"):
            continue
        for statement in statements_in(source):
            if "sqlite_master" in statement:
                continue
            if " WHERE " in statement and "= '" in statement:
                raise AssertionError(f"{source.module} embeds a literal in {statement[:60]}")
