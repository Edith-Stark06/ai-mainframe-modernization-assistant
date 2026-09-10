"""
Modernization Report API Schema.

Aggregates the SAME artifacts the Architecture, Java, and Validation
Center endpoints already expose into one response -- it does not
recompute any metric independently. Every section reuses an existing
domain model or the shared ``compute_validation_stages`` classification;
nothing here is a second implementation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.validation import StageResult, StageStatus
from app.java_modernization.architecture.models import JavaArchitecture
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["ModernizationReportResponse"]


class ModernizationReportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str
    filename: str
    source_id: str

    # 1. Program overview
    analysis_success: bool
    paragraphs: list[str]

    # 3. Business rules / 5. Risks / 9. Strategy -- raw Phase 4 output,
    # already computed by build_analysis_bundle; not recomputed here.
    business_rules: list[dict[str, Any]] | None
    risks: list[dict[str, Any]] | None
    strategy: dict[str, Any] | None

    # 4. Dependencies (flat list, Phase 1-3)
    dependencies: list[dict[str, Any]] | None

    # 6. Coverage / 7. Confidence -- Phase 5
    coverage: dict[str, Any] | None
    confidence: dict[str, Any] | None

    # 2. Architecture (#125)
    architecture: JavaArchitecture | None
    architecture_reason: str | None

    # 9. Generated Java (#126) / 10. Compilation (#127)
    project: GeneratedProject | None
    generation_reason: str | None
    compilation: CompilationResult | None

    # 11-13. Tests / Behavioral validation / Self-repair -- shared
    # classification with the Validation Center (identical stages).
    validation_stages: list[StageResult]
    overall_status: StageStatus

    # 14. Unsupported constructs (surfaced again at top level for
    # convenience; identical data to the "Unsupported Syntax" stage above)
    unsupported_syntax: dict[str, Any] | None

    # 15. Unresolved issues -- derived by the router from validation_stages
    # (every non-PASS stage, in one place), stored rather than recomputed
    # by every consumer.
    unresolved_issues: list[str] = Field(default_factory=list)
