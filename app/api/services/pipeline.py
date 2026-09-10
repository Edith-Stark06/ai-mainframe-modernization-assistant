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
"""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.api.dependencies.workspace import resolve_workspace_source
from app.core.logging import logger
from app.dataset.analysis_bundle import AnalysisBundle, build_analysis_bundle
from app.dataset.modernization_bundle import (
    ModernizationBundle,
    build_modernization_bundle,
)
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
) -> tuple[AnalysisBundle, ModernizationBundle]:
    source_path = resolve_workspace_source(workspace_id, filename, workspace_manager)

    try:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.error("Could not read {}: {}", source_path, e)
        raise HTTPException(status_code=500, detail="Source file could not be read")

    source_id = _source_id_for(workspace_id, filename)
    work_dir = Path(tempfile.mkdtemp(prefix="modernization-api-"))

    try:
        bundle = build_analysis_bundle(source_id, source_text, work_dir / "analysis")
    except Exception as e:
        logger.error("Analysis failed for {}: {}", source_path, e)
        raise HTTPException(status_code=500, detail="Analysis failed")

    mb = build_modernization_bundle(bundle, workspace_root=work_dir / "modernize")
    return bundle, mb
