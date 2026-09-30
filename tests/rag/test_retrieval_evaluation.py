"""
The retrieval evaluation harness, and the retrieval quality it protects.

Purpose:
    Unit-test :mod:`app.rag.evaluation` itself, then use it (with the real
    embedding model) to pin what hybrid retrieval must achieve on two programs:
    the sample the improvements were developed on, and a second, held-out
    program whose questions were written without tuning anything against them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rag.evaluation import (
    EvalCase,
    evaluate_retrieval,
    load_cases,
)
from app.rag.retrieval.models import RetrievalResult

FIXTURES = Path("tests/fixtures/rag_eval")


def _chunk(text: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=text[:8] or "x",
        document_id="d",
        content=text,
        chunk_index=0,
        metadata={},
        score=0.0,
    )


def _search_returning(*texts: str):
    return lambda question, top_k: [_chunk(t) for t in texts]


# ---------------------------------------------------------------- harness


def test_ranks_report_the_first_chunk_containing_each_evidence() -> None:
    case = EvalCase("c", "q", ("alpha", "beta"))
    report = evaluate_retrieval(
        _search_returning("nothing", "has ALPHA here", "and beta"), [case], top_k=5
    )
    (result,) = report.results
    assert result.ranks == {"alpha": 2, "beta": 3}
    assert result.complete and result.evidence_recall == 1.0
    assert result.reciprocal_rank == pytest.approx(0.5)


def test_missing_evidence_is_named_and_lowers_the_scores() -> None:
    case = EvalCase("c", "q", ("alpha", "gamma"))
    report = evaluate_retrieval(_search_returning("alpha"), [case], top_k=5)
    (result,) = report.results
    assert not result.complete
    assert result.missing == ["gamma"]
    assert result.evidence_recall == 0.5
    assert report.complete_rate == 0.0
    assert report.mean_evidence_recall == 0.5


def test_only_the_first_top_k_chunks_count() -> None:
    case = EvalCase("c", "q", ("late",))
    report = evaluate_retrieval(_search_returning("a", "b", "late"), [case], top_k=2)
    assert report.results[0].ranks == {"late": None}


def test_matching_ignores_case_and_column_padding() -> None:
    case = EvalCase("c", "q", ("ws-age pic 9(3) value 0",))
    report = evaluate_retrieval(
        _search_returning("01 WS-AGE          PIC 9(3)   VALUE 0."), [case], top_k=3
    )
    assert report.results[0].complete


def test_aggregates_over_several_cases() -> None:
    cases = [EvalCase("hit", "q", ("a",)), EvalCase("miss", "q", ("zzz",))]
    report = evaluate_retrieval(_search_returning("a"), cases, top_k=3)
    assert report.complete_rate == 0.5
    assert report.mean_reciprocal_rank == 0.5


def test_empty_case_list_is_well_defined() -> None:
    report = evaluate_retrieval(_search_returning("a"), [], top_k=3)
    assert report.complete_rate == report.mean_reciprocal_rank == 0.0


def test_report_text_lists_misses_with_what_was_missing() -> None:
    report = evaluate_retrieval(
        _search_returning("a"), [EvalCase("bad", "q", ("zzz",))], top_k=3
    )
    text = report.format()
    assert "MISS bad" in text and "zzz" in text and "complete=0%" in text


def test_load_cases_reads_the_bundled_files() -> None:
    for name in ("sales_report_cases.json", "eligibility_cases.json"):
        cases = load_cases(FIXTURES / name)
        assert cases
        assert len({c.id for c in cases}) == len(cases)
        assert all(c.question and c.evidence for c in cases)


def test_load_cases_from_a_custom_file(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps({"cases": [{"id": "x", "question": "q?", "evidence": ["e"]}]})
    )
    assert load_cases(path) == [EvalCase("x", "q?", ("e",))]


# ------------------------------------------------- quality (real embeddings)


@pytest.fixture(scope="module")
def real_provider():
    from app.rag.embeddings.provider import SentenceTransformerProvider

    return SentenceTransformerProvider()


def _services(program: Path, provider):
    from app.rag.indexing.memory import InMemoryIndex
    from app.rag.ingestion import index_program
    from app.rag.retrieval.hybrid import HybridRetrievalService
    from app.rag.retrieval.service import RetrievalService

    index = InMemoryIndex(expected_dimension=384)
    index_program(
        source_id=program.stem.upper(),
        source_text=program.read_text(encoding="utf-8"),
        source_path=program.name,
        extra_metadata={"filename": program.name},
        embedding_provider=provider,
        index=index,
    )
    return RetrievalService(provider, index), HybridRetrievalService(provider, index)


def _report(service, cases_file: str, top_k: int):
    cases = load_cases(FIXTURES / cases_file)
    return evaluate_retrieval(
        lambda q, k: service.search(q, top_k=k), cases, top_k=top_k
    )


@pytest.mark.slow
def test_hybrid_beats_vector_and_finds_everything_on_the_sales_report(
    real_provider,
) -> None:
    vector, hybrid = _services(FIXTURES / "sales_report.cbl", real_provider)
    base = _report(vector, "sales_report_cases.json", 8)
    got = _report(hybrid, "sales_report_cases.json", 8)
    assert got.complete_rate == 1.0, got.format()
    assert got.complete_rate > base.complete_rate
    assert got.mean_evidence_recall > base.mean_evidence_recall


@pytest.mark.slow
def test_the_two_part_question_that_used_to_fail_now_retrieves_both_facts(
    real_provider,
) -> None:
    vector, hybrid = _services(FIXTURES / "sales_report.cbl", real_provider)
    for service, expect_complete in ((vector, False), (hybrid, True)):
        report = _report(service, "sales_report_cases.json", 5)
        case = next(
            r for r in report.results if r.case.id == "two_part_high_value_and_discount"
        )
        assert case.complete is expect_complete, report.format()


@pytest.mark.slow
def test_hybrid_generalises_to_a_held_out_program(real_provider) -> None:
    vector, hybrid = _services(FIXTURES / "eligibility.cbl", real_provider)
    base = _report(vector, "eligibility_cases.json", 5)
    got = _report(hybrid, "eligibility_cases.json", 5)
    assert got.complete_rate >= 0.95, got.format()
    assert got.complete_rate >= base.complete_rate
