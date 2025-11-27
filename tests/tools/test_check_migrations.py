"""The lock file that freezes a shipped migration."""

from __future__ import annotations

from legvise.store.schema import MIGRATIONS
from legvise.tools.check_migrations import (
    LOCK_NAME,
    current_lines,
    main,
    problems,
    read_lock,
)
from legvise.tools.walk import repo_root


def test_the_lock_file_matches_the_code() -> None:
    assert problems() == []


def test_the_lock_file_is_in_the_repository() -> None:
    assert (repo_root() / LOCK_NAME).exists()


def test_there_is_one_locked_line_per_migration() -> None:
    assert len(read_lock()) == len(MIGRATIONS)


def test_a_locked_line_carries_the_version_digest_and_name() -> None:
    version, digest, name = read_lock()[0].split(" ", 2)
    assert version == "0001"
    assert len(digest) == 16
    assert name == MIGRATIONS[0].name


def test_the_versions_are_zero_padded_and_in_order() -> None:
    versions = [line.split(" ", 1)[0] for line in read_lock()]
    assert versions == sorted(versions)
    assert all(len(version) == 4 for version in versions)


def test_the_digest_in_the_file_is_the_one_the_code_computes() -> None:
    locked = {line.split(" ", 1)[0]: line.split(" ")[1] for line in read_lock()}
    for step in MIGRATIONS:
        assert locked[f"{step.version:04d}"] == step.digest()


def test_the_generated_lines_match_the_file() -> None:
    assert list(current_lines()) == list(read_lock())


def test_the_lock_file_carries_a_comment_explaining_itself() -> None:
    text = (repo_root() / LOCK_NAME).read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "Append only" in text


def test_the_lock_file_has_no_carriage_returns() -> None:
    assert b"\r" not in (repo_root() / LOCK_NAME).read_bytes()


def test_running_the_check_returns_zero_while_it_is_clean() -> None:
    assert main(("--check",)) == 0
