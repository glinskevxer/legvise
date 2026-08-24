"""The runbook, and the two halves of it that are read out of the tree."""

from __future__ import annotations

import pytest

from legvise.rules import clause_codes, clauses_for_stage, stages
from legvise.tools import build_operations
from legvise.tools.build_operations import (
    OUTPUT,
    REMEDIES,
    checks,
    is_current,
    remedy_for,
    render,
    stage_rows,
    target,
)
from legvise.tools.walk import package_root


def test_the_runbook_on_disk_is_current() -> None:
    assert is_current(), f"{OUTPUT} is stale"


def test_the_check_mode_passes_while_it_is_current() -> None:
    assert build_operations.main(("--check",)) == 0


def test_every_stage_of_the_rule_book_has_advice() -> None:
    assert set(REMEDIES) == set(stages())


def test_every_stage_names_a_command_to_run() -> None:
    for stage, (advice, command) in REMEDIES.items():
        assert advice, stage
        assert command.startswith("legvise "), stage


def test_a_stage_row_counts_its_own_clauses() -> None:
    for stage, count, _, _ in stage_rows():
        assert count == len(clauses_for_stage(stage))


def test_the_rows_cover_every_stage_once() -> None:
    assert [row[0] for row in stage_rows()] == list(stages())


@pytest.mark.parametrize("code", clause_codes())
def test_every_clause_resolves_to_advice(code: str) -> None:
    advice, command = remedy_for(code)
    assert advice
    assert command


def test_a_clause_takes_the_advice_of_its_stage() -> None:
    assert remedy_for("DEPTH.01") == remedy_for("DEPTH.02")


def test_a_clause_nobody_wrote_has_no_advice() -> None:
    assert remedy_for("NOWHERE.01") == ("", "")


def test_every_check_module_is_listed() -> None:
    on_disk = {path.stem for path in (package_root() / "tools").glob("check_*.py")}
    assert {name for name, _ in checks()} == on_disk


def test_every_check_carries_a_sentence_about_itself() -> None:
    for name, summary in checks():
        assert summary, name
        assert not summary.endswith("."), name


def test_the_checks_are_listed_in_name_order() -> None:
    names = [name for name, _ in checks()]
    assert names == sorted(names)


def test_the_runbook_names_the_file_it_is_written_from() -> None:
    assert "legvise.tools.build_operations" in render()
    assert target().name == "operations.md"


def test_the_runbook_shows_the_command_for_a_refusal() -> None:
    body = render()
    assert "legvise scan refusals --session SESSION" in body
    assert "legvise db verify" in body
    assert "legvise db prune --keep-days 30" in body


def test_the_runbook_counts_what_it_covered() -> None:
    tail = render().strip().splitlines()[-1]
    assert f"{len(clause_codes())} clauses" in tail
    assert f"{len(checks())} self checks" in tail


def test_the_runbook_has_a_row_for_every_stage() -> None:
    body = render()
    for stage in stages():
        assert f"| {stage} | " in body


def test_the_runbook_has_a_row_for_every_check() -> None:
    body = render()
    for name, _ in checks():
        assert f"| `{name}` |" in body


def test_writing_it_reports_how_many_stages_it_covered(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert build_operations.main(()) == 0
    printed = capsys.readouterr().out
    assert f"wrote {len(stages())} stages" in printed
