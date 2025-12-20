"""The generated rule book document."""

from __future__ import annotations

from legvise.rules import clause, clause_codes, stages
from legvise.tools.build_rules import (
    OUTPUT,
    call_sites,
    clause_text,
    is_current,
    main,
    render,
    target,
    undocumented,
)


def test_the_document_on_disk_is_current() -> None:
    assert is_current()


def test_the_document_lives_under_docs() -> None:
    assert OUTPUT == "docs/rules.md"
    assert target().exists()


def test_the_document_says_it_is_generated() -> None:
    assert "Do not edit" in render()


def test_every_clause_appears_in_the_document() -> None:
    body = render()
    for code in clause_codes():
        assert f"`{code}`" in body


def test_every_clause_wording_appears_in_the_document() -> None:
    body = render()
    for code in clause_codes():
        assert clause(code).text in body


def test_every_stage_gets_its_own_heading() -> None:
    body = render()
    for stage in stages():
        assert f"## {stage}" in body


def test_every_clause_has_at_least_one_call_site() -> None:
    assert undocumented() == ()


def test_a_clause_raised_in_two_places_lists_both() -> None:
    sites = call_sites()["BOOK.02"]
    assert "model.book" in sites
    assert len(sites) > 1


def test_the_call_sites_drop_the_package_prefix() -> None:
    for sites in call_sites().values():
        for site in sites:
            assert not site.startswith("legvise.")


def test_the_footer_counts_the_clauses() -> None:
    assert f"{len(clause_codes())} clauses" in render()


def test_the_document_has_no_carriage_returns() -> None:
    assert b"\r" not in target().read_bytes()


def test_the_check_mode_passes_while_it_is_current() -> None:
    assert main(("--check",)) == 0


def test_a_clause_code_can_be_looked_up_on_its_own() -> None:
    assert clause_text("EDGE.01") == clause("EDGE.01").text
