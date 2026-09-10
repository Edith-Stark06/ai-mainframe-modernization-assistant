"""
#129 — the language-independent behavioral test case model.

A :class:`BehavioralTestCase` is derived from deterministic Phase 1-5 /
Phase 9 analysis (business rules, source locations, unsupported-behavior
records) — never invented. ``executable`` + ``inconclusive_reason`` are
mandatory: a case touching unsupported COBOL, a missing external
dependency, or a generator stub must say so rather than pretend it can
be verified.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.java_modernization.architecture.models import SourceRef
from app.behavioral.version import EXTRACTION_VERSION

__all__ = [
    "InputSource",
    "InputValue",
    "ExpectedBranch",
    "ExpectedCalculation",
    "ExpectedOutput",
    "ExpectedError",
    "ExpectedStateChange",
    "BehavioralTestCase",
    "BehavioralSuite",
]


class InputSource(str, Enum):
    #: taken verbatim from a COBOL VALUE clause / literal in the analysis
    ANALYZED = "analyzed"
    #: a boundary value deterministically generated around a comparison
    BOUNDARY_GENERATED = "boundary_generated"


class InputValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: str
    source: InputSource
    #: the comparison this value partitions, e.g. "WS-AGE >= 18", if any
    partition_of: str | None = None


class ExpectedBranch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    branch_id: str  # stable id, e.g. "CHECK-ELIGIBILITY.IF.true"
    paragraph: str
    condition: str
    taken: bool


class ExpectedCalculation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    operator: str  # "+" | "-" | "*" | "/"
    operands: tuple[str, ...]
    raw: str
    source_ref: SourceRef | None = None


class ExpectedOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: str  # "display" | "field"
    expected_value: str
    observable: bool = True


class ExpectedError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    description: str
    observable: bool


class ExpectedStateChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    from_value: str | None
    to_value: str


class BehavioralTestCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    test_id: str
    name: str
    description: str

    inputs: tuple[InputValue, ...] = ()
    preconditions: tuple[InputValue, ...] = ()

    expected_branches: tuple[ExpectedBranch, ...] = ()
    expected_calculations: tuple[ExpectedCalculation, ...] = ()
    expected_outputs: tuple[ExpectedOutput, ...] = ()
    expected_errors: tuple[ExpectedError, ...] = ()
    expected_state_changes: tuple[ExpectedStateChange, ...] = ()

    source_refs: tuple[SourceRef, ...] = ()
    business_rule_ids: tuple[str, ...] = ()
    #: coarse evidence-strength label, not a calibrated probability
    confidence: str = "high"

    executable: bool = False
    inconclusive_reason: str | None = None

    extraction_version: str = EXTRACTION_VERSION
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class BehavioralSuite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    extraction_version: str = EXTRACTION_VERSION
    analysis_version: str
    tests: tuple[BehavioralTestCase, ...] = ()

    @property
    def executable_tests(self) -> tuple[BehavioralTestCase, ...]:
        return tuple(t for t in self.tests if t.executable)

    @property
    def non_executable_tests(self) -> tuple[BehavioralTestCase, ...]:
        return tuple(t for t in self.tests if not t.executable)

    def content_hash(self) -> str:
        payload = json.dumps(
            [t.to_dict() for t in self.tests], sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def by_id(self) -> dict[str, BehavioralTestCase]:
        return {t.test_id: t for t in self.tests}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "extraction_version": self.extraction_version,
            "analysis_version": self.analysis_version,
            "content_hash": self.content_hash(),
            "test_count": len(self.tests),
            "executable_count": len(self.executable_tests),
            "non_executable_count": len(self.non_executable_tests),
            "tests": [t.to_dict() for t in self.tests],
        }
