"""#126 — Java code generation (project assembly + traceability)."""

from __future__ import annotations

from app.java_modernization.generation.generator import generate_project
from app.java_modernization.generation.models import (
    GeneratedJavaArtifact,
    GeneratedProject,
    MappingStatus,
)

__all__ = [
    "generate_project",
    "GeneratedProject",
    "GeneratedJavaArtifact",
    "MappingStatus",
]
