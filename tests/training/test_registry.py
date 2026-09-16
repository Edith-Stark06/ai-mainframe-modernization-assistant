"""#121 Part 13 — model registry. Adoption is never automatic."""

from __future__ import annotations

import pytest

from app.training.comparison import compare_models
from app.training.errors import TrainingPipelineError
from app.training.registry import (
    STATUS_ADOPTED,
    STATUS_CANDIDATE,
    STATUS_REJECTED,
    STATUS_TRAINED,
    STATUS_VALIDATED,
    ModelRegistry,
)
from tests.training.conftest import make_artifact


@pytest.fixture
def registry(tmp_path):
    return ModelRegistry(tmp_path / "registry.json")


def _cmp(decision_kw_baseline, decision_kw_candidate):
    return compare_models(
        make_artifact("baseline", **decision_kw_baseline),
        make_artifact("candidate", **decision_kw_candidate),
    )


def test_register_training_sets_status_trained(registry, mock_run) -> None:
    rec = registry.register_training(mock_run)
    assert rec.status == STATUS_TRAINED
    assert rec.decision is None
    assert rec.is_real_model is False
    assert rec.dataset_manifest_hash == mock_run.data.dataset_manifest_hash
    registry.save()
    assert registry.path.exists()


def test_double_register_is_rejected(registry, mock_run) -> None:
    registry.register_training(mock_run)
    with pytest.raises(TrainingPipelineError, match="already in registry"):
        registry.register_training(mock_run)


def test_improved_becomes_candidate_not_adopted(registry, mock_run) -> None:
    registry.register_training(mock_run)
    cmp = _cmp(dict(pass_rate=0.40), dict(pass_rate=0.65))
    assert cmp.decision == "IMPROVED"
    rec = registry.attach_evaluation(mock_run.model_version, cmp)
    assert rec.status == STATUS_CANDIDATE
    assert rec.status != STATUS_ADOPTED


def test_no_meaningful_improvement_becomes_validated(registry, mock_run) -> None:
    registry.register_training(mock_run)
    cmp = _cmp(dict(pass_rate=0.50), dict(pass_rate=0.52))
    rec = registry.attach_evaluation(mock_run.model_version, cmp)
    assert rec.status == STATUS_VALIDATED


def test_regressed_becomes_rejected(registry, mock_run) -> None:
    registry.register_training(mock_run)
    cmp = _cmp(dict(pass_rate=0.60), dict(pass_rate=0.45))
    rec = registry.attach_evaluation(mock_run.model_version, cmp)
    assert rec.status == STATUS_REJECTED


def test_adopt_requires_improved_candidate_and_real_model(registry, mock_run) -> None:
    registry.register_training(mock_run)
    cmp = _cmp(dict(pass_rate=0.40), dict(pass_rate=0.65))
    registry.attach_evaluation(mock_run.model_version, cmp)
    # it is an IMPROVED CANDIDATE, but a mock (not real) model -> cannot adopt
    with pytest.raises(TrainingPipelineError, match="not a real model"):
        registry.adopt(mock_run.model_version, approved_by="alice")


def test_adopt_rejects_non_candidate(registry, mock_run) -> None:
    registry.register_training(mock_run)
    with pytest.raises(TrainingPipelineError):
        registry.adopt(mock_run.model_version, approved_by="alice")


def test_adopt_requires_approver(registry, mock_run) -> None:
    registry.register_training(mock_run)
    cmp = _cmp(dict(pass_rate=0.40), dict(pass_rate=0.65))
    registry.attach_evaluation(mock_run.model_version, cmp)
    with pytest.raises(TrainingPipelineError, match="approved_by"):
        registry.adopt(mock_run.model_version, approved_by="  ")


def test_registry_roundtrips_through_disk(registry, mock_run) -> None:
    registry.register_training(mock_run)
    registry.save()
    reloaded = ModelRegistry(registry.path)
    assert reloaded.get(mock_run.model_version) is not None
