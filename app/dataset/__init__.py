"""
Phase 6 — Training Dataset (#118).

Deterministic, versioned, provenance-tracked dataset generation from the
Phase 1–5 analysis outputs, plus schema/security/duplicate/leakage
validation and reproducible train/validation/test splitting.

No model training happens here or anywhere in Phase 6.
"""

from app.dataset.schema import (
    DatasetExample,
    Difficulty,
    GroundTruthStatus,
    Provenance,
    TaskType,
)
from app.dataset.version import (
    ANALYSIS_VERSION,
    BENCHMARK_VERSION,
    DATASET_VERSION,
    GENERATOR_VERSION,
    PROMPT_VERSION,
)

__all__ = [
    "DatasetExample",
    "Difficulty",
    "GroundTruthStatus",
    "Provenance",
    "TaskType",
    "DATASET_VERSION",
    "BENCHMARK_VERSION",
    "PROMPT_VERSION",
    "GENERATOR_VERSION",
    "ANALYSIS_VERSION",
]
