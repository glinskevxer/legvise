"""The changelog against the version the code says it is."""

from __future__ import annotations

from legvise import __version__
from legvise.tools.check_changelog import (
    CHANGELOG_NAME,
    body_of,
    entries,
    problems,
    target,
)


def test_the_changelog_matches_the_version_the_code_says() -> None:
    assert problems() == []


def test_the_changelog_is_in_the_repository_root() -> None:
    assert CHANGELOG_NAME == "CHANGELOG.md"
    assert target().exists()


def test_the_top_entry_is_the_current_version() -> None:
    assert entries()[0].version == __version__


def test_every_entry_carries_a_date() -> None:
    for entry in entries():
        assert entry.is_dated, entry.version


def test_the_versions_descend_down_the_file() -> None:
    parts = [entry.parts for entry in entries()]
    assert parts == sorted(parts, reverse=True)


def test_no_version_is_listed_twice() -> None:
    versions = [entry.version for entry in entries()]
    assert len(versions) == len(set(versions))


def test_every_entry_says_something_about_the_release() -> None:
    for entry in entries():
        assert body_of(entry.version), entry.version


def test_the_first_release_named_the_two_kinds_of_scan() -> None:
    # Against the first entry rather than the current one. An entry describes
    # its own release, and once there is a second one the top of the file is a
    # list of what changed rather than a description of the whole tool.
    body = " ".join(body_of("0.1.0")).lower()
    assert "cross venue" in body
    assert "triangular" in body


def test_the_first_release_named_the_edge_decomposition() -> None:
    body = " ".join(body_of("0.1.0"))
    assert "net = gross - fees - slippage - rebalance" in body


def test_the_current_entry_says_what_changed_in_it() -> None:
    body = " ".join(body_of(__version__)).lower()
    assert "settings file" in body
    assert "prun" in body


def test_the_current_entry_is_the_version_the_code_says() -> None:
    assert entries()[0].version == __version__


def test_a_version_nobody_released_has_no_body() -> None:
    assert body_of("9.9.9") == ()


def test_the_changelog_has_no_carriage_returns() -> None:
    assert b"\r" not in target().read_bytes()
