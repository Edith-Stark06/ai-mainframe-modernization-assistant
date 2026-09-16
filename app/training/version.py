"""
Phase 7 / #121 fine-tuning pipeline versioning constants.

Every training run records the exact versions that produced it so a
later "did fine-tuning help?" comparison is unambiguous and another
developer can reconstruct the run.

* ``TRAINING_PIPELINE_VERSION`` — the orchestration code in
  :mod:`app.training`; bump whenever the run specification, manifest
  schema or decision logic changes.
* ``PREPROCESSING_VERSION``     — how :mod:`app.training.dataset` turns
  a :class:`~app.dataset.schema.DatasetExample` into a training record
  (prompt/response rendering, filtering, ordering). Bump whenever that
  transformation changes even if nothing else does.
* ``DECISION_POLICY_VERSION``   — the thresholds / rules in
  :mod:`app.training.comparison` that map a baseline-vs-candidate
  comparison onto one of IMPROVED / NO_MEANINGFUL_IMPROVEMENT /
  REGRESSED / INCONCLUSIVE.
* ``REGISTRY_SCHEMA_VERSION``   — the on-disk model-registry format.

These are deliberately separate from the Phase 6 constants in
:mod:`app.dataset.version` — #121 never mutates a Phase 6 artifact.
"""

from __future__ import annotations

TRAINING_PIPELINE_VERSION: str = "phase7-train-v1"
PREPROCESSING_VERSION: str = "p7-preproc-v1"
DECISION_POLICY_VERSION: str = "p7-decision-v1"
REGISTRY_SCHEMA_VERSION: str = "p7-registry-v1"

__all__ = [
    "TRAINING_PIPELINE_VERSION",
    "PREPROCESSING_VERSION",
    "DECISION_POLICY_VERSION",
    "REGISTRY_SCHEMA_VERSION",
]
