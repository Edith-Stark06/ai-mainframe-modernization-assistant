"""Exceptions for the #121 fine-tuning pipeline.

All are subclasses of :class:`TrainingPipelineError` so a caller can
catch the whole family. Nothing here is swallowed silently by the
pipeline — a failure always surfaces as one of these.
"""

from __future__ import annotations


class TrainingPipelineError(Exception):
    """Base class for every #121 pipeline error."""


class TrainingConfigError(TrainingPipelineError):
    """A training configuration is missing required fields or is malformed."""


class DatasetResolutionError(TrainingPipelineError):
    """The requested training dataset / split could not be resolved.

    Raised when the dataset version cannot be found, the on-disk hash does
    not match the recorded one, the requested split is unavailable, or an
    example fails Phase 6 schema validation. The pipeline never silently
    falls back to a different dataset.
    """


class BenchmarkLeakageError(TrainingPipelineError):
    """Training data overlaps the frozen evaluation benchmark.

    Raised when a training example shares a ``source_id`` or an identical
    source program with a #119 benchmark example, or when a
    benchmark-safe split is too small to train on. The fine-tuning
    pipeline must never train on anything the model is later evaluated
    against.
    """


class TrainingBackendUnavailableError(TrainingPipelineError):
    """No real fine-tuning backend is available in this environment.

    The reproducible pipeline, configuration, manifest and evaluation
    still work; only the weight-update step cannot run. This is reported
    honestly — a fake fine-tuned model is never produced.
    """


class CheckpointError(TrainingPipelineError):
    """A checkpoint is missing, incomplete, or fails its hash check."""


class ComparisonError(TrainingPipelineError):
    """Two evaluation reports cannot be compared.

    Raised when the baseline and candidate were evaluated against
    different benchmark versions / content hashes / metric versions.
    """


__all__ = [
    "TrainingPipelineError",
    "TrainingConfigError",
    "DatasetResolutionError",
    "BenchmarkLeakageError",
    "TrainingBackendUnavailableError",
    "CheckpointError",
    "ComparisonError",
]
