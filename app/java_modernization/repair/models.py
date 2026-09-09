"""#128 — structured self-repair models."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.java_modernization.architecture.models import SourceRef
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.version import REPAIR_VERSION

__all__ = [
    "FileChange",
    "FilePatch",
    "RepairPatch",
    "RepairAttempt",
    "RepairResult",
]


class FileChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    replacement: str


class FilePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    changes: tuple[FileChange, ...]


class RepairPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    files: tuple[FilePatch, ...] = ()
    explanation: str = ""
    #: context refs (E1, E2, …) the model says it based the fix on
    source_basis: tuple[str, ...] = ()

    def signature(self) -> str:
        payload = json.dumps(
            [
                {
                    "path": fp.path,
                    "changes": [c.model_dump() for c in fp.changes],
                }
                for fp in sorted(self.files, key=lambda x: x.path)
            ],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def is_empty(self) -> bool:
        return not self.files or all(not fp.changes for fp in self.files)


class RepairAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_number: int
    original_error_count: int
    original_diagnostic_signature: str
    affected_files: tuple[str, ...] = ()
    affected_source_locations: tuple[SourceRef, ...] = ()
    context_refs: tuple[str, ...] = ()
    proposed_patch: RepairPatch | None = None
    patch_applied: bool = False
    reject_reason: str | None = None
    compilation_result: CompilationResult | None = None
    remaining_error_count: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        if self.compilation_result is not None:
            d["compilation_result"] = self.compilation_result.to_dict()
        return d


class RepairResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repair_version: str = REPAIR_VERSION
    success: bool
    stopped_reason: str  # "compiled" | "max_attempts" | "no_progress" | "duplicate_patch" | "provider_failure" | "unsafe_patch" | "not_needed"
    attempts: tuple[RepairAttempt, ...] = ()
    initial_error_count: int = 0
    final_error_count: int = 0
    final_files: dict[str, str] = Field(default_factory=dict)
    semantic_equivalence_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_version": self.repair_version,
            "success": self.success,
            "stopped_reason": self.stopped_reason,
            "initial_error_count": self.initial_error_count,
            "final_error_count": self.final_error_count,
            "attempt_count": len(self.attempts),
            "attempts": [a.to_dict() for a in self.attempts],
            "semantic_equivalence_verified": self.semantic_equivalence_verified,
        }
