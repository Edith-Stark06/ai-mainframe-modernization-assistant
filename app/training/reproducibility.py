"""
Reproducibility records for a fine-tuning run (#121 Parts 5, 7, 8).

We are careful to distinguish:

* a **reproducible run specification** — seed, dataset hash, config hash,
  base model, tokenizer, preprocessing version, command, environment —
  which this module captures deterministically; from
* **bit-for-bit identical weights**, which no CPU/GPU training framework
  can guarantee across machines and which we never claim.

Nothing here imports a training framework; it only records facts.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.training.config import TrainingConfig
from app.training.dataset import ResolvedTrainingData
from app.training.version import TRAINING_PIPELINE_VERSION

__all__ = [
    "capture_environment",
    "RunSpec",
    "CheckpointMeta",
    "TrainingManifest",
    "utc_now_iso",
]

_TRACKED_PACKAGES = (
    "torch",
    "transformers",
    "peft",
    "datasets",
    "accelerate",
    "trl",
    "pydantic",
    "numpy",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version(name)
        except PackageNotFoundError:
            return None
    except Exception:  # pragma: no cover - importlib always present on 3.12
        return None


def capture_environment() -> dict[str, Any]:
    """Record the software environment (no secrets, no network)."""
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "training_pipeline_version": TRAINING_PIPELINE_VERSION,
        "packages": {name: _package_version(name) for name in _TRACKED_PACKAGES},
    }


@dataclass(frozen=True)
class RunSpec:
    """Everything needed to *re-issue* a training run.

    Two runs with the same :meth:`spec_hash` were asked to do the same
    thing; whether they produce identical floating-point weights depends
    on the backend and hardware.
    """

    config_hash: str
    config_version: str
    base_model: str
    tokenizer: str
    method: str
    dataset_version: str
    dataset_manifest_hash: str
    training_split: str
    preprocessing_version: str
    random_seed: int
    training_example_count: int
    training_source_count: int
    benchmark_version: str
    benchmark_content_hash: str

    @classmethod
    def build(cls, config: TrainingConfig, data: ResolvedTrainingData) -> "RunSpec":
        return cls(
            config_hash=config.config_hash,
            config_version=config.training_config_version,
            base_model=config.base_model,
            tokenizer=config.tokenizer,
            method=config.method,
            dataset_version=data.dataset_version,
            dataset_manifest_hash=data.dataset_manifest_hash,
            training_split=data.split,
            preprocessing_version=data.preprocessing_version,
            random_seed=config.random_seed,
            training_example_count=data.example_count,
            training_source_count=data.source_count,
            benchmark_version=data.benchmark_version,
            benchmark_content_hash=data.benchmark_content_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_hash": self.config_hash,
            "config_version": self.config_version,
            "base_model": self.base_model,
            "tokenizer": self.tokenizer,
            "method": self.method,
            "dataset_version": self.dataset_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "training_split": self.training_split,
            "preprocessing_version": self.preprocessing_version,
            "random_seed": self.random_seed,
            "training_example_count": self.training_example_count,
            "training_source_count": self.training_source_count,
            "benchmark_version": self.benchmark_version,
            "benchmark_content_hash": self.benchmark_content_hash,
        }

    @property
    def spec_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CheckpointMeta:
    """Identity of a produced checkpoint (#121 Part 7)."""

    model_version: str
    base_model: str
    training_config_version: str
    config_hash: str
    dataset_version: str
    dataset_manifest_hash: str
    training_run_id: str
    backend: str
    is_real_model: bool
    checkpoint_path: str | None = None
    checkpoint_hash: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "base_model": self.base_model,
            "training_config_version": self.training_config_version,
            "config_hash": self.config_hash,
            "dataset_version": self.dataset_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "training_run_id": self.training_run_id,
            "backend": self.backend,
            "is_real_model": self.is_real_model,
            "checkpoint_path": self.checkpoint_path,
            "checkpoint_hash": self.checkpoint_hash,
            "notes": self.notes,
        }


@dataclass
class TrainingManifest:
    """The complete record of one training run (#121 Part 8)."""

    run_id: str
    model_version: str
    created_at: str
    run_spec: RunSpec
    checkpoint: CheckpointMeta
    environment: dict[str, Any]
    parameters: dict[str, Any]
    training_metadata: dict[str, Any]
    dataset_metadata: dict[str, Any]
    reproducibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_version": self.model_version,
            "created_at": self.created_at,
            "training_pipeline_version": TRAINING_PIPELINE_VERSION,
            "run_spec": self.run_spec.to_dict(),
            "run_spec_hash": self.run_spec.spec_hash,
            "checkpoint": self.checkpoint.to_dict(),
            "environment": self.environment,
            "parameters": self.parameters,
            "training_metadata": self.training_metadata,
            "dataset_metadata": self.dataset_metadata,
            "reproducibility": self.reproducibility,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
        return p
