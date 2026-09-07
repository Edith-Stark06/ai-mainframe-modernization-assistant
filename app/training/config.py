"""
Versioned, machine-readable training configuration (#121 Part 3).

A :class:`TrainingConfig` fully specifies a fine-tuning run: base model,
tokenizer, dataset version + hash, split, seed and every hyper-parameter
that materially affects the result.

* It is serialisable to / from YAML and JSON.
* :meth:`TrainingConfig.config_hash` is a stable content hash — two
  materially different configurations produce different hashes, and the
  same configuration always produces the same hash regardless of key
  order or file formatting.
* ``training_config_version`` is the human-facing label; the hash is the
  machine identity.

Only parameters that are actually applied are recorded. Optional
hyper-parameters left as ``None`` are omitted from the hash so adding a
knob with its default value does not silently invalidate historical
config identities.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.training.errors import TrainingConfigError
from app.training.version import PREPROCESSING_VERSION

__all__ = ["TrainingConfig", "load_config", "dump_config"]


class TrainingConfig(BaseModel):
    """A complete, reproducible fine-tuning configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- identity -----------------------------------------------------
    training_config_version: str = Field(..., min_length=1)
    description: str = ""

    # --- model ------------------------------------------------------
    base_model: str = Field(..., min_length=1)
    tokenizer: str = Field(..., min_length=1)
    method: str = Field(
        "lora",
        description="fine-tuning method, e.g. 'lora' | 'full' | 'qlora'",
    )

    # --- data ------------------------------------------------------
    dataset_version: str = Field(..., min_length=1)
    dataset_manifest_hash: str = Field(
        ...,
        min_length=8,
        description="sha256 of the canonical training dataset file (#118)",
    )
    training_split: str = Field("train", pattern="^(train|validation|test)$")
    preprocessing_version: str = PREPROCESSING_VERSION
    max_training_examples: int | None = Field(None, gt=0)

    # --- optimisation ---------------------------------------------
    random_seed: int = 42
    epochs: float = Field(1.0, gt=0)
    learning_rate: float = Field(..., gt=0)
    batch_size: int = Field(..., gt=0)
    gradient_accumulation_steps: int = Field(1, gt=0)
    max_sequence_length: int = Field(..., gt=0)
    warmup_ratio: float | None = Field(None, ge=0, le=1)
    weight_decay: float | None = Field(None, ge=0)
    lr_scheduler: str | None = None

    # --- method-specific (LoRA / PEFT) ---------------------------
    lora_r: int | None = Field(None, gt=0)
    lora_alpha: int | None = Field(None, gt=0)
    lora_dropout: float | None = Field(None, ge=0, le=1)
    lora_target_modules: tuple[str, ...] | None = None

    # --- strategy -----------------------------------------------
    evaluation_strategy: str = Field("epoch")
    checkpoint_strategy: str = Field("epoch")

    # --- free-form, still hashed --------------------------------
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_model", "tokenizer")
    @classmethod
    def _no_path_traversal(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("model / tokenizer id must not contain '..'")
        return v

    # ---------------------------------------------------------------

    def canonical_dict(self) -> dict[str, Any]:
        """The dict that defines this config's identity (``None`` dropped)."""
        raw = self.model_dump(mode="json", exclude_none=True)
        # ``description`` is documentation, not identity.
        raw.pop("description", None)
        return raw

    @property
    def config_hash(self) -> str:
        payload = json.dumps(
            self.canonical_dict(), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_yaml(self) -> str:
        return yaml.safe_dump(
            self.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            default_flow_style=False,
        )

    def to_json(self) -> str:
        return json.dumps(self.canonical_dict(), indent=2, sort_keys=True) + "\n"


def load_config(path: str | Path) -> TrainingConfig:
    """Parse a YAML or JSON training config, validating every field."""
    p = Path(path)
    if not p.exists():
        raise TrainingConfigError(f"training config not found: {p}")
    text = p.read_text(encoding="utf-8")
    try:
        if p.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise TrainingConfigError(f"{p} is not valid {p.suffix}: {exc}") from exc
    if not isinstance(data, dict):
        raise TrainingConfigError(f"{p} must contain a mapping at the top level")
    try:
        return TrainingConfig.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise TrainingConfigError(f"{p} is not a valid training config: {exc}") from exc


def dump_config(config: TrainingConfig, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(config.to_yaml(), encoding="utf-8")
    return p
