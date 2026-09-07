"""
Lightweight model registry (#121 Part 13).

A JSON file (default ``models/registry.json``) recording every model the
pipeline has produced, its lineage, and its benchmark verdict.

Status lifecycle::

    TRAINED  --evaluate-->  VALIDATED / CANDIDATE / REJECTED  --adopt-->  ADOPTED

* ``TRAINED``    — a checkpoint exists; not yet evaluated.
* ``VALIDATED``  — evaluated; decision was NO_MEANINGFUL_IMPROVEMENT or
  INCONCLUSIVE. Keep the baseline.
* ``CANDIDATE``  — evaluated; decision was IMPROVED. Eligible for a
  human adoption decision.
* ``REJECTED``   — evaluated; decision was REGRESSED.
* ``ADOPTED``    — a human explicitly promoted a CANDIDATE. Never set
  automatically, never as a side effect of training or evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.dataset.corpus import REPO_ROOT
from app.training.comparison import (
    IMPROVED,
    INCONCLUSIVE,
    NO_MEANINGFUL_IMPROVEMENT,
    REGRESSED,
    ComparisonResult,
)
from app.training.errors import TrainingPipelineError
from app.training.pipeline import TrainingRun
from app.training.reproducibility import utc_now_iso
from app.training.version import REGISTRY_SCHEMA_VERSION

__all__ = [
    "ModelRecord",
    "ModelRegistry",
    "DEFAULT_REGISTRY_PATH",
    "STATUS_TRAINED",
    "STATUS_VALIDATED",
    "STATUS_CANDIDATE",
    "STATUS_REJECTED",
    "STATUS_ADOPTED",
]

DEFAULT_REGISTRY_PATH = REPO_ROOT / "models" / "registry.json"

STATUS_TRAINED = "TRAINED"
STATUS_VALIDATED = "VALIDATED"
STATUS_CANDIDATE = "CANDIDATE"
STATUS_REJECTED = "REJECTED"
STATUS_ADOPTED = "ADOPTED"

_DECISION_TO_STATUS = {
    IMPROVED: STATUS_CANDIDATE,
    NO_MEANINGFUL_IMPROVEMENT: STATUS_VALIDATED,
    INCONCLUSIVE: STATUS_VALIDATED,
    REGRESSED: STATUS_REJECTED,
}


class ModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_version: str
    base_model: str
    training_run_id: str
    training_config_version: str
    config_hash: str
    dataset_version: str
    dataset_manifest_hash: str
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    is_real_model: bool = False
    status: str = STATUS_TRAINED
    decision: str | None = None
    benchmark_evaluation: dict[str, Any] | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    notes: str = ""


class ModelRegistry:
    def __init__(self, path: str | Path = DEFAULT_REGISTRY_PATH) -> None:
        self.path = Path(path)
        self.records: list[ModelRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.records = [ModelRecord.model_validate(r) for r in data.get("models", [])]

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "models": [
                r.model_dump(mode="json")
                for r in sorted(self.records, key=lambda x: x.model_version)
            ],
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return self.path

    def get(self, model_version: str) -> ModelRecord | None:
        return next((r for r in self.records if r.model_version == model_version), None)

    def register_training(self, run: TrainingRun) -> ModelRecord:
        if self.get(run.model_version):
            raise TrainingPipelineError(
                f"model_version {run.model_version!r} already in registry"
            )
        rec = ModelRecord(
            model_version=run.model_version,
            base_model=run.config.base_model,
            training_run_id=run.run_id,
            training_config_version=run.config.training_config_version,
            config_hash=run.config.config_hash,
            dataset_version=run.data.dataset_version,
            dataset_manifest_hash=run.data.dataset_manifest_hash,
            checkpoint=run.manifest.checkpoint.to_dict(),
            is_real_model=run.is_real_model,
            status=STATUS_TRAINED,
            notes=run.manifest.checkpoint.notes,
        )
        self.records.append(rec)
        return rec

    def attach_evaluation(
        self, model_version: str, comparison: ComparisonResult
    ) -> ModelRecord:
        rec = self.get(model_version)
        if rec is None:
            raise TrainingPipelineError(f"unknown model_version {model_version!r}")
        overall = {r.name: r.to_dict() for r in comparison.overall}
        rec.benchmark_evaluation = {
            "benchmark_version": comparison.benchmark_version,
            "benchmark_content_hash": comparison.benchmark_content_hash,
            "evaluation_mode": comparison.evaluation_mode,
            "decision_policy_version": comparison.decision_policy_version,
            "baseline_model_version": comparison.baseline_model_version,
            "overall": overall,
            "rationale": comparison.rationale,
        }
        rec.decision = comparison.decision
        rec.status = _DECISION_TO_STATUS.get(comparison.decision, STATUS_VALIDATED)
        rec.updated_at = utc_now_iso()
        return rec

    def adopt(self, model_version: str, approved_by: str) -> ModelRecord:
        """Explicit human promotion. Requires an IMPROVED CANDIDATE."""
        rec = self.get(model_version)
        if rec is None:
            raise TrainingPipelineError(f"unknown model_version {model_version!r}")
        if not approved_by.strip():
            raise TrainingPipelineError("adopt() requires a non-empty approved_by")
        if rec.status != STATUS_CANDIDATE or rec.decision != IMPROVED:
            raise TrainingPipelineError(
                f"cannot adopt {model_version!r}: status={rec.status} "
                f"decision={rec.decision}. Only an IMPROVED CANDIDATE with "
                f"benchmark evidence may be adopted."
            )
        if not rec.is_real_model:
            raise TrainingPipelineError(
                f"cannot adopt {model_version!r}: it was produced by a "
                f"non-training backend and is not a real model."
            )
        rec.status = STATUS_ADOPTED
        rec.notes = (rec.notes + f" | adopted by {approved_by} {utc_now_iso()}").strip(
            " |"
        )
        rec.updated_at = utc_now_iso()
        return rec
