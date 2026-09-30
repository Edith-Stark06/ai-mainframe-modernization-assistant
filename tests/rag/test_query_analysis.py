"""Query analysis: splitting, tokenising, phrases, glossary."""

from __future__ import annotations

import pytest

from app.rag.retrieval.query import (
    expand_terms,
    extract_phrases,
    split_question,
    tokenize,
)

# ---------------------------------------------------------------- split


def test_single_question_is_not_split() -> None:
    q = "At what order total does the status become HIGH VALUE?"
    assert split_question(q) == [q]


def test_two_part_question_yields_original_then_each_part() -> None:
    q = (
        "At what order total does the status become HIGH VALUE, and what happens "
        "to the customer's discount rate for type R?"
    )
    parts = split_question(q)
    assert parts[0] == q
    assert parts[1:] == [
        "At what order total does the status become HIGH VALUE",
        "what happens to the customer's discount rate for type R?",
    ]


def test_three_part_question() -> None:
    parts = split_question(
        "What is the tax rate, when is the order flagged PREMIUM, and what is "
        "shown at the end of processing?"
    )
    assert len(parts) == 4
    assert parts[1] == "What is the tax rate"


def test_semicolon_and_question_mark_split() -> None:
    assert len(split_question("What is X now; how is Y computed?")) == 3
    assert len(split_question("What is X now? How is Y computed?")) == 3


def test_and_inside_a_noun_phrase_does_not_split() -> None:
    q = "How do the tax and discount rates interact?"
    assert split_question(q) == [q]


def test_fragments_too_short_to_search_are_discarded() -> None:
    q = "What is X, and why?"
    assert split_question(q) == [q]


# ------------------------------------------------------------- tokenize


def test_cobol_and_java_names_tokenise_alike() -> None:
    assert tokenize("WS-TOTAL") == tokenize("wsTotal") == ["ws", "total"]


def test_decimal_and_integer_numbers_stay_whole() -> None:
    assert tokenize("VALUE 0.18 and 50000") == ["value", "0.18", "and", "50000"]


def test_stopwords_are_dropped_only_on_request() -> None:
    assert "the" in tokenize("the total")
    assert tokenize("What is the total?", drop_stopwords=True) == ["total"]


def test_domain_words_are_not_stopwords() -> None:
    assert tokenize("status order total", drop_stopwords=True) == [
        "status",
        "order",
        "total",
    ]


# -------------------------------------------------------------- phrases


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("When is the status HIGH VALUE?", ["high value"]),
        ("What does 'ZERO VALUE ORDER' mean?", ["zero value order"]),
        ('Where is "READY" set?', ["ready"]),
        ("What is the tax rate?", []),
        ("Is WS-TOTAL used?", []),
    ],
)
def test_extract_phrases(query: str, expected: list[str]) -> None:
    assert extract_phrases(query) == expected


# ------------------------------------------------------------- glossary


def test_everyday_words_expand_to_cobol_verbs() -> None:
    assert "accept" in expand_terms(["user", "values"])
    assert "display" in expand_terms(["show"])
    assert expand_terms(["values"]) == ["values"]


def test_expansion_has_no_duplicates() -> None:
    out = expand_terms(["user", "enter", "input"])
    assert out.count("accept") == 1
