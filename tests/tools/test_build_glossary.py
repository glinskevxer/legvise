"""The generated glossary of the desk's records."""

from __future__ import annotations

from legvise.tools.build_glossary import (
    OUTPUT,
    entries,
    is_current,
    main,
    render,
    target,
)


def test_the_glossary_on_disk_is_current() -> None:
    assert is_current()


def test_the_glossary_lives_under_docs() -> None:
    assert OUTPUT == "docs/glossary.md"
    assert target().exists()


def test_the_glossary_says_it_is_generated() -> None:
    assert "Do not edit" in render()


def test_every_record_the_desk_keeps_is_listed() -> None:
    names = {entry.name for entry in entries()}
    for expected in ("Venue", "Instrument", "Book", "Plan", "Fill", "Cycle", "Band"):
        assert expected in names


def test_a_record_carries_its_fields() -> None:
    venue = next(entry for entry in entries() if entry.name == "Venue")
    assert venue.is_record
    assert {field.name for field in venue.fields} >= {"code", "notional_cap", "active"}


def test_a_field_carries_its_annotation() -> None:
    level = next(entry for entry in entries() if entry.name == "Level")
    assert {field.annotation for field in level.fields} == {"Decimal"}


def test_an_enum_is_listed_without_fields() -> None:
    side = next(entry for entry in entries() if entry.name == "Side")
    assert not side.is_record


def test_every_entry_carries_a_summary() -> None:
    for entry in entries():
        assert entry.summary, entry.name


def test_the_entries_are_grouped_by_module() -> None:
    modules = [entry.module for entry in entries()]
    assert modules == sorted(modules, key=modules.index)
    assert all(module.startswith("model.") for module in modules)


def test_every_entry_name_appears_in_the_document() -> None:
    body = render()
    for entry in entries():
        assert f"### {entry.name}" in body


def test_the_footer_counts_the_entries() -> None:
    assert f"{len(entries())} entries" in render()


def test_the_glossary_has_no_carriage_returns() -> None:
    assert b"\r" not in target().read_bytes()


def test_the_check_mode_passes_while_it_is_current() -> None:
    assert main(("--check",)) == 0
