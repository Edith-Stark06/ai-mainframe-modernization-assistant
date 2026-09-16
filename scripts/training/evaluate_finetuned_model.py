"""
#121 — evaluate a checkpoint against the frozen Phase 6 benchmark.

    python -m scripts.training.evaluate_finetuned_model --run-dir <dir> \
        [--mode raw|analysis|retrieval] [--out DIR] [--label NAME]

Uses the SAME benchmark, prompts, metrics and scoring as the #120
baseline. For a mock checkpoint this builds the clearly-labelled
:class:`MockCheckpointProvider` (not a real model). A real checkpoint
needs the inference stack on the machine and ``--real``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.dataset.version import BENCHMARK_VERSION
from app.evaluation.modes import EvalMode
from app.training.backend import build_checkpoint_provider
from app.training.errors import TrainingPipelineError
from app.training.evaluation import evaluate_model, verify_benchmark_untouched


def _resolve_checkpoint(args: argparse.Namespace) -> tuple[Path, str]:
    if args.checkpoint:
        cp = Path(args.checkpoint)
        label = args.label or f"checkpoint:{cp.name}"
        return cp, label
    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "training_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cp = Path(manifest["checkpoint"]["checkpoint_path"])
        label = args.label or manifest["model_version"]
        return cp, label
    cp = run_dir / "checkpoint"
    return cp, (args.label or f"checkpoint:{run_dir.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--run-dir")
    src.add_argument("--checkpoint")
    parser.add_argument("--label", default="")
    parser.add_argument(
        "--mode", default="raw", choices=["raw", "analysis", "retrieval"]
    )
    parser.add_argument("--benchmark", default=BENCHMARK_VERSION)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--timestamp", default="")
    args = parser.parse_args(argv)

    before = verify_benchmark_untouched(args.benchmark)
    checkpoint_dir, label = _resolve_checkpoint(args)

    try:
        provider = build_checkpoint_provider(checkpoint_dir, real=args.real)
    except TrainingPipelineError as exc:
        print(f"\nEVALUATION NOT RUN: {exc}\n", file=sys.stderr)
        return 2

    artifact = evaluate_model(
        provider,
        model_label=label,
        benchmark_version=args.benchmark,
        mode=EvalMode(args.mode),
        timestamp=args.timestamp,
    )
    after = verify_benchmark_untouched(args.benchmark)
    assert before == after, "benchmark content hash changed during evaluation"

    o = artifact.summary["overall"]
    print(f"model:            {label}")
    print(f"benchmark:        {artifact.benchmark_version} ({before[:12]})")
    print(f"mode:             {artifact.mode}")
    print(f"pass rate:        {o['pass_rate']}")
    print(f"hallucination:    {o['hallucination_rate']}")
    print(f"attribution prec: {o['attribution_precision']}")

    if args.out:
        artifact.write(args.out)
        print(f"wrote:            {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
