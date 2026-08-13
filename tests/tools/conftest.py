"""Pointing a check at a made up tree, so its failure branch runs.

Every check in `legvise.tools` reads the package and reports what is wrong with
it. The package is not wrong, which is the point, and it means the branch that
builds the message has never run: the tests all watch a check come back clean.
A check that has only ever returned an empty list is not a tested check. It is
a function nobody has ever seen produce output.

So these build a `SourceFile` out of a string and swap it in for the real walk.
The check then reads a module that is wrong on purpose, in exactly one way, and
the test reads the sentence it produced.

The swap works because every check imports `source_files` and `suite_files` into
its own namespace at module level. That is worth keeping: a check that reached
through `walk.source_files()` instead could not be pointed anywhere.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from legvise.tools.walk import SourceFile

Pointer = Callable[..., None]


def a_module(text: str, module: str = "legvise.made_up") -> SourceFile:
    """One synthetic module, parsed the way the walk would have parsed it."""
    return SourceFile(
        path=Path(module.replace(".", "/") + ".py"),
        module=module,
        tree=ast.parse(text),
        text=text,
    )


def a_test_module(text: str, module: str = "tests.test_made_up") -> SourceFile:
    """One synthetic test module, for the checks that read the suite."""
    return a_module(text, module)


def a_decorated_test(decorator: str, name: str = "test_a_thing_that_never_runs") -> SourceFile:
    """A test module holding one test under one decorator."""
    return a_test_module(
        '"""Fine."""\n'
        "\n"
        "import pytest\n"
        "\n"
        "\n"
        f"@pytest.mark.{decorator}\n"
        f"def {name}() -> None:\n"
        "    pass\n"
    )


@pytest.fixture()
def reading(monkeypatch: pytest.MonkeyPatch) -> Pointer:
    """Point a check at made up sources instead of at the package."""

    def point(
        check: ModuleType,
        *sources: SourceFile,
        suite: tuple[SourceFile, ...] = (),
    ) -> None:
        if hasattr(check, "source_files"):
            monkeypatch.setattr(check, "source_files", lambda: sources)
        if hasattr(check, "suite_files"):
            monkeypatch.setattr(check, "suite_files", lambda: suite)

    return point
