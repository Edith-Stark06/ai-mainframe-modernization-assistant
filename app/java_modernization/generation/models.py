"""#126 — generated-Java-project model with full COBOL traceability."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.java_modernization.architecture.models import SourceRef, UnsupportedBehavior
from app.java_modernization.version import GENERATION_VERSION

__all__ = ["MappingStatus", "GeneratedJavaArtifact", "GeneratedProject"]

MAPPING_MAPPED = "mapped"
MAPPING_UNAVAILABLE = "unavailable"


class MappingStatus:
    MAPPED = MAPPING_MAPPED
    UNAVAILABLE = MAPPING_UNAVAILABLE


class GeneratedJavaArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    file_path: str  # project-relative, forward slashes
    class_name: str
    method_name: str | None = None
    kind: str  # "class" | "method" | "record" | "manifest"
    source_locations: tuple[SourceRef, ...] = ()
    mapping_status: str = MAPPING_UNAVAILABLE
    architecture_component_id: str | None = None
    business_rule_ids: tuple[str, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    unsupported_behaviors: tuple[UnsupportedBehavior, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class GeneratedProject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    generation_version: str = GENERATION_VERSION
    source_id: str
    architecture_id: str
    main_class: str
    #: project-relative path -> file content (compilable .java only)
    files: dict[str, str]
    artifacts: tuple[GeneratedJavaArtifact, ...] = ()
    assumptions: tuple[str, ...] = ()
    unsupported_behaviors: tuple[UnsupportedBehavior, ...] = ()
    generator_diagnostics: tuple[dict[str, str], ...] = ()
    semantic_equivalence_verified: bool = False

    @property
    def java_files(self) -> dict[str, str]:
        return {p: c for p, c in self.files.items() if p.endswith(".java")}

    def content_hash(self) -> str:
        payload = json.dumps(
            {
                p: hashlib.sha256(c.encode()).hexdigest()
                for p, c in sorted(self.files.items())
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def write(self, root: str | Path) -> Path:
        base = Path(root)
        for rel, content in self.files.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        return base

    def manifest(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "generation_version": self.generation_version,
            "source_id": self.source_id,
            "architecture_id": self.architecture_id,
            "main_class": self.main_class,
            "content_hash": self.content_hash(),
            "files": sorted(self.files.keys()),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "assumptions": list(self.assumptions),
            "unsupported_behaviors": [
                u.model_dump(mode="json") for u in self.unsupported_behaviors
            ],
            "generator_diagnostics": [dict(d) for d in self.generator_diagnostics],
            "semantic_equivalence_verified": self.semantic_equivalence_verified,
            "note": (
                "This is a modernization CANDIDATE. Compilation success does not "
                "imply behavioral equivalence — Phase 10 owns that."
            ),
        }
