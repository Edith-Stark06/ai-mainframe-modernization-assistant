"""
Phase 6 dataset example schema (#118).

A formal, versioned, machine-checkable schema for one training-dataset
example. Pydantic v2 (the repository's model convention) — not a second
JSON-Schema stack.

Design rules enforced here:

* Every example carries a stable ``example_id`` and a ``dataset_version``.
* ``analysis`` fields are **explicitly optional**: ``None`` means "this
  stage was not run / not applicable for this example", never an empty
  ``{}`` that would imply information was analysed when it was not.
* Provenance is mandatory and cannot be faked: ``ground_truth_status``
  and ``provenance`` are separate axes and are cross-validated.
* ``source`` is never empty; ``expected_output`` is never empty for the
  task types that require an answer.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "TaskType",
    "Difficulty",
    "Provenance",
    "GroundTruthStatus",
    "SourceLocation",
    "ExampleInput",
    "ExampleAnalysis",
    "ExampleMetadata",
    "DatasetExample",
    "REQUIRES_EXPECTED_OUTPUT",
    "derive_example_id",
]


class TaskType(str, Enum):
    """The eight Phase 6 task types."""

    COBOL_EXPLANATION = "cobol_explanation"
    BUSINESS_RULE_EXTRACTION = "business_rule_extraction"
    MODERNIZATION_RECOMMENDATION = "modernization_recommendation"
    RISK_IDENTIFICATION = "risk_identification"
    COBOL_TO_STRUCTURED = "cobol_to_structured"
    COBOL_TO_JAVA = "cobol_to_java"
    MODERNIZATION_QA = "modernization_qa"
    SOURCE_GROUNDED_QA = "source_grounded_qa"


#: Task types that MUST carry a non-empty ``expected_output``.
REQUIRES_EXPECTED_OUTPUT: frozenset[TaskType] = frozenset(TaskType)


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    DIFFICULT = "difficult"
    ADVERSARIAL = "adversarial"


class Provenance(str, Enum):
    """Where the *example* came from."""

    PUBLIC_SOURCE = "public_source"
    SYNTHETIC = "synthetic"
    REPOSITORY_FIXTURE = "repository_fixture"
    MANUALLY_CURATED = "manually_curated"
    DETERMINISTIC_GENERATED = "deterministic_generated"
    REVIEWED_REFERENCE = "reviewed_reference"


class GroundTruthStatus(str, Enum):
    """How trustworthy the ``expected_output`` is as a label."""

    #: Produced verbatim by the deterministic Phase 1–5 analyzers.
    DETERMINISTIC = "deterministic"
    #: A human reviewed and confirmed the answer.
    REVIEWED = "reviewed"
    #: Illustrative / non-gold — must NOT be treated as ground truth.
    REFERENCE = "reference"
    #: Behavioural / compilation evidence recorded (see metadata.notes).
    EXECUTABLE_VERIFIED = "executable_verified"


class SourceLocation(BaseModel):
    """A pointer into the example's source. Reuses the parser Position shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    line: int = Field(..., ge=1)
    column: int = Field(default=1, ge=1)
    offset: int = Field(default=0, ge=0)
    filename: str = Field(default="")
    snippet: str | None = Field(
        default=None,
        description="Verbatim source text at this location, if recorded.",
    )


class ExampleInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(..., min_length=1, description="The COBOL source.")
    source_id: str = Field(..., min_length=1)
    #: Free-form extra input the task needs (e.g. a QA question).
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source")
    @classmethod
    def _source_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source cannot be blank")
        return v


