"""#121 Part 15 — training configuration."""

from __future__ import annotations

import pytest

from app.training.config import TrainingConfig, dump_config, load_config
from app.training.errors import TrainingConfigError

_MIN = dict(
    training_config_version="t1",
    base_model="org/model",
    tokenizer="org/model",
    dataset_version="phase6-v1",
    dataset_manifest_hash="0" * 64,
    learning_rate=1e-4,
    batch_size=4,
    max_sequence_length=1024,
)


def test_shipped_configs_load_and_validate() -> None:
    for path in (
        "configs/training/finetune-v1.yaml",
        "configs/training/finetune-v1-full.yaml",
    ):
        cfg = load_config(path)
        assert cfg.dataset_version == "phase6-v1"
        assert len(cfg.dataset_manifest_hash) == 64
        assert cfg.random_seed is not None


def test_config_hash_is_deterministic_and_order_independent() -> None:
    a = TrainingConfig(**_MIN)
    b = TrainingConfig.model_validate(dict(reversed(list(_MIN.items()))))
    assert a.config_hash == b.config_hash
    # round-trip through JSON keeps identity
    assert TrainingConfig.model_validate_json(a.model_dump_json()).config_hash == (
        a.config_hash
    )


def test_materially_different_configs_have_different_hashes() -> None:
    a = load_config("configs/training/finetune-v1.yaml")
    b = load_config("configs/training/finetune-v1-full.yaml")
    assert a.training_config_version != b.training_config_version
    assert a.config_hash != b.config_hash


def test_description_is_not_part_of_identity() -> None:
    a = TrainingConfig(**_MIN, description="one")
    b = TrainingConfig(**_MIN, description="two")
    assert a.config_hash == b.config_hash


def test_missing_required_field_is_rejected(tmp_path) -> None:
    bad = tmp_path / "c.yaml"
    bad.write_text("base_model: x\n", encoding="utf-8")
    with pytest.raises(TrainingConfigError):
        load_config(bad)


def test_malformed_yaml_is_rejected(tmp_path) -> None:
    bad = tmp_path / "c.yaml"
    bad.write_text("base_model: [unclosed\n", encoding="utf-8")
    with pytest.raises(TrainingConfigError):
        load_config(bad)


def test_path_traversal_in_model_id_is_rejected() -> None:
    with pytest.raises(Exception):
        TrainingConfig(**{**_MIN, "base_model": "../../etc/passwd"})


def test_optional_none_fields_do_not_change_hash() -> None:
    a = TrainingConfig(**_MIN)
    b = TrainingConfig(**_MIN, warmup_ratio=None, weight_decay=None)
    assert a.config_hash == b.config_hash


def test_dump_and_reload_roundtrip(tmp_path) -> None:
    cfg = load_config("configs/training/finetune-v1.yaml")
    p = dump_config(cfg, tmp_path / "out.yaml")
    assert load_config(p).config_hash == cfg.config_hash
