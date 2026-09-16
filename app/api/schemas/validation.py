"""
Validation Center API Schemas.

Defines the explicit, honest status vocabulary the whole Phase 12
Validation Center is built on: every stage reports exactly one of
PASS / FAIL / INCONCLUSIVE / NOT_AVAILABLE, computed deterministically
from real #125-#131 artifacts (see
``app.dataset.modernization_bundle.build_modernization_bundle`` and
``compute_validation_stages`` below). Nothing here re-runs analysis or
invents a verdict -- it only classifies what already ran.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["StageStatus", "StageResult", "ValidationResponse", "CORE_STAGES"]


class StageStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class StageResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stage: str
    status: StageStatus
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


#: Stages that gate ``overall_status``. Risks / Unsupported Syntax / COBOL
#: Tests / Self Repair are reported individually but are informational --
#: e.g. "1 risk identified" is not itself a pipeline failure, and Self
#: Repair being NOT_AVAILABLE (no AI provider configured) must not by
#: itself prevent an otherwise-clean analysis from reading PASS.
CORE_STAGES: frozenset[str] = frozenset(
    {"Parser", "Analysis", "Java Generation", "Compilation", "Behavioral Equivalence"}
)


class ValidationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str
    filename: str
    stages: list[StageResult]
    overall_status: StageStatus = Field(
        ...,
        description=(
            "Deterministic rollup over CORE_STAGES only: FAIL if any core "
            "stage FAILed, else INCONCLUSIVE if any core stage is "
            "INCONCLUSIVE or NOT_AVAILABLE, else PASS. Never upgraded past "
            "what the worst core stage actually established."
        ),
    )
