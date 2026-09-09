"""
Provenance — the source identity every knowledge chunk MUST carry (#122).

The Phase 8 safety invariant: no anonymous context ever reaches the
model. A :class:`Provenance` records *where a piece of knowledge came
from* — the source artifact, the exact location in it where practical,
and the deterministic-analysis identity (rule id, risk id, …) when the
chunk is derived from an analysis object rather than raw text.

Fields that the source genuinely does not provide are ``None`` — never
guessed. Validation (:meth:`Provenance.validate_complete`) rejects a
provenance with no ``source_id``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge.errors import ProvenanceError

__all__ = ["SourceType", "Provenance"]


class SourceType(str, Enum):
    # raw ingested artifacts
    COBOL = "cobol"
    COPYBOOK = "copybook"
    JCL = "jcl"
    DB2_METADATA = "db2_metadata"
    VSAM_METADATA = "vsam_metadata"
    CICS_METADATA = "cics_metadata"
    # deterministic analysis artifacts
    AST = "ast"
    IR = "ir"
    CFG = "cfg"
    DEPENDENCY = "dependency"
    BUSINESS_RULE = "business_rule"
    MODERNIZATION_RISK = "modernization_risk"
    MODERNIZATION_STRATEGY = "modernization_strategy"
    MODERNIZATION_PATTERN = "modernization_pattern"
    # generated artifacts
    GENERATED_JAVA = "generated_java"


_ANALYSIS_TYPES = frozenset(
    {
        SourceType.AST,
        SourceType.IR,
        SourceType.CFG,
        SourceType.DEPENDENCY,
        SourceType.BUSINESS_RULE,
        SourceType.MODERNIZATION_RISK,
        SourceType.MODERNIZATION_STRATEGY,
        SourceType.MODERNIZATION_PATTERN,
    }
)


class Provenance(BaseModel):
    """Immutable source identity for one knowledge chunk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: the program / artifact this knowledge belongs to (e.g. ``CUSTOMER``)
    source_id: str = Field(..., min_length=1)
    source_type: SourceType
    #: workspace-relative path when the chunk came from a file; ``None``
    #: for analysis objects that have no file of their own.
    source_path: str | None = None

    #: 1-based inclusive line span in ``source_path`` (or the owning COBOL
    #: program for analysis chunks) when it is known.
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    # structural location (all optional, never guessed)
    paragraph: str | None = None
    section: str | None = None
    statement: str | None = None
    symbol: str | None = None

    # analysis-object identity
    rule_id: str | None = None
    risk_id: str | None = None
    strategy_id: str | None = None
    pattern_id: str | None = None
    dependency: str | None = None

    # generated-Java location
    java_class: str | None = None
    java_method: str | None = None

    # pipeline versions
    artifact_version: str
    analysis_version: str | None = None

    #: the owning COBOL program for an analysis chunk (so a rule chunk can
    #: point back at ``CUSTOMER.cbl`` even though the rule object has no
    #: file). Equal to ``source_path`` for raw-text chunks.
    program_source_id: str | None = None

    @field_validator("source_id", "source_path", "paragraph", "section", "symbol")
    @classmethod
    def _no_traversal(cls, v: str | None) -> str | None:
        if isinstance(v, str) and ".." in v:
            raise ValueError("provenance strings must not contain '..'")
        return v

    def validate_complete(self) -> "Provenance":
        """Raise :class:`ProvenanceError` unless this provenance is usable."""
        if not self.source_id or not self.source_id.strip():
            raise ProvenanceError("chunk provenance has no source_id")
        if not self.artifact_version:
            raise ProvenanceError(
                f"chunk provenance for {self.source_id!r} has no artifact_version"
            )
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ProvenanceError(
                f"line span for {self.source_id!r} is inverted "
                f"({self.line_start}..{self.line_end})"
            )
        if self.source_type in _ANALYSIS_TYPES and self.analysis_version is None:
            raise ProvenanceError(
                f"analysis chunk for {self.source_id!r} "
                f"({self.source_type.value}) has no analysis_version"
            )
        return self

    @property
    def has_location(self) -> bool:
        return self.line_start is not None or self.paragraph is not None

    def citation(self) -> str:
        """A short, human-readable, non-fabricated source reference."""
        prog = self.program_source_id or self.source_path or self.source_id
        if self.source_type is SourceType.BUSINESS_RULE and self.rule_id:
            base = f"BusinessRule {self.rule_id} (source: {prog})"
        elif self.source_type is SourceType.MODERNIZATION_RISK and self.risk_id:
            base = f"Risk {self.risk_id} (source: {prog})"
        elif self.source_type is SourceType.DEPENDENCY and self.dependency:
            base = f"Dependency {self.dependency} (source: {prog})"
        elif self.source_type is SourceType.GENERATED_JAVA and self.java_class:
            m = f".{self.java_method}" if self.java_method else ""
            base = f"Generated Java {self.java_class}{m} (from {prog})"
        else:
            base = str(prog)
        if self.line_start is not None and self.line_end is not None:
            base += f" lines {self.line_start}–{self.line_end}"
        elif self.line_start is not None:
            base += f" line {self.line_start}"
        if self.paragraph:
            base += f" paragraph {self.paragraph}"
        return base

    def to_metadata(self) -> dict[str, Any]:
        """Flat, queryable, JSON-safe metadata (drops ``None`` values)."""
        raw = self.model_dump(mode="json")
        return {k: v for k, v in raw.items() if v is not None}
