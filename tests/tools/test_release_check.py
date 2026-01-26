"""The one gate that runs every other gate."""

from __future__ import annotations

import pytest

from legvise.tools.release_check import GATES, GENERATED, failures, main
from legvise.tools.walk import package_root


def test_the_whole_tree_is_ready_to_ship() -> None:
    assert failures() == {}


def test_the_gate_returns_zero_while_it_is_clean() -> None:
    assert main(()) == 0


def test_every_check_module_is_in_the_release_gate() -> None:
    on_disk = {
        path.stem
        for path in (package_root() / "tools").glob("check_*.py")
        if path.stem != "check_docstrings"
    }
    listed = {name for name, _ in GATES}
    assert on_disk - listed == set()


def test_every_generator_is_in_the_release_gate() -> None:
    on_disk = {
        path.stem
        for path in (package_root() / "tools").glob("*.py")
        if path.stem in {"schema_dump", "build_rules", "build_glossary"}
    }
    assert {name for name, _ in GENERATED} == on_disk


def test_no_gate_is_listed_twice() -> None:
    names = [name for name, _ in GATES]
    assert len(names) == len(set(names))


def test_the_gate_list_covers_more_than_ten_checks() -> None:
    assert len(GATES) > 10


def test_the_verdict_counts_every_gate(capsys: pytest.CaptureFixture[str]) -> None:
    main(())
    printed = capsys.readouterr().out
    assert f"{len(GATES) + len(GENERATED) + 1} gates clean" in printed


def test_the_verbose_flag_is_accepted(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(("--verbose",)) == 0
    assert "clean" in capsys.readouterr().out


def test_every_gate_returns_a_list_of_strings() -> None:
    for name, gate in GATES:
        result = gate()
        assert isinstance(result, list), name
        assert all(isinstance(line, str) for line in result), name
