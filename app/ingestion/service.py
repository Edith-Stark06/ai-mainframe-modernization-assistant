"""
File Ingestion Service.

Purpose:
    Orchestrate the complete file ingestion pipeline for a single upload
    request.  This is the primary application-service layer component that
    the API router delegates to.

Responsibilities:
    - Accept one or more :class:`fastapi.UploadFile` objects.
    - Validate each file via :class:`app.ingestion.validator.FileValidator`.
    - Create an isolated workspace via
      :class:`app.ingestion.workspace.WorkspaceManager`.
    - Persist each file (or expanded ZIP contents) via
      :class:`app.ingestion.uploader.FileUploader`.
    - Extract :class:`app.ingestion.models.FileMetadata` for each saved
      file via :class:`app.ingestion.metadata.MetadataExtractor`.
    - Return an :class:`app.ingestion.models.IngestionResult` to the caller.
    - Clean up the workspace on error so no orphaned directories remain.

Dependencies:
    - fastapi                   — :class:`fastapi.UploadFile`
    - app.core.exceptions       — :class:`ValidationException`,
                                  :class:`InternalServerException`
    - app.core.logging          — Loguru logger
    - app.ingestion.metadata    — :class:`MetadataExtractor`
    - app.ingestion.models      — :class:`FileMetadata`, :class:`IngestionResult`
    - app.ingestion.uploader    — :class:`FileUploader`
    - app.ingestion.validator   — :class:`FileValidator`
    - app.ingestion.workspace   — :class:`WorkspaceManager`

Examples:
    Using the service from a route handler::

        from app.ingestion.service import IngestionService

        service = IngestionService()
        result = await service.ingest(files)
        return result

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from fastapi import UploadFile

from app.core.exceptions import InternalServerException
from app.core.logging import logger
from app.ingestion.metadata import MetadataExtractor
from app.ingestion.models import FileMetadata, IngestionResult
from app.ingestion.uploader import FileUploader
from app.ingestion.validator import FileValidator
from app.ingestion.workspace import WorkspaceManager

__all__ = ["IngestionService"]


class IngestionService:
    """
    Application service that orchestrates the file ingestion pipeline.

    The service is designed to be instantiated per-request (or as a
    FastAPI dependency) and is stateless beyond its collaborators.

    Attributes:
        _validator:  :class:`FileValidator` instance.
        _workspace:  :class:`WorkspaceManager` instance.
        _uploader:   :class:`FileUploader` instance.
        _extractor:  :class:`MetadataExtractor` instance.
    """

    def __init__(self) -> None:
        """Initialise the service with its required collaborators."""
        self._validator = FileValidator()
        self._workspace = WorkspaceManager()
        self._uploader = FileUploader()
        self._extractor = MetadataExtractor()

    async def ingest(self, files: list[UploadFile]) -> IngestionResult:
        """
        Run the complete ingestion pipeline for a list of uploaded files.

        The pipeline is:
        1. Collect all file bytes from the ASGI upload stream.
        2. Validate filenames for duplicate detection.
        3. Validate each file's extension, non-emptiness, and size.
        4. Create a workspace directory.
        5. Save / expand each file.
        6. Extract metadata for each saved file.
        7. Return the aggregated :class:`IngestionResult`.

        If any error occurs after the workspace is created, the workspace
        is cleaned up before re-raising the exception.

        Args:
            files: List of :class:`~fastapi.UploadFile` objects from the
                   multipart request.

        Returns:
            An :class:`~app.ingestion.models.IngestionResult` containing
            the workspace record and per-file metadata.

        Raises:
            ValidationException: If any file fails validation checks.
            InternalServerException: If an unexpected I/O error occurs
                during workspace creation or file writing.
        """
        logger.info("IngestionService: starting ingestion for {} file(s).", len(files))

        # ------------------------------------------------------------------
        # Step 1: Read all file bytes up-front so we can validate before
        #         touching the filesystem.
        # ------------------------------------------------------------------
        file_data: list[tuple[str, bytes]] = []
        for upload in files:
            filename = upload.filename or "unknown"
            content = await upload.read()
            file_data.append((filename, content))
            logger.debug(
                "IngestionService: read '{}' ({} bytes).", filename, len(content)
            )

        # ------------------------------------------------------------------
        # Step 2: Validate for duplicates across the whole batch.
        # ------------------------------------------------------------------
        self._validator.validate_no_duplicates([fn for fn, _ in file_data])

        # ------------------------------------------------------------------
        # Step 3: Per-file validation (extension, empty, size).
        # ------------------------------------------------------------------
        for filename, content in file_data:
            self._validator.validate_extension(filename)
            self._validator.validate_not_empty(content, filename)
            self._validator.validate_size(content, filename)

        # ------------------------------------------------------------------
        # Step 4: Create workspace.
        # ------------------------------------------------------------------
        workspace_record = self._workspace.create()
        workspace_path = self._workspace.workspace_path(workspace_record.workspace_id)

        # ------------------------------------------------------------------
        # Steps 5–6: Save files and extract metadata, rolling back on error.
        # ------------------------------------------------------------------
        metadata_records: list[FileMetadata] = []
        try:
            for filename, content in file_data:
                ext = filename[filename.rfind(".") :].lower() if "." in filename else ""

                if ext == ".zip":
                    # Expand ZIP and process each member
                    expanded = self._uploader.expand_zip(workspace_path, content)
                    for member_name, member_content in expanded:
                        meta = self._extractor.extract(
                            filename=member_name,
                            content=member_content,
                            workspace_id=workspace_record.workspace_id,
                        )
                        metadata_records.append(meta)
                else:
                    self._uploader.save_file(workspace_path, filename, content)
                    meta = self._extractor.extract(
                        filename=filename,
                        content=content,
                        workspace_id=workspace_record.workspace_id,
                    )
                    metadata_records.append(meta)

        except Exception as exc:
            # Clean up the workspace to avoid orphaned directories.
            self._workspace.delete(workspace_record.workspace_id)
            logger.error(
                "IngestionService: error during ingestion, "
                "workspace '{}' cleaned up. Cause: {}",
                workspace_record.workspace_id,
                exc,
            )
            if isinstance(exc, (InternalServerException,)):
                raise
            raise InternalServerException(
                message="An unexpected error occurred during file ingestion.",
                details={"cause": str(exc)},
            ) from exc

        result = IngestionResult(
            workspace=workspace_record,
            files=metadata_records,
            total_files=len(metadata_records),
        )

        logger.info(
            "IngestionService: ingestion complete — workspace='{}', files={}.",
            workspace_record.workspace_id,
            result.total_files,
        )
        return result
