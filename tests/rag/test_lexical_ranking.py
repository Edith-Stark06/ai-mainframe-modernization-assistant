"""BM25 ranking with phrase bonus."""

from __future__ import annotations

from app.rag.retrieval.lexical import rank_bm25
from app.rag.retrieval.models import RetrievalResult


def _chunk(cid: str, text: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=cid,
        document_id="d",
        content=text,
        chunk_index=0,
        metadata={},
        score=0.0,
    )


CHUNKS = [
    _chunk("data", "01 WS-TAX-RATE PIC 9V99 VALUE 0.18. 01 WS-TOTAL PIC 9(9)"),
    _chunk(
        "rule", "Business rule: When WS-TOTAL >= 50000, set WS-STATUS to 'HIGH VALUE'."
    ),
    _chunk("java", "private void calculateTax() { wsTax = wsSubtotal * wsTaxRate; }"),
    _chunk("misc", "DISPLAY 'SALES PROCESSING SUMMARY'."),
]


def _ids(query: str) -> list[str]:
    return [c.chunk_id for c, _ in rank_bm25(query, CHUNKS)]


def test_exact_number_finds_its_chunk_first() -> None:
    assert _ids("What happens at 50000?")[0] == "rule"


def test_quoted_phrase_gets_the_phrase_bonus() -> None:
    assert _ids("When is the status HIGH VALUE?")[0] == "rule"


def test_java_camel_case_matches_cobol_words() -> None:
    assert "java" in _ids("Where is the tax rate used?")


def test_chunks_without_any_match_are_excluded() -> None:
    assert "misc" not in _ids("tax rate")


def test_query_with_only_stopwords_returns_nothing() -> None:
    assert rank_bm25("what is the", CHUNKS) == []


def test_empty_candidates_return_nothing() -> None:
    assert rank_bm25("tax", []) == []


def test_ranking_is_deterministic_and_scores_descend() -> None:
    first = rank_bm25("tax rate total", CHUNKS)
    assert first == rank_bm25("tax rate total", CHUNKS)
    scores = [s for _, s in first]
    assert scores == sorted(scores, reverse=True)


def test_glossary_links_user_input_to_accept() -> None:
    chunks = [
        _chunk("acc", "ACCEPT WS-CUSTOMER-NAME. ACCEPT WS-QUANTITY."),
        _chunk("other", "MOVE 0 TO WS-COUNT."),
    ]
    ranked = rank_bm25("Which values are read from the user?", chunks)
    assert [c.chunk_id for c, _ in ranked] == ["acc"]


def test_verbatim_phrase_outranks_the_same_words_scattered() -> None:
    """Without the phrase bonus the chunk that merely repeats the words wins."""
    scattered = _chunk("scattered", "high high high status value value value")
    phrase = _chunk("phrase", "MOVE 'HIGH VALUE' TO WS-STATUS")
    filler = [_chunk(f"f{i}", f"MOVE {i} TO WS-X{i}") for i in range(5)]
    ranked = rank_bm25("Is the status HIGH VALUE?", [scattered, phrase, *filler])
    assert ranked[0][0].chunk_id == "phrase"
