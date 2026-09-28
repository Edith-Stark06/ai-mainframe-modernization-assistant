"""
JCL Analysis API Router.

Purpose:
    Expose :class:`~app.jcl.service.JclAnalysisService` over HTTP --
    the JCL analogue of ``/analyze`` for COBOL. Before this router, the
    JCL parser built in task #stage46 had zero API or frontend wiring:
    it was exercised only by ``tests/jcl/``. This closes that gap so a
    ``.jcl`` file uploaded to a workspace is actually analyzable, not
    just parseable in isolation.

Responsibilities:
    - ``POST /workspaces/{workspace_id}/jcl/analyze`` -- resolve
      *filename* within the workspace, run
      :class:`~app.jcl.service.JclAnalysisService`, and return the
      serialized result.

Non-responsibilities:
    - JCL lexing/parsing itself (delegated to :mod:`app.jcl`).
    - Cross-referencing a step's ``PGM=`` target against workspace
      COBOL programs -- that correlation lives in
      :mod:`app.workspace.jcl_correlation`, wired into the
      modernization intelligence endpoint instead, since it is COBOL
      program context, not JCL analysis itself.

Dependencies:
    - app.api.dependencies.workspace -- resolve_workspace_source
    - app.api.schemas.jcl -- JclAnalysisResponse, JclAnalysisRequest
    - app.ingestion.workspace -- WorkspaceManager
    - app.jcl.service -- JclAnalysisService

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies.workspace import resolve_workspace_source
from app.api.schemas.jcl import JclAnalysisRequest, JclAnalysisResponse
from app.core.logging import logger
from app.ingestion.workspace import WorkspaceManager
from app.jcl.service import JclAnalysisService

router = APIRouter(prefix="/workspaces/{workspace_id}/jcl", tags=["jcl"])


def get_jcl_analysis_service() -> JclAnalysisService:
    return JclAnalysisService()


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.post("/analyze", response_model=JclAnalysisResponse)
def execute_jcl_analysis(
    workspace_id: uuid.UUID,
    request: JclAnalysisRequest,
    jcl_service: JclAnalysisService = Depends(get_jcl_analysis_service),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> JclAnalysisResponse:
    """
    Analyze a JCL job stream within a workspace.

    Args:
        workspace_id: UUID4 of the workspace containing the JCL file.
        request: Identifies the ``.jcl`` filename to analyze.
        jcl_service: Injected :class:`JclAnalysisService`.
        workspace_manager: Injected :class:`WorkspaceManager`.

    Returns:
        The serialized :class:`~app.jcl.models.JclAnalysisResult`. Never
        raises for a malformed or partial job stream -- see
        ``JclAnalysisService.analyze_file``'s own contract.
    """
    source_path = resolve_workspace_source(
        workspace_id, request.filename, workspace_manager
    )

    try:
        result = jcl_service.analyze_file(source_path)
    except Exception as e:
        logger.error(f"JCL analysis failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="JCL analysis failed")

    return JclAnalysisResponse(**result.to_dict())
