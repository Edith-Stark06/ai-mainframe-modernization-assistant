"""
#121 — compare a baseline and a fine-tuned evaluation, and emit the
improvement decision.

    python -m scripts.training.compare_models \
        --baseline reports/baseline-eval/benchmark-v1/raw \
        --candidate reports/training-runs/<run_id>/eval \
        [--out DIR] [--register --model-version <mv> [--registry PATH]]

Both inputs are directories containing a ``summary.json`` (+ optional
``detailed.jsonl``) written by the evaluation step. The comparison
refuses to run if the two evaluations used different benchmark
versions / content hashes / prompt versions / modes.

Decision: IMPROVED | NO_MEANINGFUL_IMPROVEMENT | REGRESSED | INCONCLUSIVE.
Never marks a model ADOPTED.
"""

from __future__ import annotations

import argparse
import sys

from app.training.comparison import compare_models
from app.training.errors import TrainingPipelineError
from app.training.evaluation import EvaluationArtifact
from app.training.registry import DEFAULT_REGISTRY_PATH, ModelRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="dir with summary.json")
    parser.add_argument("--candidate", required=True, help="dir with summary.json")
    parser.add_argument("--out", default="")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--model-version", default="")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    args = parser.parse_args(argv)

    baseline = EvaluationArtifact.from_dir(args.baseline)
    candidate = EvaluationArtifact.from_dir(args.candidate)

    try:
        result = compare_models(baseline, candidate)
    except TrainingPipelineError as exc:
        print(f"\nCOMPARISON NOT RUN: {exc}\n", file=sys.stderr)
        return 2

    print(result.to_markdown())

    if args.out:
        result.write(args.out)
        print(f"wrote: {args.out}")

    if args.register:
        if not args.model_version:
            print("--register requires --model-version", file=sys.stderr)
            return 2
        reg = ModelRegistry(args.registry)
        rec = reg.attach_evaluation(args.model_version, result)
        reg.save()
        print(f"registry: {rec.model_version} -> status {rec.status} ({rec.decision})")

    # exit code reflects the decision for CI use
    return {"IMPROVED": 0, "NO_MEANINGFUL_IMPROVEMENT": 0}.get(result.decision, 1)


if __name__ == "__main__":
    sys.exit(main())
