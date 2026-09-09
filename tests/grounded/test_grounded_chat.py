"""#123 — grounded context, provenance boundary, citations, hallucination."""

from __future__ import annotations

import pytest

from app.grounded import (
    Basis,
    ContextItem,
    GroundedChat,
    GroundedContext,
    build_context_from_bundle,
    build_grounded_prompt,
)
from app.grounded.errors import ContextProvenanceError
from app.knowledge.provenance import Provenance, SourceType
from tests.grounded.conftest import FailingProvider, ScriptedAnswerProvider

# --- context construction + provenance boundary ----------------------


def test_context_has_all_three_lanes_with_provenance(elig_bundle, retriever) -> None:
    ctx = build_context_from_bundle(
        "What are the business rules?", elig_bundle, retriever=retriever
    )
    assert ctx.source_context and ctx.analysis_context and ctx.retrieved_context
    for it in ctx.all_items():
        assert it.provenance.source_id == "ELIGIBILITY"
        it.provenance.validate_complete()
    assert {it.basis for it in ctx.analysis_context} == {Basis.DETERMINISTIC_FACT}
    assert {it.basis for it in ctx.retrieved_context} == {Basis.RETRIEVED_KNOWLEDGE}


def test_validate_rejects_an_item_without_usable_provenance() -> None:
    bad = ContextItem(
        ref="E1",
        basis=Basis.DETERMINISTIC_FACT,
        content="something",
        provenance=Provenance.model_construct(
            source_id="", source_type=SourceType.COBOL, artifact_version="v1"
        ),
        kind="source",
    )
    ctx = GroundedContext(question="q", source_context=[bad])
    with pytest.raises(ContextProvenanceError):
        ctx.validate()


def test_build_prompt_runs_the_hard_boundary() -> None:
    bad = ContextItem(
        ref="",
        basis=Basis.DETERMINISTIC_FACT,
        content="x",
        provenance=Provenance(
            source_id="P", source_type=SourceType.COBOL, artifact_version="v1"
        ),
        kind="source",
    )
    with pytest.raises(ContextProvenanceError):
        build_grounded_prompt(GroundedContext(question="q", source_context=[bad]))


def test_prompt_labels_fact_vs_retrieved(elig_bundle, retriever) -> None:
    ctx = build_context_from_bundle("explain", elig_bundle, retriever=retriever)
    prompt = build_grounded_prompt(ctx)
    assert "DETERMINISTIC_FACT" in prompt
    assert "RETRIEVED_KNOWLEDGE" in prompt
    assert "Never invent" in prompt or "Do not use outside knowledge" in prompt


# --- honest answers -------------------------------------------------


def test_grounded_answer_keeps_verified_citations(elig_bundle, retriever) -> None:
    p = ScriptedAnswerProvider(
        {
            "answer": "CHECK-ELIGIBILITY sets WS-RESULT from WS-AGE.",
            "evidence": "REAL",
            "confidence": "moderate",
            "insufficient_context": False,
        }
    )
    res = GroundedChat(p, retriever=retriever).ask(
        "What does CHECK-ELIGIBILITY do?", elig_bundle
    )
    assert not res.answer.insufficient_context
    assert len(res.answer.evidence) == 2
    for e in res.answer.evidence:
        assert e.source_id == "ELIGIBILITY"
        assert e.citation
    assert res.answer.confidence.value != "no_supporting_evidence"


def test_fabricated_evidence_id_is_stripped(elig_bundle, retriever) -> None:
    p = ScriptedAnswerProvider(
        {
            "answer": "The program performs CHECK-ELIGIBILITY.",
            "evidence": "REAL+FAKE",
            "confidence": "high",
            "insufficient_context": False,
        }
    )
    res = GroundedChat(p, retriever=retriever).ask("what runs?", elig_bundle)
    assert "E999" in res.answer.rejected_claims
    assert all(e.ref != "E999" for e in res.answer.evidence)


# --- hallucination defense -----------------------------------------


@pytest.mark.parametrize(
    "answer,question",
    [
        ("Variable WS-CREDIT-SCORE holds the value 720.", "What is WS-CREDIT-SCORE?"),
        (
            "Paragraph VALIDATE-CUSTOMER-CREDIT performs the check.",
            "which paragraph validates credit?",
        ),
        (
            "Business rule BR-777 rejects customers over 65.",
            "what rule rejects over 65?",
        ),
        ("It calls the external program NOTREAL-SUB.", "what does it CALL?"),
    ],
)
def test_answers_about_nonexistent_things_become_cannot_determine(
    elig_bundle, retriever, answer, question
) -> None:
    p = ScriptedAnswerProvider(
        {
            "answer": answer,
            "evidence": "REAL",
            "confidence": "high",
            "insufficient_context": False,
        }
    )
    res = GroundedChat(p, retriever=retriever).ask(question, elig_bundle)
    assert res.answer.insufficient_context
    assert res.answer.evidence == ()
    assert "cannot be determined" in res.answer.answer.lower()
    assert res.answer.rejected_claims


def test_model_uncertainty_is_respected(elig_bundle, retriever) -> None:
    p = ScriptedAnswerProvider(
        {
            "answer": "I cannot determine this from the available evidence.",
            "evidence": [],
            "confidence": "none",
            "insufficient_context": True,
        }
    )
    res = GroundedChat(p, retriever=retriever).ask(
        "What DB2 tables does it use?", elig_bundle
    )
    assert res.answer.insufficient_context
    assert res.answer.confidence.value == "no_supporting_evidence"


def test_unparseable_model_output_is_safe(elig_bundle, retriever) -> None:
    from app.ai.providers.models import LLMResponse
    from app.ai.providers.base import LLMProvider

    class Garbage(LLMProvider):
        def generate(self, request):  # noqa: ANN001
            return LLMResponse(text="not json at all", model="g")

    res = GroundedChat(Garbage(), retriever=retriever).ask("q?", elig_bundle)
    assert res.answer.insufficient_context


def test_provider_failure_is_a_safe_cannot_determine(elig_bundle, retriever) -> None:
    res = GroundedChat(FailingProvider(), retriever=retriever).ask("q?", elig_bundle)
    assert res.provider_failed
    assert res.answer.insufficient_context
    assert any("provider_failure" in n for n in res.answer.notes)


def test_context_provenance_manifest_is_json_safe(elig_bundle, retriever) -> None:
    import json

    p = ScriptedAnswerProvider(
        {
            "answer": "x",
            "evidence": "REAL",
            "confidence": "low",
            "insufficient_context": False,
        }
    )
    res = GroundedChat(p, retriever=retriever).ask("explain the program", elig_bundle)
    json.dumps(res.to_dict())
    assert res.to_dict()["context_provenance"]


def test_works_without_a_retriever(elig_bundle) -> None:
    p = ScriptedAnswerProvider(
        {
            "answer": "CHECK-ELIGIBILITY handles age.",
            "evidence": "REAL",
            "confidence": "low",
            "insufficient_context": False,
        }
    )
    res = GroundedChat(p).ask("what does CHECK-ELIGIBILITY do?", elig_bundle)
    assert res.context.retrieved_context == []
    assert res.answer.evidence
