"""
Shared "resolve -> analyze -> modernize" entry point for the
architecture / java / validation / report API routes.

This is the adapter's single point of contact with the deterministic
pipeline: it resolves the requested workspace file, builds the
existing Phase 1-5 :class:`AnalysisBundle`
(``app.dataset.analysis_bundle.build_analysis_bundle``, already used by
``/analyze``), and the existing Phase 9-11
:class:`~app.dataset.modernization_bundle.ModernizationBundle`
(architecture/generation/compilation/behavioral validation). Every
route builds on the SAME two calls -- nothing here re-implements
analysis or modernization.

The result is cached per ``(workspace_id, filename, source_sha256)``
via :mod:`app.api.services.pipeline_cache` so that Architecture,
COBOL<->Java, Validation Center, and Report -- four independent HTTP
requests -- reuse one pipeline run for the same file instead of each
re-running analysis, architecture generation, Java generation,
compilation, and behavioral validation from scratch. See that module's
docstring for the full cache design and safety rationale.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.api.dependencies.workspace import resolve_workspace_source
from app.api.services.pipeline_cache import CacheValue, PipelineCache
from app.core.logging import logger
from app.dataset.analysis_bundle import build_analysis_bundle
from app.dataset.modernization_bundle import build_modernization_bundle
from app.ingestion.workspace import WorkspaceManager

__all__ = ["run_pipeline_for_source"]

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _source_id_for(workspace_id: uuid.UUID, filename: str) -> str:
    stem = Path(filename).stem
    safe_stem = _SAFE_ID_RE.sub("-", stem) or "SOURCE"
    return f"{safe_stem}-{str(workspace_id)[:8]}"


def run_pipeline_for_source(
    workspace_id: uuid.UUID,
    filename: str,
    workspace_manager: WorkspaceManager,
    cache: PipelineCache,
) -> CacheValue:
    """Resolve ``filename`` in ``workspace_id`` and return its
    ``(AnalysisBundle, ModernizationBundle)``, reusing a cached result
    for the exact same workspace + file content when available.

    ``cache`` is a required parameter, not a ``Depends(...)`` default:
    this is a plain function, not itself a FastAPI-invoked route
    handler, so a ``Depends(...)`` default here would never actually be
    resolved -- FastAPI only resolves dependencies for parameters of
    functions it calls directly (route handlers, or dependencies of
    dependencies it calls). Callers (the four routers) each declare
    ``cache: PipelineCache = Depends(get_pipeline_cache)`` on their own
    route handler and pass it through explicitly -- the same pattern
    already used here for ``workspace_manager``.
    """
    source_path = resolve_workspace_source(workspace_id, filename, workspace_manager)

    try:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.error("Could not read {}: {}", source_path, e)
        raise HTTPException(status_code=500, detail="Source file could not be read")

    source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    key = (str(workspace_id), filename, source_sha256)

    def _build() -> CacheValue:
        source_id = _source_id_for(workspace_id, filename)
        work_dir = Path(tempfile.mkdtemp(prefix="modernization-api-"))
        try:
            bundle = build_analysis_bundle(
                source_id, source_text, work_dir / "analysis"
            )
        except Exception as e:
            logger.error("Analysis failed for {}: {}", source_path, e)
            raise HTTPException(status_code=500, detail="Analysis failed")
        mb = build_modernization_bundle(bundle, workspace_root=work_dir / "modernize")
        return bundle, mb

    return cache.get_or_build(key, _build)