class ExampleAnalysis(BaseModel):
    """
    The deterministic Phase 1–5 analysis attached to the example.

    Every field is ``None`` unless that stage was actually run and
    produced output for this example. ``None`` != ``{}`` != ``[]``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ast: dict[str, Any] | None = None
    ir: dict[str, Any] | None = None
    cfg: dict[str, Any] | None = None
    dependencies: list[dict[str, Any]] | None = None
    business_rules: list[dict[str, Any]] | None = None
    risks: list[dict[str, Any]] | None = None
    strategy: dict[str, Any] | None = None
    coverage: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None


class ExampleMetadata(BaseModel):
    """
    Two explicit, non-overlapping provenance axes:

    * ``source_provenance`` — where the COBOL *source* came from
      (``repository_fixture`` / ``synthetic`` / ``public_source`` / …).
    * ``provenance`` — how this labeled *example* (the source→answer
      pair) was created (``deterministic_generated`` / ``reviewed_reference``
      / ``manually_curated`` / …).

    They are never conflated: a synthetic source with a deterministically
    generated answer has ``source_provenance = synthetic`` and
    ``provenance = deterministic_generated``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(..., min_length=1)
    source_provenance: Provenance
    provenance: Provenance
    license: str = Field(..., min_length=1)
    generator_version: str = Field(..., min_length=1)
    analysis_version: str = Field(..., min_length=1)
    ground_truth_status: GroundTruthStatus
    source_sha256: str = Field(..., min_length=64, max_length=64)
    notes: str | None = None
    created_at: str | None = None

    @model_validator(mode="after")
    def _provenance_ground_truth_consistency(self) -> ExampleMetadata:
        gt = self.ground_truth_status
        prov = self.provenance
        # A DETERMINISTIC label must come from a deterministic/generated
        # or fixture pipeline, never from something merely "synthetic"
        # or "public" without a generator.
        if gt is GroundTruthStatus.DETERMINISTIC and prov not in (
            Provenance.DETERMINISTIC_GENERATED,
            Provenance.REPOSITORY_FIXTURE,
        ):
            raise ValueError(
                "ground_truth_status=deterministic requires provenance "
                "deterministic_generated or repository_fixture"
            )
        return self


class DatasetExample(BaseModel):
    """One line of a dataset JSONL file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    example_id: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    task_type: TaskType
    difficulty: Difficulty
    input: ExampleInput
    analysis: ExampleAnalysis = Field(default_factory=ExampleAnalysis)
    expected_output: dict[str, Any] = Field(default_factory=dict)
    source_locations: list[SourceLocation] = Field(default_factory=list)
    metadata: ExampleMetadata

    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _expected_output_present_when_required(self) -> DatasetExample:
        if self.task_type in REQUIRES_EXPECTED_OUTPUT and not self.expected_output:
            raise ValueError(
                f"expected_output is required and non-empty for task "
                f"{self.task_type.value}"
            )
        return self

    @model_validator(mode="after")
    def _source_locations_resolve(self) -> DatasetExample:
        src = self.input.source
        lines = src.splitlines()
        for loc in self.source_locations:
            if loc.line > max(1, len(lines)):
                raise ValueError(
                    f"source_location line {loc.line} is past end of source "
                    f"({len(lines)} lines) in {self.example_id}"
                )
            if loc.snippet is not None and loc.snippet.strip():
                if loc.snippet.strip() not in src:
                    raise ValueError(
                        f"source_location snippet not found verbatim in source "
                        f"in {self.example_id}"
                    )
        return self

    @model_validator(mode="after")
    def _metadata_source_matches_input(self) -> DatasetExample:
        if self.metadata.source_id != self.input.source_id:
            raise ValueError("metadata.source_id != input.source_id")
        actual = hashlib.sha256(self.input.source.encode("utf-8")).hexdigest()
        if self.metadata.source_sha256 != actual:
            raise ValueError(
                f"metadata.source_sha256 does not match the actual source hash "
                f"in {self.example_id}"
            )
        return self

    def normalized_source(self) -> str:
        """Whitespace-normalised source for duplicate/leakage comparison."""
        return "\n".join(
            " ".join(line.split()) for line in self.input.source.splitlines()
        ).strip()

    def dedup_key(self) -> str:
        """Content identity ignoring example_id / version / metadata."""
        question = str(self.input.context.get("question", ""))
        payload = "␟".join(
            (
                self.task_type.value,
                self.normalized_source(),
                " ".join(question.split()).lower(),
                _canonical_json(self.expected_output),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------


def _canonical_json(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def derive_example_id(task_type: TaskType, source_id: str, variant: str = "") -> str:
    """
    Deterministic, collision-resistant example id.

    Stable for identical ``(task_type, source_id, variant)`` — never
    random, never dependent on Python object identity.
    """
    digest = hashlib.sha1(
        f"{task_type.value}␟{source_id}␟{variant}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{task_type.value}-{digest}"
