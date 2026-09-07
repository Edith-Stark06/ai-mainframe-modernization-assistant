"""#121 Part 15 — checkpoint identity + backend availability."""

from __future__ import annotations

import json

import pytest

from app.ai.providers.models import LLMRequest
from app.training.backend import (
    DeterministicMockBackend,
    MockCheckpointProvider,
    build_backend,
    build_checkpoint_provider,
)
from app.training.errors import CheckpointError, TrainingBackendUnavailableError


def test_model_version_is_never_ambiguous(mock_run) -> None:
    mv = mock_run.model_version
    assert mv not in ("latest", "model", "finetuned")
    assert mock_run.config.training_config_version in mv
    assert mock_run.run_spec.spec_hash[:8] in mv


def test_checkpoint_meta_records_lineage(mock_run) -> None:
    cp = mock_run.manifest.checkpoint
    assert cp.is_real_model is False
    assert cp.config_hash == mock_run.config.config_hash
    assert cp.dataset_manifest_hash == mock_run.data.dataset_manifest_hash
    assert cp.checkpoint_hash
    assert "NOT A REAL FINE-TUNED MODEL" in cp.notes


def test_mock_checkpoint_provider_rejects_a_non_mock_dir(tmp_path) -> None:
    with pytest.raises(CheckpointError):
        MockCheckpointProvider(tmp_path)

    (tmp_path / "mock_checkpoint.json").write_text(
        json.dumps({"backend": "something-else"}), encoding="utf-8"
    )
    with pytest.raises(CheckpointError):
        MockCheckpointProvider(tmp_path)


def test_mock_checkpoint_provider_is_deterministic(mock_run) -> None:
    p = MockCheckpointProvider(mock_run.checkpoint_dir)
    req = LLMRequest(prompt="## Task\ncobol_explanation\n", temperature=0.0)
    assert p.generate(req).text == p.generate(req).text
    assert p.model.startswith("mock-checkpoint:")


def test_build_backend_auto_and_real_raise_when_unavailable() -> None:
    # environment has cpu torch + transformers but not peft/datasets/accelerate
    with pytest.raises(TrainingBackendUnavailableError):
        build_backend("auto")
    with pytest.raises(TrainingBackendUnavailableError):
        build_backend("transformers-lora")


def test_build_backend_unknown_name_raises() -> None:
    with pytest.raises(
        TrainingBackendUnavailableError, match="unknown training backend"
    ):
        build_backend("wishful-thinking")


def test_build_backend_mock_is_the_only_no_op_path() -> None:
    b = build_backend("mock")
    assert isinstance(b, DeterministicMockBackend)
    assert b.is_real is False


def test_build_checkpoint_provider_real_is_unavailable(mock_run) -> None:
    with pytest.raises(TrainingBackendUnavailableError):
        build_checkpoint_provider(mock_run.checkpoint_dir, real=True)
