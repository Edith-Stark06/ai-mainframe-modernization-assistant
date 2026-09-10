"""
Shared workspace/source-file resolution for modernization API routes.

Promoted out of ``app.api.routers.modernization`` (where it was a
private helper) so the new Phase 12 architecture/java/validation/report
routers reuse the exact same workspace lookup + path-traversal guard
instead of a fourth copy of it.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException

from app.core.exceptions import ResourceNotFoundException
from app.ingestion.workspace import WorkspaceManager

__all__ = ["resolve_workspace_source"]


def resolve_workspace_source(
    workspace_id: uuid.UUID,
    filename: str,
    workspace_manager: WorkspaceManager,
) -> Path:
    """Resolve ``filename`` within ``workspace_id``, guarding against a
    missing workspace, an invalid filename, path traversal outside the
    workspace root, and a missing source file."""
    try:
        ws = workspace_manager.get(str(workspace_id))
    except ResourceNotFoundException:
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        ws_root = Path(ws.path).resolve()
        source_path = (ws_root / filename).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid filename format")

    if not source_path.is_relative_to(ws_root):
        raise HTTPException(status_code=403, detail="Forbidden path traversal detected")
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source file not found")
    return source_path
