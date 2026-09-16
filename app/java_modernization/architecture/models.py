"""
#125 — target Java architecture model.

A :class:`JavaArchitecture` is an *evidence-based* description of the
Java shape a COBOL program should be modernized into. It is derived
deterministically from Phase 1–5 analysis (no LLM). Every component
references — never duplicates — the deterministic business rules,
dependencies and source locations behind it.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.java_modernization.version import ARCHITECTURE_VERSION

__all__ = [
    "ComponentType",
    "SourceRef",
    "Evidence",
    "Assumption",
    "UnsupportedBehavior",
    "ExternalInterface",
    "DataModelElement",
    "ArchitectureComponent",
    "StrategyRef",
    "JavaArchitecture",
]


class ComponentType(str, Enum):
    SERVICE = "SERVICE"
    DOMAIN = "DOMAIN"
    REPOSITORY = "REPOSITORY"
    DTO = "DTO"
    CONFIGURATION = "CONFIGURATION"
    INTEGRATION = "INTEGRATION"


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    source_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    paragraph: str | None = None

    def render(self) -> str:
        loc = self.source_path or f"{self.source_id}.cbl"
        if self.line_start and self.line_end:
            loc += f":{self.line_start}-{self.line_end}"
        elif self.line_start:
            loc += f":{self.line_start}"
        if self.paragraph:
            loc += f" ({self.paragraph})"
        return loc


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str  # "dependency" | "business_rule" | "risk" | "strategy" | "data_item" | "coverage"
    detail: str
    source_refs: tuple[SourceRef, ...] = ()


class Assumption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assumption_id: str
    statement: str
    reason: str
    source_refs: tuple[SourceRef, ...] = ()


class UnsupportedBehavior(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    construct_name: str
    explanation: str
    impact: str
    source_refs: tuple[SourceRef, ...] = ()
    diagnostic_code: str | None = None


class ExternalInterface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    interface_id: str
    kind: str  # "CALL" | "FILE_IO" | "CICS" | "DB2" | "VSAM" | "JCL"
    target: str
    modeled: bool
    source_refs: tuple[SourceRef, ...] = ()
    note: str = ""


class DataModelElement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    java_concept: str  # "DTO" | "ValueObject" | "field"
    java_type: str
    cobol_picture: str | None = None
    initial_value: str | None = None
    source_refs: tuple[SourceRef, ...] = ()


class ArchitectureComponent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    component_id: str
    name: str
    type: ComponentType
    responsibility: str
    source_refs: tuple[SourceRef, ...] = ()
    business_rule_ids: tuple[str, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    external_interface_ids: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class StrategyRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation_id: str
    strategy: str
    is_primary: bool
    rationale: str
    evidence: tuple[str, ...] = ()
    referenced_risk_ids: tuple[str, ...] = ()


class JavaArchitecture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    architecture_id: str
    version: str = ARCHITECTURE_VERSION
    analysis_version: str
    source_id: str

    primary_strategy: StrategyRef | None = None
    alternative_strategies: tuple[StrategyRef, ...] = ()

    components: tuple[ArchitectureComponent, ...] = ()
    data_model: tuple[DataModelElement, ...] = ()
    external_interfaces: tuple[ExternalInterface, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    unsupported_behaviors: tuple[UnsupportedBehavior, ...] = ()

    #: component_id -> COBOL source refs (flattened, for #126 traceability)
    source_mappings: dict[str, tuple[SourceRef, ...]] = Field(default_factory=dict)

    semantic_equivalence_verified: bool = False

    def by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.components:
            out[c.type.value] = out.get(c.type.value, 0) + 1
        return dict(sorted(out.items()))

    def content_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json", exclude={"architecture_id"}),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["content_hash"] = self.content_hash()
        d["by_type"] = self.by_type()
        return d
