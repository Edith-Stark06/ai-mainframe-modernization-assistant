"""#124 — advisor operations, fact/retrieval/recommendation separation, hallucination."""

from __future__ import annotations

import json

import pytest

from app.advisor import ModernizationAdvisor
from app.grounded.models import ConfidenceBand
from tests.advisor.conftest import GOOD, FailingProvider, ScriptedAdvisor

_OPS = [
    "explain_program",
    "identify_risks",
    "recommend_strategy",
    "explain_dependencies",
    "propose_java_architecture",
    "review_generated_java",
]


@pytest.mark.parametrize("op", _OPS)
def test_every_operation_returns_a_grounded_structured_response(op, bundle, retriever):
    adv = ModernizationAdvisor(ScriptedAdvisor(GOOD), retriever=retriever)
    resp = getattr(adv, op)(bundle)
    d = resp.to_dict()
    assert d["operation"] == op
    assert d["facts"], "advisor must consume deterministic facts"
    assert not resp.insufficient_evidence
    assert resp.evidence  # verified citations
    assert resp.recommendation and d["recommendation_basis"] == "AI_RECOMMENDATION"
    json.dumps(d)


def test_fact_retrieval_recommendation_are_distinguishable(bundle, retriever):
    adv = ModernizationAdvisor(ScriptedAdvisor(GOOD), retriever=retriever)
    resp = adv.identify_risks(bundle)
    for f in resp.facts:
        assert f.basis == "DETERMINISTIC_FACT"
        f.provenance.validate_complete()
    for e in resp.evidence:
        assert e.basis == "DETERMINISTIC_FACT"
    for e in resp.retrieved_knowledge:
        assert e.basis == "RETRIEVED_KNOWLEDGE"
    bs = resp.basis_summary
    assert bs["DETERMINISTIC_FACT"] >= 1
    assert bs["AI_RECOMMENDATION"] == 1


def test_deterministic_facts_come_from_analysis_not_the_model(bundle):
    # a model that outputs an empty conclusion still yields deterministic facts
    empty = {
        "conclusion": "",
        "recommendation": "",
        "evidence": [],
        "confidence": "none",
        "insufficient_context": True,
    }
    resp = ModernizationAdvisor(ScriptedAdvisor(empty)).identify_risks(bundle)
    assert resp.insufficient_evidence
    assert len(resp.facts) >= 1  # risks still reported deterministically


def test_affected_source_locations_are_real(bundle, retriever):
    adv = ModernizationAdvisor(ScriptedAdvisor(GOOD), retriever=retriever)
    resp = adv.explain_program(bundle)
    src_lines = bundle.source.splitlines()
    assert resp.affected_source_locations
    for loc in resp.affected_source_locations:
        assert loc.source_id == "ELIGIBILITY"
        if loc.line_start is not None:
            assert 1 <= loc.line_start <= len(src_lines)


# --- hallucination-prone cases ------------------------------------


def test_absent_paragraph_short_circuits_without_the_model(bundle):
    class Boom(ScriptedAdvisor):
        def generate(self, request):  # noqa: ANN001
            raise AssertionError("model must not be called for an absent paragraph")

    resp = ModernizationAdvisor(Boom(GOOD)).explain_paragraph(bundle, "NO-SUCH-PARA")
    assert resp.insufficient_evidence
    assert "contains no paragraph" in resp.conclusion.lower()


def test_absent_business_rule_short_circuits(bundle):
    resp = ModernizationAdvisor(ScriptedAdvisor(GOOD)).explain_business_rule(
        bundle, "BR-999"
    )
    assert resp.insufficient_evidence
    assert "br-999" in resp.conclusion.lower()


def test_hallucinated_conclusion_identifiers_are_rejected(bundle, retriever):
    bad = {
        "conclusion": "It computes WS-FICO-SCORE and CALLs RATING-SUB.",
        "recommendation": "ok",
        "evidence": "REAL",
        "confidence": "high",
        "insufficient_context": False,
    }
    resp = ModernizationAdvisor(
        ScriptedAdvisor(bad), retriever=retriever
    ).explain_program(bundle)
    assert resp.insufficient_evidence
    assert resp.evidence == ()
    assert any("WS-FICO-SCORE" in n for n in resp.notes)


def test_recommendation_may_reason_beyond_evidence_but_is_labelled(bundle):
    r = {
        "conclusion": "It validates age.",
        "recommendation": "Adopt a hexagonal architecture with a domain service layer.",
        "evidence": "REAL",
        "confidence": "moderate",
        "insufficient_context": False,
    }
    resp = ModernizationAdvisor(ScriptedAdvisor(r)).recommend_strategy(bundle)
    assert not resp.insufficient_evidence
    assert "hexagonal" in resp.recommendation
    assert resp.to_dict()["recommendation_basis"] == "AI_RECOMMENDATION"


def test_provider_failure_is_safe(bundle):
    resp = ModernizationAdvisor(FailingProvider()).explain_program(bundle)
    assert resp.insufficient_evidence
    assert resp.confidence is ConfidenceBand.NONE
    assert any("provider_failure" in n for n in resp.notes)
    assert resp.facts  # deterministic facts still available


def test_context_is_task_scoped(bundle):
    from app.advisor.context import build

    risks_ctx = build("identify_risks", bundle).context
    deps_ctx = build("explain_dependencies", bundle).context
    risk_txt = " ".join(i.content for i in risks_ctx.all_items())
    dep_txt = " ".join(i.content for i in deps_ctx.all_items())
    assert "risk" in risk_txt.lower()
    assert "dependency" in dep_txt.lower()
    # the risk context is not just the whole dependency dump
    assert len(risks_ctx.analysis_context) != len(deps_ctx.analysis_context)


def test_unrelated_source_is_excluded_from_advisor_context(bundle):
    from app.advisor.context import build
    from app.knowledge import (
        EmbeddingModelId,
        KnowledgeIndex,
        KnowledgeIngestor,
        KnowledgeRetriever,
    )
    from app.rag.embeddings.provider import DeterministicFakeProvider
    import tempfile
    from app.dataset.analysis_bundle import build_analysis_bundle

    other = build_analysis_bundle(
        "OTHER",
        open("tests/fixtures/phase5/simple_procedural.cbl").read(),
        tempfile.mkdtemp(),
    )
    idx = KnowledgeIndex(
        DeterministicFakeProvider(dimension=48), EmbeddingModelId("fake", "m", "v1", 48)
    )
    idx.add(KnowledgeIngestor().ingest_bundle(bundle).chunks)
    idx.add(KnowledgeIngestor().ingest_bundle(other).chunks)
    scoped = KnowledgeRetriever(idx, allowed_source_ids={"ELIGIBILITY"})

    ctx = build("explain_program", bundle, retriever=scoped).context
    for it in ctx.all_items():
        assert it.provenance.source_id == "ELIGIBILITY"
