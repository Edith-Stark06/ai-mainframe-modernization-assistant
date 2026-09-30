"""Deterministic check that an answer's figures come from the context."""

from __future__ import annotations

import pytest

from app.rag.grounding import find_ungrounded_figures

CTX = [
    "Business rule BR-007: When WS-TOTAL >= 50000, set WS-STATUS to 'HIGH VALUE'.",
    "01 WS-TAX-RATE PIC 9V99 VALUE 0.18.",
    "MOVE 0.10 TO WS-DISCOUNT-RATE",
]


def check(answer: str, question: str = "") -> list[str]:
    return find_ungrounded_figures(answer, CTX, question)


def test_invented_figure_is_reported() -> None:
    assert check("The threshold is 7,500.") == ["7,500"]


def test_figure_in_context_is_grounded() -> None:
    assert check("HIGH VALUE at 50000 or more.") == []


@pytest.mark.parametrize("written", ["50,000", "50 000", "50 000", "50 000"])
def test_thousands_separators_are_understood(written: str) -> None:
    assert check(f"Status changes at {written}.") == []


def test_invented_figure_with_space_separator_is_caught() -> None:
    assert check("Typically about 10 000.") == ["10 000"]


@pytest.mark.parametrize("answer", ["18% tax", "tax of 18 %", "a rate of 0.18"])
def test_percentage_and_fraction_forms_match(answer: str) -> None:
    assert check(answer) == []


def test_small_whole_numbers_are_treated_as_enumeration() -> None:
    assert check("Step 1, then 2, then 3. It has 5 paragraphs.") == []


def test_small_decimals_are_still_checked() -> None:
    assert check("The discount is 0.25.") == ["0.25"]


def test_numbers_in_the_question_are_grounded() -> None:
    assert check("Yes, 9999 applies.", question="Does 9999 apply?") == []


def test_chunk_id_citations_and_rule_ids_are_ignored() -> None:
    assert check("See [business_rule-0b43ac91f2] and BR-003.") == []


def test_duplicates_are_reported_once_in_order() -> None:
    assert check("Over 7,500 or 3,200; again 7,500.") == ["7,500", "3,200"]


def test_no_context_means_every_real_figure_is_ungrounded() -> None:
    assert find_ungrounded_figures("It is 50000.", [], "") == ["50000"]
