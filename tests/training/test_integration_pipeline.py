"""#121 Part 16 — one deterministic end-to-end pipeline test.

    phase6 dataset -> config -> training run -> checkpoint metadata
        -> evaluation -> baseline comparison -> decision -> registry

Uses the DETERMINISTIC MOCK backend (labelled, no weights) and the
Phase 6 ``HeuristicDemoProvider`` for the baseline. No GPU, no model
service, no network. It proves the plumbing — not that fine-tuning works.
"""

from __future__ import annotations

from app.evaluation.modes import EvalMode
from app.evaluation.providers import HeuristicDemoProvider
from app.training.backend import MockCheckpointProvider
from app.training.comparison import compare_models
from app.training.config import load_config
from app.training.evaluation import evaluate_model, verify_benchmark_untouched
from app.training.pipeline import run_training
from app.training.registry import ModelRegistry

BV = "benchmark-v1"


def test_full_pipeline_mock(tmp_path) -> None:
    hash_before = verify_benchmark_untouched(BV)

    # 1. config -> 2. training run
    config = load_config("configs/training/finetune-v1.yaml")
    run = run_training(
        config,
        backend="mock",
        output_root=tmp_path / "runs",
        run_id="integration-run",
        created_at="2026-01-01T00:00:00Z",
    )

    # 3. checkpoint metadata / manifest
    assert run.is_real_model is False
    assert (run.run_dir / "training_manifest.json").exists()
    # phase6-v2 is benchmark-disjoint by construction: nothing to exclude,
    # and every training source is outside the benchmark.
    assert run.data.excluded_benchmark_sources == ()
    assert run.data.source_count >= 8
    manifest = run.manifest.to_dict()
    assert manifest["run_spec"]["benchmark_content_hash"] == hash_before

    # 4. evaluation (same benchmark + metrics as #120), same mode both sides
    baseline = evaluate_model(
        HeuristicDemoProvider(),
        model_label="baseline:heuristic-demo",
        benchmark_version=BV,
        mode=EvalMode.RAW,
    )
    candidate = evaluate_model(
        MockCheckpointProvider(run.checkpoint_dir),
        model_label=run.model_version,
        benchmark_version=BV,
        mode=EvalMode.RAW,
    )
    assert baseline.summary["overall"]["n"] == candidate.summary["overall"]["n"]

    # 5. comparison -> 6. decision
    comparison = compare_models(baseline, candidate)
    assert comparison.decision in (
        "IMPROVED",
        "NO_MEANINGFUL_IMPROVEMENT",
        "REGRESSED",
        "INCONCLUSIVE",
    )
    assert comparison.benchmark_content_hash == hash_before
    assert comparison.rationale

    # 7. registry — status is never ADOPTED off the back of a run
    reg = ModelRegistry(tmp_path / "registry.json")
    reg.register_training(run)
    rec = reg.attach_evaluation(run.model_version, comparison)
    assert rec.status != "ADOPTED"
    reg.save()

    # benchmark bytes untouched by the whole flow
    assert verify_benchmark_untouched(BV) == hash_before


def test_full_pipeline_is_deterministic(tmp_path) -> None:
    config = load_config("configs/training/finetune-v1.yaml")

    def once(where: str) -> tuple[str, str, dict]:
        run = run_training(
            config,
            backend="mock",
            output_root=tmp_path / where,
            run_id="r",
            created_at="2026-01-01T00:00:00Z",
        )
        cand = evaluate_model(
            MockCheckpointProvider(run.checkpoint_dir),
            model_label=run.model_version,
            benchmark_version=BV,
            mode=EvalMode.RAW,
        )
        return run.model_version, run.run_spec.spec_hash, cand.summary["overall"]

    a = once("a")
    b = once("b")
    assert a == b
