"""#121 Part 15 — reproducibility & training manifest."""

from __future__ import annotations

from app.training.pipeline import run_training
from app.training.reproducibility import RunSpec, capture_environment
from app.training.dataset import resolve_training_data

BV = "benchmark-v1"


def test_run_spec_is_stable_for_same_config_and_data(config_v1) -> None:
    data = resolve_training_data(
        "phase6-v1", "train", benchmark_version=BV, min_training_sources=1
    )
    a = RunSpec.build(config_v1, data)
    b = RunSpec.build(config_v1, data)
    assert a.spec_hash == b.spec_hash
    assert a.random_seed == config_v1.random_seed
    assert a.dataset_manifest_hash == data.dataset_manifest_hash
    assert a.config_hash == config_v1.config_hash


def test_capture_environment_has_no_secrets_and_lists_packages() -> None:
    env = capture_environment()
    assert "python_version" in env
    assert "torch" in env["packages"]
    blob = str(env).lower()
    for banned in ("key", "token", "secret", "password", "authorization"):
        assert banned not in blob


def test_manifest_is_complete_and_json_safe(mock_run) -> None:
    import json

    d = mock_run.manifest.to_dict()
    for key in (
        "run_id",
        "model_version",
        "run_spec",
        "run_spec_hash",
        "checkpoint",
        "environment",
        "parameters",
        "training_metadata",
        "dataset_metadata",
        "reproducibility",
    ):
        assert key in d
    assert d["run_spec"]["random_seed"] == mock_run.config.random_seed
    assert d["dataset_metadata"]["dataset_manifest_hash"]
    assert d["reproducibility"]["not_guaranteed"]  # honest about weight determinism
    json.dumps(d)  # must be serialisable


def test_two_mock_runs_same_inputs_same_checkpoint_hash(tmp_path, config_v1) -> None:
    kw = dict(
        backend="mock",
        output_root=tmp_path,
        min_training_sources=1,
        created_at="2026-01-01T00:00:00Z",
    )
    r1 = run_training(config_v1, run_id="x1", **kw)
    r2 = run_training(config_v1, run_id="x2", **kw)
    assert r1.run_spec.spec_hash == r2.run_spec.spec_hash
    assert r1.model_version == r2.model_version
    assert (
        r1.manifest.checkpoint.checkpoint_hash == r2.manifest.checkpoint.checkpoint_hash
    )


def test_manifest_written_to_disk(mock_run) -> None:
    p = mock_run.run_dir / "training_manifest.json"
    assert p.exists()
    assert (mock_run.run_dir / "resolved_config.yaml").exists()
    assert (mock_run.run_dir / "training_records.jsonl").exists()
