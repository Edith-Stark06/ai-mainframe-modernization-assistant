"""
#121 — run a reproducible fine-tuning training run.

    python -m scripts.training.train_model --config configs/training/finetune-v1.yaml \
        [--backend auto|transformers-lora|mock] [--out DIR] [--register]

* ``--backend auto`` (default) uses the real Hugging Face LoRA backend and
  FAILS LOUDLY if the training stack / base-model weights are not present.
  It never silently substitutes a mock.
* ``--backend mock`` runs the DETERMINISTIC MOCK backend — a pipeline
  dry-run that produces a checkpoint *descriptor* (no weights). Its output
  is not a real fine-tuned model and must not be adopted.

Writes ``<out>/<run_id>/training_manifest.json`` (+ resolved config and
training records). With ``--register`` the run is added to the model
registry with status ``TRAINED``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.dataset.corpus import REPO_ROOT
from app.dataset.version import BENCHMARK_VERSION
from app.training.config import load_config
from app.training.dataset import DEFAULT_MIN_TRAINING_SOURCES
from app.training.errors import TrainingPipelineError
from app.training.pipeline import run_training
from app.training.registry import DEFAULT_REGISTRY_PATH, ModelRegistry

_DEFAULT_OUT = REPO_ROOT / "reports" / "training-runs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--backend", default="auto", choices=["auto", "transformers-lora", "mock"]
    )
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--benchmark", default=BENCHMARK_VERSION)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--created-at", default=None)
    parser.add_argument(
        "--min-training-sources", type=int, default=DEFAULT_MIN_TRAINING_SOURCES
    )
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    args = parser.parse_args(argv)

    config = load_config(args.config)
    print(
        f"config {config.training_config_version} "
        f"(hash {config.config_hash[:12]})  base_model={config.base_model}"
    )

    try:
        run = run_training(
            config,
            backend=args.backend,
            output_root=args.out,
            benchmark_version=args.benchmark,
            run_id=args.run_id,
            created_at=args.created_at,
            min_training_sources=args.min_training_sources,
            max_examples=args.max_examples,
        )
    except TrainingPipelineError as exc:
        print(f"\nTRAINING NOT RUN: {exc}\n", file=sys.stderr)
        return 2

    s = run.summary()
    print(f"run_id:          {s['run_id']}")
    print(f"model_version:   {s['model_version']}")
    print(f"real model:      {s['is_real_model']}")
    print(f"train examples:  {s['training_example_count']}")
    print(f"train sources:   {s['training_source_count']}")
    print(f"excluded (bench): {s['excluded_benchmark_sources']}")
    print(f"manifest:        {Path(run.run_dir) / 'training_manifest.json'}")

    if args.register:
        reg = ModelRegistry(args.registry)
        reg.register_training(run)
        reg.save()
        print(f"registered:      {run.model_version} -> {reg.path} (status TRAINED)")

    if not run.is_real_model:
        print(
            "\nNOTE: this run used a non-training backend. It is a pipeline "
            "dry-run, NOT a fine-tuned model."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
