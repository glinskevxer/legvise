"""The rule book: lookup, grouping, and the shape of a refusal."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument, Refused
from legvise.rules import clause, clause_codes, clauses_for_stage, refuse, stages


def test_a_clause_carries_its_code_stage_and_words() -> None:
    found = clause("DEPTH.01")
    assert found.code == "DEPTH.01"
    assert found.stage == "DEPTH"
    assert "visible book" in found.text


def test_an_unknown_clause_is_refused_by_name() -> None:
    with pytest.raises(BadArgument) as caught:
        clause("DEPTH.99")
    assert caught.value.why == "not in the rule book"


def test_every_code_in_the_book_resolves() -> None:
    for code in clause_codes():
        assert clause(code).code == code


def test_no_clause_code_appears_twice_in_the_book() -> None:
    codes = clause_codes()
    assert len(codes) == len(set(codes))


def test_every_clause_has_a_stage_prefix_that_matches_its_code() -> None:
    for code in clause_codes():
        assert code.startswith(clause(code).stage + ".")


def test_stages_are_listed_once_each_in_book_order() -> None:
    listed = stages()
    assert listed[0] == "BOOK"
    assert len(listed) == len(set(listed))
    assert "EDGE" in listed


def test_a_stage_owns_the_clauses_that_carry_its_prefix() -> None:
    owned = clauses_for_stage("CAP")
    assert {c.code for c in owned} == {"CAP.01", "CAP.02", "CAP.03"}


def test_a_stage_nobody_owns_is_refused() -> None:
    with pytest.raises(BadArgument):
        clauses_for_stage("MARGIN")


def test_a_refusal_quotes_the_clause_it_rests_on() -> None:
    err = refuse("BAND.01", "leg 1")
    assert isinstance(err, Refused)
    assert err.subject == "leg 1"
    assert err.why.startswith("BAND.01: ")


def test_refuse_returns_rather_than_raising() -> None:
    err = refuse("EDGE.01", "plan 3")
    assert isinstance(err, Refused)
    with pytest.raises(Refused):
        raise err


def test_refusing_on_an_unknown_clause_fails_at_the_lookup() -> None:
    with pytest.raises(BadArgument):
        refuse("NOPE.01", "leg 1")


def test_clause_text_is_a_sentence_not_a_label() -> None:
    for code in clause_codes():
        text = clause(code).text
        assert " " in text
        assert text == text.lower() or text[0].islower()
