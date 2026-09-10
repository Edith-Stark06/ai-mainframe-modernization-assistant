"""
Java Generation ("COBOL <-> Java") API Schemas.

Wraps the existing, already-typed
:class:`~app.java_modernization.generation.models.GeneratedProject`
(#126, source-mapped via ``GeneratedJavaArtifact.source_locations``)
and :class:`~app.java_modernization.compilation.models.CompilationResult`
(#127) directly. No Java is generated or compiled by the API layer --
it only reports what #126/#127 already produced.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["JavaGenerationResponse"]


class JavaGenerationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str
    filename: str
    available: bool = Field(
        ...,
        description=(
            "False when Java generation could not run (architecture "
            "unavailable, or generation itself failed) -- see 'reason'."
        ),
    )
    reason: str | None = None
    project: GeneratedProject | None = Field(
        default=None,
        description=(
            "The real #126 generated project. 'project.artifacts' carries "
            "the COBOL<->Java mapping: file_path, class/method name, "
            "source_locations, mapping_status, architecture_component_id, "
            "business_rule_ids."
        ),
    )
    compilation: CompilationResult | None = Field(
        default=None,
        description=(
            "The real #127 compilation result for 'project', or null if "
            "generation did not produce a project to compile. Compilation "
            "success is NOT semantic/behavioral equivalence -- see the "
            "Validation Center for that distinction."
        ),
    )
