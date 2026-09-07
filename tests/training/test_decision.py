"""#121 Parts 11-12 — the improvement decision. All four outcomes."""

from __future__ import annotations

import pytest

from app.training.comparison import (
    IMPROVED,
    INCONCLUSIVE,
    NO_MEANINGFUL_IMPROVEMENT,
    REGRESSED,
    compare_models,
)
from app.training.errors import ComparisonError
from tests.training.conftest import make_artifact


def _decide(baseline_kw, candidate_kw):
    return compare_models(
        make_artifact("baseline", **baseline_kw),
        make_artifact("candidate", **candidate_kw),
    )


def test_improved_requires_meaningful_gain_without_regression() -> None:
    r = _decide(
        dict(
            pass_rate=0.40,
            hallucination_rate=0.50,
            by_task={"risk_identification": 0.4},
        ),
        dict(
            pass_rate=0.62,
            hallucination_rate=0.45,
            by_task={"risk_identification": 0.7},
        ),
    )
    assert r.decision == IMPROVED
    assert any("rose by" in x for x in r.rationale)


def test_small_gain_is_not_improvement() -> None:
    r = _decide(dict(pass_rate=0.50), dict(pass_rate=0.53))
    assert r.decision == NO_MEANINGFUL_IMPROVEMENT


def test_overall_drop_is_regression() -> None:
    r = _decide(dict(pass_rate=0.60), dict(pass_rate=0.50))
    assert r.decision == REGRESSED


def test_more_hallucination_without_gain_is_regression() -> None:
    r = _decide(
        dict(pass_rate=0.50, hallucination_rate=0.30),
        dict(pass_rate=0.51, hallucination_rate=0.45),
    )
    assert r.decision == REGRESSED


def test_task_regression_not_offset_by_overall_is_regression() -> None:
    r = _decide(
        dict(pass_rate=0.50, by_task={"a": 0.9, "b": 0.5}),
        dict(pass_rate=0.52, by_task={"a": 0.5, "b": 0.55}),
    )
    assert r.decision == REGRESSED
    assert any("per-task regression" in x for x in r.rationale)


def test_higher_score_alone_does_not_force_adoption() -> None:
    # candidate overall is higher, but a critical task collapses -> REGRESSED
    r = _decide(
        dict(pass_rate=0.50, by_task={"critical": 1.0, "other": 0.2}),
        dict(pass_rate=0.58, by_task={"critical": 0.4, "other": 0.9}),
    )
    assert r.decision == REGRESSED
    assert r.decision != IMPROVED


def test_too_few_examples_is_inconclusive() -> None:
    r = _decide(dict(n=10, pass_rate=0.4), dict(n=10, pass_rate=0.9))
    assert r.decision == INCONCLUSIVE


def test_example_count_mismatch_is_inconclusive() -> None:
    r = _decide(dict(n=22, pass_rate=0.4), dict(n=20, pass_rate=0.6))
    assert r.decision == INCONCLUSIVE


def test_provider_failures_make_it_inconclusive() -> None:
    r = _decide(dict(pass_rate=0.4), dict(pass_rate=0.7, provider_failures=3))
    assert r.decision == INCONCLUSIVE


def test_high_parse_failure_is_inconclusive() -> None:
    r = _decide(dict(pass_rate=0.4), dict(pass_rate=0.7, parse_failure_rate=0.5))
    assert r.decision == INCONCLUSIVE


def test_small_sample_caveat_is_always_present_for_benchmark_v1() -> None:
    r = _decide(dict(pass_rate=0.40), dict(pass_rate=0.62))
    assert any("sample-size caveat" in x for x in r.rationale)


def test_refuses_to_compare_across_benchmark_hashes() -> None:
    with pytest.raises(ComparisonError):
        compare_models(
            make_artifact("b", benchmark_content_hash="h1"),
            make_artifact("c", benchmark_content_hash="h2"),
        )


def test_refuses_to_compare_across_prompt_versions() -> None:
    with pytest.raises(ComparisonError):
        compare_models(
            make_artifact("b", prompt_version="p6-prompt-v1"),
            make_artifact("c", prompt_version="p7-prompt-v9"),
        )


def test_comparison_serialises(tmp_path) -> None:
    r = _decide(dict(pass_rate=0.4), dict(pass_rate=0.62))
    r.write(tmp_path)
    assert (tmp_path / "comparison.json").exists()
    assert (tmp_path / "comparison.md").exists()
