"""
Training-run orchestration (#121 Parts 5-8).

``run_training(config)`` ties the pieces together:

    resolve + benchmark-isolate data  ->  RunSpec  ->  backend.train
        ->  CheckpointMeta  ->  TrainingManifest (written to disk)

It never mutates a Phase 6 artifact and never continues past a data or
backend failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.dataset.version import BENCHMARK_VERSION
from app.training.backend import build_backend
from app.training.config import TrainingConfig
from app.training.dataset import (
    DEFAULT_MIN_TRAINING_SOURCES,
    ResolvedTrainingData,
    resolve_training_data,
)
from app.training.reproducibility import (
    CheckpointMeta,
    RunSpec,
    TrainingManifest,
    capture_environment,
    utc_now_iso,
)
from app.training.version import TRAINING_PIPELINE_VERSION

__all__ = ["TrainingRun", "run_training", "model_version_for"]


def _slug(text: str) -> str:
    keep = [c if c.isalnum() else "-" for c in text.lower()]
    out = "".join(keep).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "model"


def model_version_for(config: TrainingConfig, spec: RunSpec) -> str:
    """A never-ambiguous checkpoint identity (never bare 'latest'/'model')."""
    return (
        f"{_slug(config.base_model.split('/')[-1])}"
        f"-ft-{_slug(config.training_config_version)}"
        f"-{spec.spec_hash[:8]}"
    )


@dataclass(frozen=True)
class TrainingRun:
    run_id: str
    model_version: str
    config: TrainingConfig
    data: ResolvedTrainingData
    run_spec: RunSpec
    manifest: TrainingManifest
    run_dir: Path
    checkpoint_dir: Path
    is_real_model: bool

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_version": self.model_version,
            "run_dir": str(self.run_dir),
            "checkpoint_dir": str(self.checkpoint_dir),
            "is_real_model": self.is_real_model,
            "run_spec_hash": self.run_spec.spec_hash,
            "training_example_count": self.data.example_count,
            "training_source_count": self.data.source_count,
            "excluded_benchmark_sources": list(self.data.excluded_benchmark_sources),
        }


def run_training(
    config: TrainingConfig,
    *,
    backend: str = "auto",
    output_root: str | Path,
    benchmark_version: str = BENCHMARK_VERSION,
    run_id: str | None = None,
    created_at: str | None = None,
    min_training_sources: int = DEFAULT_MIN_TRAINING_SOURCES,
    max_examples: int | None = None,
) -> TrainingRun:
    created_at = created_at or utc_now_iso()

    data = resolve_training_data(
        config.dataset_version,
        config.training_split,
        benchmark_version=benchmark_version,
        expected_manifest_hash=config.dataset_manifest_hash,
        min_training_sources=min_training_sources,
        max_examples=max_examples or config.max_training_examples,
    )

    spec = RunSpec.build(config, data)
    model_version = model_version_for(config, spec)
    run_id = run_id or f"run-{spec.spec_hash[:12]}"

    run_dir = Path(output_root) / run_id
    checkpoint_dir = run_dir / "checkpoint"
    run_dir.mkdir(parents=True, exist_ok=True)

    impl = build_backend(backend)

    started = utc_now_iso()
    outcome = impl.train(config, data, checkpoint_dir, run_id)
    finished = utc_now_iso()

    checkpoint = CheckpointMeta(
        model_version=model_version,
        base_model=config.base_model,
        training_config_version=config.training_config_version,
        config_hash=config.config_hash,
        dataset_version=data.dataset_version,
        dataset_manifest_hash=data.dataset_manifest_hash,
        training_run_id=run_id,
        backend=outcome.backend,
        is_real_model=outcome.is_real_model,
        checkpoint_path=str(outcome.checkpoint_dir),
        checkpoint_hash=outcome.checkpoint_hash,
        notes=outcome.notes,
    )

    manifest = TrainingManifest(
        run_id=run_id,
        model_version=model_version,
        created_at=created_at,
        run_spec=spec,
        checkpoint=checkpoint,
        environment=capture_environment(),
        parameters=config.canonical_dict(),
        training_metadata={
            "backend": outcome.backend,
            "is_real_model": outcome.is_real_model,
            "started_at": started,
            "finished_at": finished,
            "metrics": outcome.metrics,
        },
        dataset_metadata=data.metadata(),
        reproducibility={
            "training_pipeline_version": TRAINING_PIPELINE_VERSION,
            "reproducible": [
                "run specification (seed, dataset hash, config hash, base "
                "model, tokenizer, preprocessing version)",
                "training-data selection and ordering",
                "benchmark isolation (excluded sources listed)",
            ],
            "not_guaranteed": [
                "bit-for-bit identical model weights across machines / "
                "framework versions / hardware",
            ],
            "command": (
                f"python -m scripts.training.train_model --config <config> "
                f"--backend {backend}"
            ),
        },
    )
    manifest.write(run_dir / "training_manifest.json")
    config.to_yaml()  # validated already; persist a copy next to the run
    (run_dir / "resolved_config.yaml").write_text(config.to_yaml(), encoding="utf-8")
    _write_records(run_dir / "training_records.jsonl", data)

    return TrainingRun(
        run_id=run_id,
        model_version=model_version,
        config=config,
        data=data,
        run_spec=spec,
        manifest=manifest,
        run_dir=run_dir,
        checkpoint_dir=checkpoint_dir,
        is_real_model=outcome.is_real_model,
    )


def _write_records(path: Path, data: ResolvedTrainingData) -> None:
    import json

    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in data.records:
            fh.write(json.dumps(rec.to_dict(), sort_keys=True, separators=(",", ":")))
            fh.write("\n")
