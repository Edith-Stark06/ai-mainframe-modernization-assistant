"""
Validation Context for Chat.

Purpose:
    Chat searches the *code* of a program, but a question such as "analyze the
    validation of the java code compilation" is about the Validation Center's
    results (does the generated Java compile, do its tests pass, how complete is
    the analysis). Those results live outside the searchable code chunks, so the
    model had nothing to answer from and deflected. This module renders the
    same per-stage results the Validation Center shows into one evidence chunk
    the chat can cite.

Responsibilities:
    - :func:`build_validation_chunk` -- format validation stages (plus the
      compilation details) as a :class:`~app.rag.retrieval.models.RetrievalResult`.

Non-responsibilities:
    - Running the pipeline or deciding when to include this chunk (the chat
      router does, using :func:`app.rag.intent.wants_validation_context`).

Dependencies:
    - app.api.services.validation_stages, app.dataset bundles

Examples:
    ::

        chunk = build_validation_chunk(bundle, mb, "payroll.cbl")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.api.services.validation_stages import (
    compute_overall_status,
    compute_validation_stages,
)
from app.dataset.analysis_bundle import AnalysisBundle
from app.dataset.modernization_bundle import ModernizationBundle
from app.rag.retrieval.models import RetrievalResult

__all__ = ["VALIDATION_CHUNK_TYPE", "build_validation_chunk"]

#: ``metadata["chunk_type"]`` of the chunk this module builds.
VALIDATION_CHUNK_TYPE = "validation"

#: Longest list (errors, file names, test ids) written out in full.
_MAX_LIST_ITEMS = 10


def _detail_text(details: dict[str, Any]) -> str:
    """A compact rendering of a stage's ``details`` (scalars and short lists)."""
    parts: list[str] = []
    for key, value in details.items():
        if value in (None, "", [], (), {}):
            continue
        if isinstance(value, dict):
            continue  # nested structures are too large to be useful in prose
        if isinstance(value, (list, tuple)):
            if any(isinstance(v, (dict, list, tuple)) for v in value):
                continue  # e.g. confidence factors: structured, not prose
            shown = ", ".join(str(v) for v in value[:_MAX_LIST_ITEMS])
            more = len(value) - _MAX_LIST_ITEMS
            parts.append(f"{key}: {shown}" + (f" (+{more} more)" if more > 0 else ""))
        else:
            parts.append(f"{key}: {value}")
    return "; ".join(parts)


def _compilation_lines(mb: ModernizationBundle) -> list[str]:
    """Facts about the Java compilation beyond its one-line stage summary."""
    compilation = mb.compilation
    if compilation is None:
        return []
    lines = [
        "Java compilation details: "
        f"{'succeeded' if compilation.success else 'failed'} with JDK "
        f"{compilation.jdk_version}; {len(compilation.errors)} error(s), "
        f"{len(compilation.warnings)} warning(s); "
        f"{len(compilation.file_records)} file(s) compiled in "
        f"{compilation.duration_s:.1f}s."
    ]
    if compilation.timed_out:
        lines.append("The compilation timed out.")
    for diagnostic in compilation.errors[:_MAX_LIST_ITEMS]:
        lines.append(f"Compiler error: {diagnostic.message}")
    return lines


def build_validation_chunk(
    bundle: AnalysisBundle, mb: ModernizationBundle, filename: str
) -> RetrievalResult:
    """
    Render the Validation Center results for *filename* as one evidence chunk.

    Args:
        bundle: The analysis bundle for the file.
        mb: The modernization bundle (generation, compilation, tests, ...).
        filename: The file the results are for.

    Returns:
        A chunk whose text lists the overall status and every stage's status
        and summary (with its key details), followed by the compilation
        details. Every figure in it comes from the same computation the
        Validation Center uses, so nothing is restated or invented here.
    """
    stages = compute_validation_stages(bundle, mb)
    overall = compute_overall_status(stages)

    lines = [
        f"Validation Center results for {filename} "
        f"(overall status: {overall.value}). Statuses are PASS, FAIL, "
        "INCONCLUSIVE or NOT_AVAILABLE; a stage that could not run is never PASS."
    ]
    for stage in stages:
        line = f"- {stage.stage}: {stage.status.value} - {stage.summary}"
        detail = _detail_text(stage.details)
        if detail:
            line += f" ({detail})"
        lines.append(line)
    lines.extend(_compilation_lines(mb))

    content = "\n".join(lines)
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]
    return RetrievalResult(
        chunk_id=f"{VALIDATION_CHUNK_TYPE}-{digest}",
        document_id=filename,
        content=content,
        chunk_index=0,
        metadata={"chunk_type": VALIDATION_CHUNK_TYPE, "filename": filename},
        score=0.0,
    )
