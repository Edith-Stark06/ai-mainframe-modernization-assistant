"""
Phase 8 end-to-end — provenance survives the whole pipeline.

    COBOL -> Phase 1-5 analysis -> knowledge chunks -> embeddings -> index
      -> retrieval -> grounded context -> fake LLM -> structured advisor
      response -> source evidence
"""

from __future__ import annotations

import json
import re
import tempfile

from app.advisor import ModernizationAdvisor
from app.ai.providers.base import LLMProvider
from app.ai.providers.models import LLMRequest, LLMResponse
from app.dataset.analysis_bundle import build_analysis_bundle
from app.grounded import GroundedChat
from app.knowledge import (
    EmbeddingModelId,
    KnowledgeIndex,
    KnowledgeIngestor,
    KnowledgeRetriever,
)
from app.rag.embeddings.provider import DeterministicFakeProvider

SRC = "tests/fixtures/phase4/eligibility_rules.cbl"


class _CiteFirstTwo(LLMProvider):
    """Cites the first two real evidence ids — deterministic, offline."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        ids = json.loads(
            re.search(r"VALID EVIDENCE IDS\n(\[.*\])", request.prompt).group(1)
        )
        payload = {
            "answer": "The program denies applicants under 18 (rule BR-001).",
            "conclusion": "The program validates applicant age and totals fees.",
            "recommendation": "Extract the paragraphs into small services.",
            "evidence": ids[:2],
            "confidence": "moderate",
            "insufficient_context": False,
        }
        return LLMResponse(text=json.dumps(payload), model="cite2")


def test_provenance_survives_every_stage():
    source = open(SRC, encoding="utf-8").read()

    # 1. deterministic analysis
    bundle = build_analysis_bundle("ELIGIBILITY", source, tempfile.mkdtemp())

    # 2. chunks — every one attributed
    ingestion = KnowledgeIngestor().ingest_bundle(bundle)
    assert ingestion.chunks and ingestion.rejected == ()
    chunk_by_id = {c.chunk_id: c for c in ingestion.chunks}
    for c in ingestion.chunks:
        assert c.provenance.source_id == "ELIGIBILITY"
        c.provenance.validate_complete()

    # 3-4. embeddings + index (identity recorded)
    idx = KnowledgeIndex(
        DeterministicFakeProvider(dimension=64),
        EmbeddingModelId("fake", "mini", "v1", 64),
        workspace_id="ws-e2e",
    )
    idx.add(ingestion.chunks)
    assert idx.stats()["embedding_identity"]

    # 5. retrieval — provenance + score, project-scoped
    retriever = KnowledgeRetriever(idx, allowed_source_ids={"ELIGIBILITY"})
    hits = retriever.retrieve("which rule handles age?", top_k=5)
    assert hits
    for h in hits:
        assert h.chunk.chunk_id in chunk_by_id
        assert h.provenance.source_id == "ELIGIBILITY"
        assert h.citation()

    # 6-7. grounded context -> fake LLM -> verified answer
    chat = GroundedChat(_CiteFirstTwo(), retriever=retriever)
    chat_res = chat.ask("Which rule denies applicants under 18?", bundle)
    for it in chat_res.context.all_items():
        it.provenance.validate_complete()
    assert not chat_res.answer.insufficient_context
    assert chat_res.answer.evidence
    for e in chat_res.answer.evidence:
        assert e.source_id == "ELIGIBILITY"
        assert e.citation

    # 8. advisor -> structured response -> source evidence
    advisor = ModernizationAdvisor(_CiteFirstTwo(), retriever=retriever)
    resp = advisor.explain_program(bundle)
    d = resp.to_dict()
    json.dumps(d)  # fully serialisable
    assert d["facts"] and d["evidence"]
    assert d["recommendation_basis"] == "AI_RECOMMENDATION"

    # every advisor source location points at a real line of the real file
    src_lines = source.splitlines()
    assert resp.affected_source_locations
    for loc in resp.affected_source_locations:
        assert loc.source_id == "ELIGIBILITY"
        if loc.line_start is not None:
            assert 1 <= loc.line_start <= len(src_lines)
        if loc.paragraph is not None:
            assert loc.paragraph in {p.upper() for p in bundle.paragraphs} or (
                loc.paragraph in bundle.paragraphs
            )

    # the benchmark / dataset are untouched by any of this
    assert "ELIGIBILITY" in {f.provenance.source_id for f in resp.facts}


def test_pipeline_is_deterministic():
    source = open(SRC, encoding="utf-8").read()

    def once():
        b = build_analysis_bundle("ELIGIBILITY", source, tempfile.mkdtemp())
        ing = KnowledgeIngestor().ingest_bundle(b)
        idx = KnowledgeIndex(
            DeterministicFakeProvider(dimension=64),
            EmbeddingModelId("fake", "mini", "v1", 64),
        )
        idx.add(ing.chunks)
        r = KnowledgeRetriever(idx, allowed_source_ids={"ELIGIBILITY"})
        adv = ModernizationAdvisor(_CiteFirstTwo(), retriever=r)
        return (
            [c.chunk_id for c in ing.chunks],
            adv.explain_program(b).to_dict(),
        )

    a = once()
    b = once()
    assert a[0] == b[0]
    assert a[1] == b[1]
