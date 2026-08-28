"""
Analysis API Router.

Purpose:
    Expose the ``POST /api/v1/workspaces/{workspace_id}/analyze`` endpoint
    that triggers COBOL source analysis through the production
    :class:`~app.analysis.service.AnalysisService`.

Responsibilities:
    - Resolve the requested source file within an existing workspace.
    - Validate the source file extension against allowed analysis types.
    - Delegate analysis to :class:`~app.analysis.service.AnalysisService`.
    - Serialize the :class:`~app.analysis.models.AnalysisResult` using
      TASK-043 serializers.
    - Return a typed :class:`~app.api.schemas.analysis.AnalysisResponse`.
    - Keep route handlers thin — no business logic here.
    - Log every request at DEBUG level and completion at INFO level.

Non-responsibilities:
    - Compiler pipeline implementation.
    - AST / IR / diagnostic serialization logic.
    - Workspace creation or file ingestion.

Dependencies:
    - fastapi                       — :class:`fastapi.APIRouter`
    - app.api.schemas.analysis      — :class:`AnalysisRequest`,
                                      :class:`AnalysisResponse`
    - app.core.config               — ``settings.workspace_dir``
    - app.core.exceptions           — :class:`ResourceNotFoundException`,
                                      :class:`ValidationException`
    - app.core.logging              — Loguru logger
    - app.analysis.service          — :class:`AnalysisService`
    - app.analysis.serializers.ast  — :func:`serialize_ast`
    - app.analysis.serializers.ir   — :func:`serialize_ir`
    - app.analysis.serializers.diagnostics — :func:`serialize_diagnostics`

Examples:
    The router is mounted in ``app.api.router``::

        from app.api.routers.analysis import router as analysis_router
        api_router.include_router(analysis_router)

    Example request::

        POST /api/v1/workspaces/ws-uuid/analyze
        Content-Type: application/json

        { "filename": "payroll.cbl" }

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends

from app.ai.orchestration.models import AICapability
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.ai.providers.errors import LLMProviderUnavailableError

from app.analysis.dependencies.graph import DependencyGraph
from app.analysis.dependencies.resolver import WorkspaceDependencyResolver
from app.analysis.dependencies.summary import DependencyAnalysisSummary
from app.analysis.serializers.ast import serialize_ast
from app.analysis.serializers.diagnostics import serialize_diagnostics
from app.analysis.serializers.ir import serialize_ir
from app.analysis.serializers.dependencies import serialize_dependencies
from app.analysis.service import AnalysisService
from app.analysis.rules.extractor import BusinessRuleExtractor
from app.analysis.rules.normalization import normalize_business_rule
from app.api.schemas.rules import BusinessRuleResponse
from app.backend.java.generator import BackendSeverity
from app.api.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisSourceMetadata,
    AnalysisStatus,
)
from app.ai.results.normalization import normalize_result
from app.api.schemas.ai import AIResultResponse
from app.api.schemas.dependencies import (
    DependencyAnalysisSummaryResponse,
    DependencyGraphEdgeResponse,
    DependencyGraphNodeResponse,
    DependencyGraphResponse,
    DependencyResponse,
    PositionResponse,
)
from app.api.dependencies.ai import get_ai_orchestrator
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.logging import logger
from app.ingestion.workspace import WorkspaceManager
from app.workspace.inventory import InventoryBuilder

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/workspaces",
    tags=["Analysis"],
)


# ---------------------------------------------------------------------------
# Supported analysis extensions
# ---------------------------------------------------------------------------

_ALLOWED_ANALYSIS_EXTENSIONS: frozenset[str] = frozenset({".cbl", ".cob"})

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/analyze",
    response_model=AnalysisResponse,
    summary="Analyze a COBOL source file",
    description=(
        "Resolve a COBOL source file within the specified workspace, "
        "run the full analysis pipeline through AnalysisService, and "
        "return the generated Java source, serialized AST, serialized IR, "
        "and any collected diagnostics."
    ),
)
async def analyze_source(
    workspace_id: str,
    request: AnalysisRequest,
    orchestrator: AIAnalysisOrchestrator | None = Depends(get_ai_orchestrator),
) -> AnalysisResponse:
    """
    Analyze a COBOL source file within an existing workspace.

    Args:
        workspace_id: UUID4 string identifying the workspace.
        request:      :class:`AnalysisRequest` containing the source filename.

    Returns:
        :class:`~app.api.schemas.analysis.AnalysisResponse` with the
        serialized analysis result.

    Raises:
        ResourceNotFoundException: If the workspace or source file does not
            exist (→ 404).
        ValidationException: If the requested file has an unsupported
            extension (→ 422).
    """
    logger.debug(
        "Analysis endpoint: workspace_id='{}', filename='{}'.",
        workspace_id,
        request.filename,
    )

    # ------------------------------------------------------------------
    # Resolve workspace through WorkspaceManager
    # ------------------------------------------------------------------
    workspace_manager = WorkspaceManager()
    try:
        workspace_record = workspace_manager.get(workspace_id)
    except ResourceNotFoundException:
        logger.warning("Analysis endpoint: workspace '{}' not found.", workspace_id)
        raise
    workspace_root = Path(workspace_record.path)

    # ------------------------------------------------------------------
    # Resolve and validate source file
    # ------------------------------------------------------------------
    source_path = (workspace_root / request.filename).resolve()

    # Path traversal prevention: ensure the resolved path is within the workspace.
    try:
        source_path.relative_to(workspace_root)
    except ValueError:
        logger.warning(
            "Analysis endpoint: path traversal attempt '{}' in workspace '{}'.",
            request.filename,
            workspace_id,
        )
        raise ValidationException(
            message="Invalid filename: path traversal is not allowed.",
            details={"filename": request.filename},
        )

    if not source_path.is_file():
        logger.warning(
            "Analysis endpoint: source file '{}' not found in workspace '{}'.",
            request.filename,
            workspace_id,
        )
        raise ResourceNotFoundException(
            resource="source",
            identifier=request.filename,
        )

    if source_path.suffix.lower() not in _ALLOWED_ANALYSIS_EXTENSIONS:
        logger.warning(
            "Analysis endpoint: unsupported extension '{}' for file '{}'.",
            source_path.suffix,
            request.filename,
        )
        raise ValidationException(
            message=(
                f"Unsupported file extension '{source_path.suffix}'. "
                f"Allowed extensions: {', '.join(sorted(_ALLOWED_ANALYSIS_EXTENSIONS))}."
            ),
            details={"filename": request.filename, "extension": source_path.suffix},
        )

    # ------------------------------------------------------------------
    # Generate correlation ID
    # ------------------------------------------------------------------
    analysis_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Compute source metadata
    # ------------------------------------------------------------------
    inventory_builder = InventoryBuilder()
    inventory = inventory_builder.build(workspace_id, workspace_root)

    target_path = str(source_path)
    scanned_file = next((f for f in inventory.files if f.path == target_path), None)

    if not scanned_file:
        logger.warning(
            "Analysis endpoint: source file '{}' not found in workspace inventory '{}'.",
            request.filename,
            workspace_id,
        )
        raise ResourceNotFoundException(
            resource="source",
            identifier=request.filename,
        )

    source_metadata = AnalysisSourceMetadata(
        extension=scanned_file.extension,
        size_bytes=scanned_file.size_bytes,
        sha256=scanned_file.sha256,
    )

    # ------------------------------------------------------------------
    # Run analysis
    # ------------------------------------------------------------------
    service = AnalysisService()
    result = service.analyze_file(source_path)

    # ------------------------------------------------------------------
    # Serialize result
    # ------------------------------------------------------------------
    serialized_ast = serialize_ast(result.ast) if result.ast is not None else None
    serialized_ir = serialize_ir(result.ir) if result.ir is not None else None
    serialized_diagnostics = serialize_diagnostics(
        result.semantic_diagnostics + result.backend_diagnostics
    )

    serialized_dependencies = [
        DependencyResponse.model_validate(dep)
        for dep in serialize_dependencies(result.dependencies)
    ]

    # ------------------------------------------------------------------
    # Compute Dependency Summary and Graph
    # ------------------------------------------------------------------
    dependency_summary = None
    dependency_graph = None
    business_rules = None
    if result.ast is not None:
        program_name = source_path.stem.upper()
        ident_div = getattr(result.ast, "identification_division", None)
        if ident_div is not None:
            pid_node = getattr(ident_div, "program_id", None)
            if pid_node is not None:
                program_name = pid_node.value.upper()

        graph = DependencyGraph.from_dependencies(program_name, result.dependencies)
        resolver = WorkspaceDependencyResolver()
        resolutions = resolver.resolve(graph, inventory)
        summary = DependencyAnalysisSummary.from_results(graph, resolutions)

        dependency_summary = DependencyAnalysisSummaryResponse(
            node_count=summary.node_count,
            edge_count=summary.edge_count,
            resolved_target_count=summary.resolved_target_count,
            unresolved_target_count=summary.unresolved_target_count,
            ambiguous_target_count=summary.ambiguous_target_count,
            dependency_counts={k.name: v for k, v in summary.dependency_counts.items()},
        )

        dependency_graph = DependencyGraphResponse(
            nodes=[
                DependencyGraphNodeResponse(identifier=node.identifier)
                for node in graph.nodes
            ],
            edges=[
                DependencyGraphEdgeResponse(
                    source=edge.source,
                    target=edge.target,
                    dependency_type=edge.dependency_type.name,  # type: ignore[arg-type]
                    source_location=(
                        PositionResponse(
                            type="Position",
                            line=edge.source_location.line,
                            column=edge.source_location.column,
                            offset=edge.source_location.offset,
                            filename=edge.source_location.filename,
                        )
                        if edge.source_location
                        else None
                    ),
                )
                for edge in graph.edges
            ],
        )

        # ------------------------------------------------------------------
        # Extract Business Rules
        # ------------------------------------------------------------------
        extractor = BusinessRuleExtractor()
        extracted_rules = extractor.extract(result.ast)
        business_rules = []
        for rule in extracted_rules:
            normalized_rule = normalize_business_rule(rule)
            source_loc = None
            if normalized_rule.source_location:
                source_loc = PositionResponse(
                    type="Position",
                    line=normalized_rule.source_location.line,
                    column=normalized_rule.source_location.column,
                    offset=normalized_rule.source_location.offset,
                    filename=normalized_rule.source_location.filename,
                )

            business_rules.append(
                BusinessRuleResponse(
                    condition=normalized_rule.condition,
                    actions=list(normalized_rule.actions),
                    source_location=source_loc,
                )
            )

    # ------------------------------------------------------------------
    # AI Analysis Orchestration
    # ------------------------------------------------------------------
    ai_analysis = None
    if request.ai_capabilities and result.success and source_path.is_file():
        if orchestrator is None:
            logger.error("AI Provider is unavailable (not configured)")
            status = AnalysisStatus.INTERNAL_ERROR
            result.error = Exception("Production LLM provider is not yet configured.")
        else:
            try:
                with open(source_path, "r", encoding="utf-8") as f:
                    source_text = f.read()

                # Construct phase-1 context to pass to orchestrator
                ai_context = {
                    "correlation_id": analysis_id,
                    "dependencies": result.dependencies,
                    "dependency_summary": dependency_summary,
                    "dependency_graph": dependency_graph,
                    "business_rules": business_rules,
                    "diagnostics": result.semantic_diagnostics
                    + result.backend_diagnostics,
                    "source_metadata": source_metadata,
                }

                # Map capabilities
                domain_capabilities = set()
                for cap in request.ai_capabilities:
                    if cap.name == "EXPLANATION":
                        domain_capabilities.add(AICapability.EXPLANATION)
                    elif cap.name == "DOCUMENTATION":
                        domain_capabilities.add(AICapability.DOCUMENTATION)

                ai_result_raw = orchestrator.analyze(
                    source=source_text,
                    capabilities=domain_capabilities,
                    context=ai_context,
                )

                normalized_result = normalize_result(ai_result_raw)
                ai_analysis = AIResultResponse.model_validate(
                    normalized_result.to_dict()
                )
            except LLMProviderUnavailableError as e:
                logger.error("AI Provider failed during analysis: {}", e)
                status = AnalysisStatus.INTERNAL_ERROR
                result.error = e
            except Exception as e:
                logger.exception("Unexpected error during AI orchestration")
                status = AnalysisStatus.INTERNAL_ERROR
                result.error = Exception(f"AI analysis failed: {e}")

    if result.error is not None:
        status = AnalysisStatus.INTERNAL_ERROR
    elif any(
        diagnostic.severity is BackendSeverity.ERROR
        for diagnostic in result.backend_diagnostics
    ):
        status = AnalysisStatus.ANALYSIS_ERROR
    elif not result.success:
        status = AnalysisStatus.ANALYSIS_ERROR
    else:
        status = AnalysisStatus.SUCCESS

    response = AnalysisResponse(
        success=result.success,
        status=status,
        analysis_id=analysis_id,
        workspace_id=workspace_id,
        filename=request.filename,
        source_metadata=source_metadata,
        java_source=result.java_source,
        ast=serialized_ast,
        ir=serialized_ir,
        diagnostics=serialized_diagnostics,
        dependencies=serialized_dependencies,
        dependency_summary=dependency_summary,
        dependency_graph=dependency_graph,
        business_rules=business_rules,
        error=str(result.error) if result.error is not None else None,
        ai_analysis=ai_analysis,
    )

    logger.info(
        "Analysis endpoint: completed — workspace='{}', file='{}', success={}.",
        workspace_id,
        request.filename,
        result.success,
    )
    return response
