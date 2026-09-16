"""#122 Steps 4-7 — embeddings, index identity, retrieval, filtering, scope."""

from __future__ import annotations

import pytest

from app.knowledge import (
    ChunkType,
    EmbeddingModelId,
    KnowledgeIndex,
    KnowledgeRetriever,
    RetrievedChunk,
)
from app.knowledge.errors import EmbeddingIdentityError, IndexError_
from app.rag.embeddings.provider import DeterministicFakeProvider

# --- embedding / index identity --------------------------------------


def test_embedding_identity_changes_with_the_model() -> None:
    a = EmbeddingModelId("fake", "mini", "v1", 48)
    b = EmbeddingModelId("fake", "mini", "v2", 48)
    c = EmbeddingModelId("fake", "large", "v1", 48)
    assert a.identity != b.identity != c.identity
    assert a.identity != c.identity


def test_index_rejects_wrong_dimension_vectors(model_id) -> None:
    idx = KnowledgeIndex(DeterministicFakeProvider(dimension=8), model_id)
    from tests.knowledge.conftest import FIXTURE
    from app.knowledge import KnowledgeIngestor

    chunks = (
        KnowledgeIngestor()
        .ingest_program("ELIGIBILITY", FIXTURE.read_text(encoding="utf-8"))
        .chunks
    )
    with pytest.raises(EmbeddingIdentityError):
        idx.add(chunks)


def test_index_stats_expose_versioned_identity(loaded_index) -> None:
    s = loaded_index.stats()
    assert s["size"] > 0
    assert s["embedding_model"] == "fake-mini"
    assert s["embedding_dimension"] == 48
    assert len(s["index_identity"]) == 16
    assert s["by_source"] == ["ELIGIBILITY"]


# --- retrieval returns provenance, never bare text -------------------


def test_retrieval_results_are_never_anonymous(retriever) -> None:
    hits = retriever.retrieve("business rules about age eligibility", top_k=5)
    assert hits
    for h in hits:
        assert isinstance(h, RetrievedChunk)
        assert h.provenance.source_id == "ELIGIBILITY"
        assert h.provenance.artifact_version
        assert h.citation()
        assert h.score is not None


def test_retrieval_is_deterministic(retriever) -> None:
    a = retriever.retrieve("shared mutable state risk", top_k=4)
    b = retriever.retrieve("shared mutable state risk", top_k=4)
    assert [h.chunk.chunk_id for h in a] == [h.chunk.chunk_id for h in b]
    assert [h.rank for h in a] == [1, 2, 3, 4]


def test_top_k_is_respected(retriever) -> None:
    assert len(retriever.retrieve("x", top_k=3)) <= 3
    with pytest.raises(IndexError_):
        retriever.retrieve("x", top_k=0)


def test_metadata_filtering(loaded_index) -> None:
    r = KnowledgeRetriever(loaded_index)
    only_rules = r.retrieve(
        "anything", top_k=50, filters={"chunk_type": "business_rule"}
    )
    assert only_rules
    assert all(h.chunk.chunk_type is ChunkType.BUSINESS_RULE for h in only_rules)

    by_para = r.retrieve("logic", top_k=50, filters={"paragraph": "CHECK-ELIGIBILITY"})
    assert by_para
    assert all(h.provenance.paragraph == "CHECK-ELIGIBILITY" for h in by_para)


def test_unknown_filter_is_rejected(loaded_index) -> None:
    with pytest.raises(IndexError_, match="unknown retrieval filter"):
        KnowledgeRetriever(loaded_index).retrieve("x", filters={"bogus": 1})


# --- project / workspace scope --------------------------------------


def test_retriever_scope_blocks_cross_project_source_filter(loaded_index) -> None:
    r = KnowledgeRetriever(loaded_index, allowed_source_ids={"ELIGIBILITY"})
    with pytest.raises(IndexError_, match="outside the retriever's project scope"):
        r.retrieve("x", filters={"source_id": "OTHER_PROGRAM"})


def test_two_projects_do_not_leak_into_each_other(
    model_id, elig_ingestion, proc_ingestion
) -> None:
    idx = KnowledgeIndex(DeterministicFakeProvider(dimension=48), model_id)
    idx.add(elig_ingestion.chunks)
    idx.add(proc_ingestion.chunks)

    scoped = KnowledgeRetriever(idx, allowed_source_ids={"ELIGIBILITY"})
    for h in scoped.retrieve("any modernization question", top_k=25):
        assert h.provenance.source_id == "ELIGIBILITY"


def test_workspace_bound_index_rejects_foreign_workspace_chunk(index) -> None:
    from app.knowledge import KnowledgeChunk, Provenance, SourceType

    p = Provenance(source_id="P", source_type=SourceType.COBOL, artifact_version="v1")
    c = KnowledgeChunk.create(
        chunk_type=ChunkType.COBOL_SOURCE,
        content="x",
        provenance=p,
        location_key="w",
        metadata={"workspace_id": "some-other-ws"},
    )
    with pytest.raises(EmbeddingIdentityError):
        index.add([c])


def test_delete_removes_from_index(loaded_index) -> None:
    cid = next(iter(loaded_index._chunks))
    assert loaded_index.contains(cid)
    assert loaded_index.delete([cid]) == 1
    assert not loaded_index.contains(cid)
