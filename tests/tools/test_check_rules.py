"""The rule book and the code agree in both directions."""

from __future__ import annotations

import pytest

from legvise.errors import Refused
from legvise.money import dec
from legvise.risk.caps import CapSet, require_trim
from legvise.rules import clause_codes, stages
from legvise.tools.check_rules import problems, raised_codes, unknown_codes, unraised


def test_the_book_and_the_code_agree() -> None:
    assert problems() == []


def test_every_clause_in_the_book_is_raised_somewhere() -> None:
    assert unraised() == ()


def test_no_refusal_names_a_clause_the_book_does_not_have() -> None:
    assert unknown_codes() == ()


def test_the_raised_codes_are_the_book_codes() -> None:
    assert set(raised_codes()) == set(clause_codes())


def test_every_stage_is_represented_in_the_raised_codes() -> None:
    raised_stages = {code.split(".")[0] for code in raised_codes()}
    assert raised_stages == set(stages())


def test_the_venue_cap_refusal_names_its_own_clause() -> None:
    caps = CapSet(
        venue_cap=dec("100"),
        venue_used=dec("99"),
        asset_cap=dec("10000"),
        asset_used=dec("0"),
        gross_cap=dec("100000"),
        gross_used=dec("0"),
    )
    with pytest.raises(Refused) as caught:
        require_trim(caps, dec("50"), subject="plan 1", floor=dec("10"))
    assert caught.value.why.startswith("CAP.01")


def test_the_asset_cap_refusal_names_the_other_clause() -> None:
    caps = CapSet(
        venue_cap=dec("10000"),
        venue_used=dec("0"),
        asset_cap=dec("100"),
        asset_used=dec("99"),
        gross_cap=dec("100000"),
        gross_used=dec("0"),
    )
    with pytest.raises(Refused) as caught:
        require_trim(caps, dec("50"), subject="plan 1", floor=dec("10"))
    assert caught.value.why.startswith("CAP.02")


def test_a_trim_nothing_bound_still_refuses_under_the_floor() -> None:
    caps = CapSet(
        venue_cap=dec("10000"),
        venue_used=dec("0"),
        asset_cap=dec("10000"),
        asset_used=dec("0"),
        gross_cap=dec("100000"),
        gross_used=dec("0"),
    )
    with pytest.raises(Refused) as caught:
        require_trim(caps, dec("5"), subject="plan 1", floor=dec("10"))
    assert caught.value.why.startswith("CAP.01")
