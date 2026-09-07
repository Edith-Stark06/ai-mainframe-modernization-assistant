"""Shared helpers for #121 fine-tuning-pipeline tests.

No test here touches a live LLM, a real training backend, or the
network. The shipped config points at ``phase6-v2`` — the
benchmark-disjoint training dataset — so the pipeline resolves cleanly
at the normal ``min_training_sources`` threshold with zero exclusions.
``phase6-v1`` (still benchmark-leaky) is exercised read-only in
``test_dataset_resolution.py`` as a regression guard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.training.config import load_config
from app.training.evaluation import EvaluationArtifact
from app.training.pipeline import TrainingRun, run_training

CONFIG_V1 = "configs/training/finetune-v1.yaml"


@pytest.fixture
def config_v1():
    return load_config(CONFIG_V1)


@pytest.fixture
def mock_run(tmp_path: Path, config_v1) -> TrainingRun:
    return run_training(
        config_v1,
        backend="mock",
        output_root=tmp_path / "runs",
        run_id="run-under-test",
        created_at="2026-01-01T00:00:00Z",
    )


def make_summary(
    *,
    n: int = 22,
    pass_rate: float = 0.5,
    hallucination_rate: float = 0.3,
    attribution_precision: float = 0.4,
    attribution_recall: float = 0.4,
    parse_failure_rate: float = 0.0,
    provider_failures: int = 0,
    by_task: dict[str, float] | None = None,
    by_difficulty: dict[str, float] | None = None,
    hallucination_totals: dict[str, int] | None = None,
    benchmark_version: str = "benchmark-v1",
    benchmark_content_hash: str = "hash-abc",
    prompt_version: str = "p6-prompt-v1",
) -> dict[str, Any]:
    by_task = by_task or {"business_rule_extraction": pass_rate}
    by_difficulty = by_difficulty or {"medium": pass_rate}
    return {
        "benchmark_version": benchmark_version,
        "benchmark_content_hash": benchmark_content_hash,
        "prompt_version": prompt_version,
        "analysis_version": "deterministic-analysis-phases-1-5",
        "run": {"mode": "raw", "model": "m", "provider_failures": provider_failures},
        "overall": {
            "n": n,
            "pass_rate": pass_rate,
            "hallucination_rate": hallucination_rate,
            "hallucination_totals": hallucination_totals or {},
            "attribution_precision": attribution_precision,
            "attribution_recall": attribution_recall,
            "parse_failure_rate": parse_failure_rate,
        },
        "by_task": {k: {"n": n, "pass_rate": v} for k, v in by_task.items()},
        "by_difficulty": {
            k: {"n": n, "pass_rate": v} for k, v in by_difficulty.items()
        },
        "failures": [],
    }


def make_artifact(model_label: str = "m", **kw: Any) -> EvaluationArtifact:
    summary = make_summary(**kw)
    return EvaluationArtifact(
        model_label=model_label,
        mode="raw",
        benchmark_version=summary["benchmark_version"],
        benchmark_content_hash=summary["benchmark_content_hash"],
        summary=summary,
        detailed=[],
    )
