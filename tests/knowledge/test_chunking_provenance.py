"""#122 Steps 1-3, 8 — chunking, provenance, determinism, isolation."""

from __future__ import annotations

import pytest

from app.knowledge import (
    ChunkType,
    KnowledgeChunk,
    KnowledgeIngestor,
    Provenance,
    ProvenanceError,
    SourceType,
    compute_chunk_id,
)
from app.knowledge.chunkers import chunk_cobol_source

# --- provenance invariant --------------------------------------------------


def test_chunk_cannot_be_created_without_source_id() -> None:
    with pytest.raises(Exception):
        Provenance(source_id="", source_type=SourceType.COBOL, artifact_version="v1")


def test_analysis_chunk_requires_analysis_version() -> None:
    p = Provenance(
        source_id="P", source_type=SourceType.BUSINESS_RULE, artifact_version="v1"
    )
    with pytest.raises(ProvenanceError, match="analysis_version"):
        p.validate_complete()


def test_chunk_rejects_mismatched_content_hash() -> None:
    p = Provenance(source_id="P", source_type=SourceType.COBOL, artifact_version="v1")
    with pytest.raises(ProvenanceError, match="content_hash"):
        KnowledgeChunk(
            chunk_id="x",
            chunk_type=ChunkType.COBOL_SOURCE,
            content="hello",
            content_hash="deadbeef",
            provenance=p,
        )


def test_every_ingested_chunk_has_validated_provenance(elig_ingestion) -> None:
    assert elig_ingestion.chunks
    assert elig_ingestion.rejected == ()
    for c in elig_ingestion.chunks:
        c.provenance.validate_complete()
        assert c.provenance.source_id == "ELIGIBILITY"
        assert c.content_hash
        assert c.provenance.artifact_version


def test_inverted_line_span_is_rejected() -> None:
    p = Provenance(
        source_id="P",
        source_type=SourceType.COBOL,
        artifact_version="v1",
        line_start=50,
        line_end=10,
    )
    with pytest.raises(ProvenanceError, match="inverted"):
        p.validate_complete()


# --- semantic boundaries ------------------------------------------------


def test_cobol_is_chunked_by_division_and_paragraph(elig_ingestion) -> None:
    types = elig_ingestion.by_type()
    assert types.get("cobol_division", 0) >= 2
    assert types.get("cobol_paragraph", 0) == 5  # MAIN + 4 rule paragraphs
    paras = {
        c.provenance.paragraph
        for c in elig_ingestion.chunks
        if c.chunk_type is ChunkType.COBOL_PARAGRAPH
    }
    assert paras == {
        "MAIN-PARA",
        "CHECK-ELIGIBILITY",
        "CALCULATE-TOTAL",
        "REVIEW-AMOUNT",
        "STATUS-STEP",
    }


def test_paragraph_chunk_lines_bracket_the_real_source(
    elig_source, elig_ingestion
) -> None:
    lines = elig_source.splitlines()
    for c in elig_ingestion.chunks:
        if c.chunk_type is ChunkType.COBOL_PARAGRAPH:
            header = lines[c.provenance.line_start - 1].strip().rstrip(".")
            assert header == c.provenance.paragraph
            assert c.provenance.line_end >= c.provenance.line_start


def test_one_chunk_per_business_rule_with_rule_id(elig_ingestion) -> None:
    rule_chunks = [
        c for c in elig_ingestion.chunks if c.chunk_type is ChunkType.BUSINESS_RULE
    ]
    assert rule_chunks
    ids = [c.provenance.rule_id for c in rule_chunks]
    assert all(ids) and len(ids) == len(set(ids))


def test_risk_and_dependency_chunks_carry_their_ids(elig_ingestion) -> None:
    for c in elig_ingestion.chunks:
        if c.chunk_type is ChunkType.RISK:
            assert c.provenance.risk_id
        if c.chunk_type is ChunkType.DEPENDENCY:
            assert c.provenance.dependency and ":" in c.provenance.dependency


# --- determinism -------------------------------------------------------


def test_ingestion_is_deterministic(elig_source) -> None:
    a = KnowledgeIngestor().ingest_program("ELIGIBILITY", elig_source)
    b = KnowledgeIngestor().ingest_program("ELIGIBILITY", elig_source)
    assert [c.chunk_id for c in a.chunks] == [c.chunk_id for c in b.chunks]
    assert [c.to_dict() for c in a.chunks] == [c.to_dict() for c in b.chunks]


def test_chunk_id_depends_on_content_and_location() -> None:
    base = dict(
        source_id="P",
        artifact_version="v1",
        chunk_type=ChunkType.COBOL_PARAGRAPH,
        location_key="para:X:1-3",
        content="A",
    )
    i1 = compute_chunk_id(**base)
    assert i1 == compute_chunk_id(**base)
    assert i1 != compute_chunk_id(**{**base, "content": "B"})
    assert i1 != compute_chunk_id(**{**base, "location_key": "para:X:4-6"})


# --- isolation --------------------------------------------------------


def test_a_chunk_never_reports_another_source(elig_ingestion, proc_ingestion) -> None:
    a_ids = {c.chunk_id for c in elig_ingestion.chunks}
    b_ids = {c.chunk_id for c in proc_ingestion.chunks}
    assert a_ids & b_ids == set()  # different source -> different ids
    for c in proc_ingestion.chunks:
        assert c.provenance.source_id == "COMPLEXPROC"
        assert "ELIGIBILITY" not in c.provenance.citation()


def test_tiny_source_still_produces_an_attributed_chunk() -> None:
    src = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. T.\n"
    chunks = chunk_cobol_source("T", src, paragraph_names=[])
    assert chunks
    assert all(c.provenance.source_id == "T" for c in chunks)
