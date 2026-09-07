"""
#121 — reproducible, evaluation-driven fine-tuning pipeline.

The pipeline answers one question: *does fine-tuning the Phase 6 curated
dataset produce a measurable improvement over the #120 baseline?* — and
records enough to reproduce that answer. It never assumes fine-tuning
helps, never trains on the frozen #119 benchmark, and never promotes a
model without benchmark evidence.

Entry points:

* :func:`app.training.pipeline.run_training` — resolve data, train,
  write the manifest.
* :func:`app.training.evaluation.evaluate_model` — score a model against
  the frozen benchmark with the Phase 6 metrics.
* :func:`app.training.comparison.compare_models` — baseline vs
  fine-tuned + the IMPROVED / NO_MEANINGFUL_IMPROVEMENT / REGRESSED /
  INCONCLUSIVE decision.
* :class:`app.training.registry.ModelRegistry` — lineage + status.
"""

from __future__ import annotations

from app.training.comparison import (
    IMPROVED,
    INCONCLUSIVE,
    NO_MEANINGFUL_IMPROVEMENT,
    REGRESSED,
    ComparisonResult,
    DecisionPolicy,
    compare_models,
)
from app.training.config import TrainingConfig, load_config
from app.training.dataset import ResolvedTrainingData, resolve_training_data
from app.training.errors import (
    BenchmarkLeakageError,
    DatasetResolutionError,
    TrainingBackendUnavailableError,
    TrainingConfigError,
    TrainingPipelineError,
)
from app.training.evaluation import EvaluationArtifact, evaluate_model
from app.training.pipeline import TrainingRun, run_training
from app.training.registry import ModelRecord, ModelRegistry

__all__ = [
    "TrainingConfig",
    "load_config",
    "ResolvedTrainingData",
    "resolve_training_data",
    "TrainingRun",
    "run_training",
    "EvaluationArtifact",
    "evaluate_model",
    "ComparisonResult",
    "DecisionPolicy",
    "compare_models",
    "IMPROVED",
    "NO_MEANINGFUL_IMPROVEMENT",
    "REGRESSED",
    "INCONCLUSIVE",
    "ModelRegistry",
    "ModelRecord",
    "TrainingPipelineError",
    "TrainingConfigError",
    "DatasetResolutionError",
    "BenchmarkLeakageError",
    "TrainingBackendUnavailableError",
]
