"""The checks that exist, the checks CI runs and the checks the gate collects."""

from __future__ import annotations

from pathlib import Path

import pytest

from legvise.tools import check_gate
from legvise.tools.check_gate import (
    GLOB,
    OUTER,
    ci_invocations,
    gate_names,
    generator_names,
    on_disk,
    problems,
)


def a_healthy_script() -> str:
    """The smallest `check.sh` text that this check is happy with."""
    lines = [f"run {name} $PY -m {name}" for name in OUTER]
    lines.append(f"for name in $(ls {GLOB}); do run $name; done")
    lines.extend(f"run {name} $PY -m legvise.tools.{name} --check" for name in generator_names())
    return "\n".join(lines) + "\n"


@pytest.fixture
def script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand in gate script the check reads instead of the real one."""
    path = tmp_path / "check.sh"
    path.write_text(a_healthy_script(), encoding="utf-8")
    monkeypatch.setattr(check_gate, "gate_script", lambda: path)
    return path


def test_the_three_lists_of_checks_agree_today() -> None:
    assert problems() == []


def test_there_are_checks_on_disk_to_compare() -> None:
    assert len(on_disk()) > 15


def test_every_check_module_is_named_for_what_it_checks() -> None:
    for name in on_disk():
        assert name.startswith("check_")


def test_the_modules_come_back_in_a_settled_order() -> None:
    assert list(on_disk()) == sorted(on_disk())


def test_the_workflow_invocations_are_read_out_of_the_file() -> None:
    assert "smoke" in ci_invocations()
    assert "release_check" in ci_invocations()


def test_continuous_integration_runs_every_check_that_exists() -> None:
    assert set(on_disk()) <= set(ci_invocations())


def test_the_release_gate_collects_every_check_that_exists() -> None:
    assert set(gate_names()) == set(on_disk())


def test_the_gate_watcher_is_itself_one_of_the_gates() -> None:
    assert "check_gate" in gate_names()
    assert "check_gate" in on_disk()


def test_continuous_integration_checks_every_generated_document() -> None:
    assert set(generator_names()) <= set(ci_invocations())


def test_there_are_documents_generated_from_the_tree() -> None:
    assert len(generator_names()) >= 5


def test_a_healthy_stand_in_script_finds_nothing_wrong(script: Path) -> None:
    assert script.exists()
    assert problems() == []


def test_a_missing_gate_script_is_a_problem_on_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_gate, "gate_script", lambda: tmp_path / "gone.sh")
    assert problems() == ["check.sh is missing"]


def test_a_script_that_stopped_globbing_the_checks_is_caught(script: Path) -> None:
    script.write_text(a_healthy_script().replace(GLOB, "src/legvise/tools/*.py"), encoding="utf-8")
    assert any("finds the checks" in line for line in problems())


@pytest.mark.parametrize("tool", OUTER)
def test_a_script_that_dropped_an_outer_tool_is_caught(script: Path, tool: str) -> None:
    kept = [line for line in a_healthy_script().splitlines() if tool not in line]
    script.write_text("\n".join(kept) + "\n", encoding="utf-8")
    assert f"check.sh no longer runs {tool}" in problems()


def test_a_script_that_forgot_one_generator_is_caught(script: Path) -> None:
    dropped = generator_names()[0]
    kept = [line for line in a_healthy_script().splitlines() if dropped not in line]
    script.write_text("\n".join(kept) + "\n", encoding="utf-8")
    assert f"check.sh does not check {dropped} output" in problems()


def test_the_script_faults_are_reported_together(script: Path) -> None:
    script.write_text("nothing useful happens here\n", encoding="utf-8")
    found = problems()
    assert len(found) == 1 + len(OUTER) + len(generator_names())


def test_a_check_the_workflow_forgot_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_gate, "ci_invocations", lambda: ())
    assert "check_layers exists and CI does not run it" in problems()


def test_a_check_the_release_gate_forgot_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_gate, "gate_names", lambda: ("check_sql",))
    found = problems()
    assert "check_layers exists and release_check does not collect it" in found
    assert "check_sql exists and release_check does not collect it" not in found


def test_a_workflow_line_for_a_deleted_check_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_gate, "ci_invocations", lambda: (*ci_invocations(), "check_ghost"))
    assert "CI runs check_ghost, which is not a module" in problems()


def test_a_gate_entry_for_a_deleted_check_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_gate, "gate_names", lambda: (*gate_names(), "check_ghost"))
    assert "release_check collects check_ghost, which is not a module" in problems()


def test_a_generator_the_workflow_forgot_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_gate, "ci_invocations", lambda: on_disk())
    found = problems()
    for name in generator_names():
        assert f"{name} is in the release gate and CI does not run it" in found


def test_a_workflow_that_moved_away_reads_as_running_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_gate, "repo_root", lambda: tmp_path)
    assert ci_invocations() == ()


def test_the_check_reports_itself_clean_from_the_command_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert check_gate.main() == 0
    assert "check_gate: clean" in capsys.readouterr().out
