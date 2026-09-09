"""#127 — structured compilation result + diagnostics with COBOL mapping."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.java_modernization.architecture.models import SourceRef
from app.java_modernization.version import COMPILATION_VERSION

__all__ = [
    "DiagnosticSeverity",
    "CompilerDiagnostic",
    "GeneratedFileRecord",
    "CompilationResult",
]


class DiagnosticSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    NOTE = "NOTE"


class CompilerDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: DiagnosticSeverity
    message: str
    file: str | None = None  # project-relative
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    error_code: str | None = None
    #: best-effort mapping of this Java location back to COBOL (#125/#126)
    cobol_source_mapping: SourceRef | None = None
    business_rule_ids: tuple[str, ...] = ()
    architecture_component_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class GeneratedFileRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    sha256: str
    classes: tuple[str, ...] = ()
    source_locations: tuple[SourceRef, ...] = ()


class CompilationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool
    compilation_version: str = COMPILATION_VERSION
    diagnostics: tuple[CompilerDiagnostic, ...] = ()
    file_records: tuple[GeneratedFileRecord, ...] = ()
    command: tuple[str, ...] = ()
    duration_s: float = 0.0
    timed_out: bool = False
    output_truncated: bool = False
    jdk_version: str = "unknown"
    workspace: str = ""
    raw_output: str = ""

    @property
    def errors(self) -> tuple[CompilerDiagnostic, ...]:
        return tuple(
            d for d in self.diagnostics if d.severity is DiagnosticSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[CompilerDiagnostic, ...]:
        return tuple(
            d for d in self.diagnostics if d.severity is DiagnosticSeverity.WARNING
        )

    def diagnostic_signature(self) -> str:
        import hashlib

        key = "|".join(
            f"{d.severity.value}:{d.file}:{d.line}:{d.message[:60]}"
            for d in sorted(
                self.diagnostics,
                key=lambda x: (x.file or "", x.line or 0, x.message),
            )
        )
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["error_count"] = len(self.errors)
        d["warning_count"] = len(self.warnings)
        d["diagnostic_signature"] = self.diagnostic_signature()
        return d
