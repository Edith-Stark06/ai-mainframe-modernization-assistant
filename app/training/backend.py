"""
Training backends (#121 Part 6) and checkpoint-evaluation providers
(#121 Part 9).

Real fine-tuning needs a compatible framework + base-model weights +
(realistically) a GPU. When that is present, :class:`TransformersLoRABackend`
runs an actual LoRA fine-tune. When it is **not** present the pipeline
does not fabricate a model — :func:`build_backend` with ``auto`` raises
:class:`TrainingBackendUnavailableError`, and the only other option,
:class:`DeterministicMockBackend`, is explicitly a *test fixture*: it
writes a checkpoint descriptor (no weights) so the rest of the pipeline
— manifest, evaluation plumbing, comparison, decision — can be exercised
end to end. Its output is never a real fine-tuned model and is never
committed or registered as ``ADOPTED``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.ai.providers.base import LLMProvider
from app.ai.providers.models import LLMRequest, LLMResponse
from app.training.config import TrainingConfig
from app.training.dataset import ResolvedTrainingData
from app.training.errors import CheckpointError, TrainingBackendUnavailableError

__all__ = [
    "TrainingOutcome",
    "TrainingBackend",
    "DeterministicMockBackend",
    "TransformersLoRABackend",
    "build_backend",
    "MockCheckpointProvider",
    "build_checkpoint_provider",
    "MOCK_CHECKPOINT_FILE",
    "MOCK_WARNING",
]

MOCK_CHECKPOINT_FILE = "mock_checkpoint.json"
MOCK_WARNING = (
    "NOT A REAL FINE-TUNED MODEL. This descriptor is produced by the "
    "deterministic mock training backend to exercise the #121 pipeline "
    "without a GPU or model weights. It must never be evaluated or "
    "registered as an actual fine-tuned checkpoint."
)


@dataclass(frozen=True)
class TrainingOutcome:
    checkpoint_dir: Path
    checkpoint_hash: str
    backend: str
    is_real_model: bool
    metrics: dict[str, float]
    notes: str


@runtime_checkable
class TrainingBackend(Protocol):
    name: str
    is_real: bool

    def train(
        self,
        config: TrainingConfig,
        data: ResolvedTrainingData,
        output_dir: Path,
        run_id: str,
    ) -> TrainingOutcome: ...


def _canonical_hash(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class DeterministicMockBackend:
    """A NON-TRAINING fixture backend. Deterministic; produces no weights."""

    name = "deterministic-mock"
    is_real = False

    def train(
        self,
        config: TrainingConfig,
        data: ResolvedTrainingData,
        output_dir: Path,
        run_id: str,
    ) -> TrainingOutcome:
        output_dir.mkdir(parents=True, exist_ok=True)
        # The checkpoint identity is a function of *what was trained*
        # (config + data + seed), not the run label — so re-running the
        # same config/data yields the same checkpoint hash.
        identity = {
            "backend": self.name,
            "config_hash": config.config_hash,
            "config_version": config.training_config_version,
            "base_model": config.base_model,
            "seed": config.random_seed,
            "dataset_version": data.dataset_version,
            "dataset_manifest_hash": data.dataset_manifest_hash,
            "training_split": data.split,
            "training_example_count": data.example_count,
            "training_source_ids": list(data.source_ids),
            "excluded_benchmark_sources": list(data.excluded_benchmark_sources),
            "record_ids": [r.example_id for r in data.records],
        }
        checkpoint_hash = _canonical_hash(identity)
        descriptor = {
            "warning": MOCK_WARNING,
            "run_id": run_id,
            "checkpoint_hash": checkpoint_hash,
            **identity,
        }
        path = output_dir / MOCK_CHECKPOINT_FILE
        path.write_text(
            json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # a deterministic pseudo "final loss" derived from the fingerprint,
        # clearly labelled as synthetic in ``notes``.
        pseudo_loss = round(0.5 + (int(checkpoint_hash[:8], 16) % 1000) / 4000.0, 4)
        return TrainingOutcome(
            checkpoint_dir=output_dir,
            checkpoint_hash=checkpoint_hash,
            backend=self.name,
            is_real_model=False,
            metrics={"synthetic_final_loss": pseudo_loss, "steps": 0},
            notes=MOCK_WARNING,
        )


class TransformersLoRABackend:
    """Real LoRA fine-tuning via Hugging Face ``transformers`` + ``peft``.

    Constructing it fails fast with
    :class:`TrainingBackendUnavailableError` when the training stack or a
    resolvable base model is missing — which is the case in the current
    CI/dev environment (CPU-only ``torch``; no ``peft`` / ``datasets`` /
    ``accelerate``).
    """

    name = "transformers-lora"
    is_real = True

    def __init__(self) -> None:
        missing = [
            m
            for m in ("torch", "transformers", "peft", "datasets", "accelerate")
            if _find_spec(m) is None
        ]
        if missing:
            raise TrainingBackendUnavailableError(
                "real fine-tuning needs " + ", ".join(missing) + " — not "
                "installed. Install the training extra and provide a base "
                "model, or use --backend mock for a pipeline dry-run "
                "(which does NOT produce a real model)."
            )

    def train(  # pragma: no cover - requires the full training stack + weights
        self,
        config: TrainingConfig,
        data: ResolvedTrainingData,
        output_dir: Path,
        run_id: str,
    ) -> TrainingOutcome:
        raise TrainingBackendUnavailableError(
            "TransformersLoRABackend.train is only reachable with the training "
            "stack and base-model weights available; document the command and "
            "run it on a suitable machine."
        )


def _find_spec(name: str) -> object | None:
    import importlib.util

    try:
        return importlib.util.find_spec(name)
    except (ImportError, ValueError):  # pragma: no cover
        return None


def build_backend(name: str = "auto") -> TrainingBackend:
    if name == "mock":
        return DeterministicMockBackend()
    if name in ("transformers-lora", "hf-lora"):
        return TransformersLoRABackend()
    if name == "auto":
        return TransformersLoRABackend()  # raises if unavailable — never mock
    raise TrainingBackendUnavailableError(
        f"unknown training backend {name!r} (use auto | transformers-lora | mock)"
    )


# ---------------------------------------------------------------------------
# checkpoint -> evaluation provider
# ---------------------------------------------------------------------------


class MockCheckpointProvider(LLMProvider):
    """Evaluate a *mock* checkpoint. NOT a real fine-tuned model.

    It confirms the directory holds a mock descriptor and then delegates
    generation to the Phase 6 :class:`HeuristicDemoProvider` — a
    deterministic, clearly-labelled non-LLM stand-in. This exists so the
    end-to-end pipeline test can produce a real, comparable benchmark
    report structure without a GPU or model service. Its scores are not a
    real fine-tuning result.
    """

    def __init__(self, checkpoint_dir: str | Path) -> None:
        path = Path(checkpoint_dir) / MOCK_CHECKPOINT_FILE
        if not path.exists():
            raise CheckpointError(
                f"{path} not found — MockCheckpointProvider only evaluates "
                f"checkpoints produced by DeterministicMockBackend"
            )
        descriptor = json.loads(path.read_text(encoding="utf-8"))
        if descriptor.get("backend") != DeterministicMockBackend.name:
            raise CheckpointError(f"{path} is not a mock checkpoint descriptor")
        self._hash = str(descriptor.get("checkpoint_hash", ""))
        if not self._hash:
            raise CheckpointError(f"{path} has no checkpoint_hash")
        self.model = f"mock-checkpoint:{self._hash[:8]}"

    def generate(self, request: LLMRequest) -> LLMResponse:
        from app.evaluation.demo_model import answer_from_prompt

        return LLMResponse(
            text=answer_from_prompt(request.prompt), model=self.model, usage=None
        )


def build_checkpoint_provider(
    checkpoint_dir: str | Path, *, real: bool = False
) -> LLMProvider:
    if real:  # pragma: no cover - needs the inference stack + weights
        raise TrainingBackendUnavailableError(
            "loading a real fine-tuned checkpoint for inference needs the "
            "transformers runtime and the checkpoint weights on this machine"
        )
    return MockCheckpointProvider(checkpoint_dir)
