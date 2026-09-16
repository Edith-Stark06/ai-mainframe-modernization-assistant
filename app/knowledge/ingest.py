"""
Knowledge ingestion (#122) — deterministic analysis -> provenance-carrying
chunks.

``KnowledgeIngestor.ingest_program`` runs (or accepts) the existing
Phase 1–5 :class:`~app.dataset.analysis_bundle.AnalysisBundle` and emits
:class:`~app.knowledge.chunk.KnowledgeChunk` objects for every artifact
type. Every chunk is provenance-validated before it is returned; a chunk
that cannot be attributed is dropped and recorded in
:attr:`IngestionResult.rejected`, never silently indexed.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field

from app.dataset.analysis_bundle import AnalysisBundle, build_analysis_bundle
from app.knowledge.chunk import KnowledgeChunk
from app.knowledge.chunkers import (
    chunk_business_rules,
    chunk_cfg,
    chunk_cobol_source,
    chunk_dependencies,
    chunk_generated_java,
    chunk_ir,
    chunk_risks,
    chunk_strategy,
)
from app.knowledge.errors import ProvenanceError
from app.knowledge.provenance import SourceType
from app.knowledge.version import ANALYSIS_CONTRACT_VERSION

__all__ = ["IngestionResult", "KnowledgeIngestor", "merge_results"]


@dataclass(frozen=True)
class IngestionResult:
    source_id: str
    chunks: tuple[KnowledgeChunk, ...]
    rejected: tuple[dict[str, str], ...] = field(default_factory=tuple)
    analysis_version: str = ANALYSIS_CONTRACT_VERSION

    def by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.chunks:
            out[c.chunk_type.value] = out.get(c.chunk_type.value, 0) + 1
        return dict(sorted(out.items()))

    def by_source(self) -> set[str]:
        return {c.provenance.source_id for c in self.chunks}


class KnowledgeIngestor:
    def __init__(self, analysis_version: str = ANALYSIS_CONTRACT_VERSION) -> None:
        self._analysis_version = analysis_version

    # -- public --------------------------------------------------------

    def ingest_program(
        self,
        source_id: str,
        source: str,
        *,
        source_path: str | None = None,
        work_dir: str | None = None,
    ) -> IngestionResult:
        bundle = build_analysis_bundle(
            source_id, source, work_dir or tempfile.mkdtemp(prefix="p8-ingest-")
        )
        return self.ingest_bundle(bundle, source_path=source_path)

    def ingest_bundle(
        self, bundle: AnalysisBundle, *, source_path: str | None = None
    ) -> IngestionResult:
        sid = bundle.source_id
        path = source_path or f"{sid}.cbl"
        av = self._analysis_version
        candidates: list[KnowledgeChunk] = []

        candidates += chunk_cobol_source(
            sid,
            bundle.source,
            source_path=path,
            paragraph_names=list(bundle.paragraphs),
            source_type=SourceType.COBOL,
        )
        candidates += chunk_business_rules(
            bundle.business_rules,
            program_source_id=sid,
            analysis_version=av,
            source_path=path,
        )
        candidates += chunk_risks(
            bundle.risks,
            program_source_id=sid,
            analysis_version=av,
            source_path=path,
        )
        candidates += chunk_dependencies(
            bundle.dependencies,
            program_source_id=sid,
            analysis_version=av,
            source_path=path,
        )
        candidates += chunk_strategy(
            bundle.strategy, program_source_id=sid, analysis_version=av
        )
        candidates += chunk_cfg(bundle.cfg, program_source_id=sid, analysis_version=av)
        candidates += chunk_ir(bundle.ir, program_source_id=sid, analysis_version=av)
        candidates += chunk_generated_java(
            bundle.java_backend_output, program_source_id=sid
        )

        kept: list[KnowledgeChunk] = []
        rejected: list[dict[str, str]] = []
        seen: set[str] = set()
        for c in candidates:
            try:
                c.provenance.validate_complete()
            except (
                ProvenanceError
            ) as exc:  # pragma: no cover - chunkers already validate
                rejected.append({"chunk_type": c.chunk_type.value, "reason": str(exc)})
                continue
            if c.chunk_id in seen:
                continue
            seen.add(c.chunk_id)
            kept.append(c)

        kept.sort(key=lambda c: (c.chunk_type.value, c.chunk_id))
        return IngestionResult(
            source_id=sid,
            chunks=tuple(kept),
            rejected=tuple(rejected),
            analysis_version=av,
        )

    def ingest_many(self, programs: list[tuple[str, str]]) -> list[IngestionResult]:
        return [self.ingest_program(sid, src) for sid, src in sorted(programs)]


def merge_results(results: list[IngestionResult]) -> tuple[KnowledgeChunk, ...]:
    out: list[KnowledgeChunk] = []
    seen: set[str] = set()
    for r in results:
        for c in r.chunks:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                out.append(c)
    out.sort(key=lambda c: (c.provenance.source_id, c.chunk_type.value, c.chunk_id))
    return tuple(out)
