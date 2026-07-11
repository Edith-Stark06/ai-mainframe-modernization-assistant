"""
Upload API Router.

Purpose:
    Expose the ``POST /api/v1/upload`` endpoint that accepts multipart
    file uploads and delegates ingestion to the application service layer.

Responsibilities:
    - Accept one or more files via ``multipart/form-data``.
    - Delegate all business logic to
      :class:`app.ingestion.service.IngestionService`.
    - Serialise the :class:`~app.ingestion.models.IngestionResult` into
      an :class:`~app.api.schemas.upload.UploadResponse`.
    - Keep route handler code thin — no business logic here.
    - Log request entry and completion at DEBUG / INFO level.

Dependencies:
    - fastapi                   — :class:`fastapi.APIRouter`,
                                  :class:`fastapi.UploadFile`,
                                  :class:`fastapi.File`
    - app.api.schemas.upload    — :class:`UploadResponse`,
                                  :class:`FileMetadataSchema`
    - app.core.logging          — Loguru logger
    - app.ingestion.service     — :class:`IngestionService`

Examples:
    The router is mounted in ``app.api.router``:

        from app.api.routers.upload import router as upload_router
        api_router.include_router(upload_router)

    Example cURL:

        curl -X POST http://localhost:8000/api/v1/upload \\
             -F "files=@payroll.cbl" \\
             -F "files=@batch.jcl"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from fastapi import APIRouter, File, UploadFile

from app.api.schemas.upload import FileMetadataSchema, UploadResponse
from app.core.logging import logger
from app.ingestion.service import IngestionService

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=UploadResponse,
    status_code=200,
    summary="Upload mainframe source files",
    description=(
        "Accept one or more mainframe source files (COBOL, JCL, Copybook, "
        "plain text) or ZIP archives via multipart/form-data upload. "
        "Each file is validated, persisted to an isolated workspace, and "
        "its metadata is extracted and returned. "
        "Supported extensions: .cbl, .cob, .cpy, .jcl, .txt, .zip."
    ),
)
async def upload_files(
    files: list[UploadFile] = File(
        ...,
        description=(
            "One or more mainframe source files. "
            "Supported: .cbl, .cob, .cpy, .jcl, .txt, .zip."
        ),
    ),
) -> UploadResponse:
    """
    Ingest one or more uploaded mainframe files.

    The handler is intentionally thin — it delegates the complete
    ingestion pipeline to :class:`~app.ingestion.service.IngestionService`
    and maps the result to the API response schema.

    Args:
        files: Multipart-uploaded files from the request.

    Returns:
        :class:`~app.api.schemas.upload.UploadResponse` with the workspace
        ID, per-file metadata, and total file count.

    Raises:
        ValidationException: Propagated from the service if any file
            fails validation (returned as 422 by the global handler).
        InternalServerException: Propagated from the service on unexpected
            I/O errors (returned as 500 by the global handler).
    """
    logger.debug("Upload endpoint: received {} file(s).", len(files))

    service = IngestionService()
    result = await service.ingest(files)

    file_schemas = [FileMetadataSchema(**meta.model_dump()) for meta in result.files]

    response = UploadResponse(
        workspace_id=result.workspace.workspace_id,
        files=file_schemas,
        total_files=result.total_files,
        message=f"{result.total_files} file(s) ingested successfully.",
    )

    logger.info(
        "Upload endpoint: ingestion complete — workspace='{}', files={}.",
        result.workspace.workspace_id,
        result.total_files,
    )
    return response
