"""#119 — evaluation benchmark tests."""

from __future__ import annotations

import json

import pytest

from app.benchmark.metrics import (
    attribution,
    concept_coverage,
    java_structural_coverage,
    prf,
    rule_match_prf,
    strategy_correctness,
)
from app.benchmark.models import BenchmarkSuite, compute_content_hash
from app.benchmark.report import generate_report
from app.benchmark.scoring import score_example
from app.benchmark.suite import load_benchmark
from app.dataset.schema import Difficulty
from app.dataset.version import BENCHMARK_VERSION


@pytest.fixture(scope="module")
def suite() -> BenchmarkSuite:
    return load_benchmark(BENCHMARK_VERSION)


# ---------------------------------------------------------------------------
# immutability + structure
# ---------------------------------------------------------------------------


def test_frozen_benchmark_loads_and_hash_verifies(suite) -> None:
    assert suite.benchmark_version == BENCHMARK_VERSION
    assert len(suite.examples) >= 16
    assert suite.content_hash == compute_content_hash(suite.examples)


def test_mutating_a_benchmark_example_fails_hash_check(suite) -> None:
    mutated = list(suite.examples)
    first = mutated[0]
    mutated[0] = first.model_copy(update={"expected_output": {"tampered": True}})
    with pytest.raises(ValueError, match="content hash mismatch"):
        BenchmarkSuite(
            benchmark_version=suite.benchmark_version,
            prompt_version=suite.prompt_version,
            analysis_version=suite.analysis_version,
            content_hash=suite.content_hash,
            examples=tuple(mutated),
        )


def test_every_example_is_never_training(suite) -> None:
    assert all(e.never_training is True for e in suite.examples)


def test_all_four_difficulties_present_and_defined(suite) -> None:
    dist = {d.value for d in suite.by_difficulty()}
    assert dist == {"easy", "medium", "difficult", "adversarial"}


def test_adversarial_examples_document_their_trap(suite) -> None:
    adv = suite.by_difficulty()[Difficulty.ADVERSARIAL]
    assert len(adv) >= 4
    assert all((e.trap or "").strip() for e in adv)


def test_benchmark_covers_the_required_tasks(suite) -> None:
    tasks = {t.value for t in suite.by_task()}
    for required in (
        "cobol_explanation",
        "business_rule_extraction",
        "risk_identification",
        "modernization_recommendation",
        "source_grounded_qa",
        "cobol_to_java",
    ):
        assert required in tasks


def test_benchmark_is_not_the_training_dataset() -> None:
    # the dataset builder must not read/write the benchmark dir
    import app.dataset.builder as b

    src = b.__file__
    text = open(src, encoding="utf-8").read()
    assert "benchmark" not in text.lower()


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def test_prf_basic() -> None:
    r = prf({"a", "b", "c"}, {"b", "c", "d"})
    assert round(r.precision, 3) == 0.667
    assert round(r.recall, 3) == 0.667
    assert prf(set(), set()).f1 == 1.0


def test_concept_coverage() -> None:
    assert concept_coverage("uses WS-A and MAIN-PARA", ["WS-A", "MAIN-PARA"]) == 1.0
    assert concept_coverage("nothing here", ["WS-A", "WS-B"]) == 0.0


def test_rule_match_prf_is_order_independent() -> None:
    g = [{"condition": "A = 1", "actions": [{"raw": "X = 2"}]}]
    p = [{"condition": "A  =  1", "actions": [{"raw": "X = 2"}]}]
    assert rule_match_prf(p, g).f1 == 1.0


def test_strategy_correctness() -> None:
    assert strategy_correctness("REWRITE", "rewrite") == 1.0
    assert strategy_correctness("REHOST", "REWRITE") == 0.0


def test_attribution_rewards_only_supporting_citations() -> None:
    src = "line one\n       CALL 'SUB'.\nline three\n"
    good = attribution([{"line": 2, "claim_terms": ["CALL"]}], src, [{"line": 2}])
    assert good.precision == 1.0 and good.recall == 1.0
    # a citation to a line that does not contain the claimed token
    bad = attribution([{"line": 1, "claim_terms": ["CALL"]}], src, [{"line": 2}])
    assert bad.precision == 0.0
    # an out-of-range citation is invented
    inv = attribution([{"line": 99, "claim_terms": ["CALL"]}], src, [{"line": 2}])
    assert inv.invented == 1


def test_java_structural_coverage() -> None:
    gold = (
        "public class X { public static void main(String[] a){} void run(){ return; } }"
    )
    good = java_structural_coverage(gold, gold)
    assert good["construct_coverage"] == 1.0
    bad = java_structural_coverage("// nothing", gold)
    assert bad["construct_coverage"] == 0.0
    assert bad["missing"]


# ---------------------------------------------------------------------------
# scoring — oracle & adversarial
# ---------------------------------------------------------------------------


def test_oracle_answers_pass_the_whole_benchmark(suite) -> None:
    fails = [
        e.example_id
        for e in suite.examples
        if not score_example(e, json.dumps(e.expected_output)).passed
    ]
    assert fails == []


def test_garbage_answers_fail_and_are_flagged(suite) -> None:
    for e in suite.examples:
        sc = score_example(e, "the WS-INVENTED-THING drives a FRAUD-SCORE rule")
        assert not sc.passed


def test_adversarial_bait_is_caught_business_rules(suite) -> None:
    # the misleading-comment example: gold is [], any invented rule fails
    ex = next(
        e for e in suite.examples if e.input.source_id == "syn_misleading_comments"
    )
    baited = score_example(
        ex,
        json.dumps(
            {"business_rules": [{"condition": "VIP", "actions": ["20% discount"]}]}
        ),
    )
    assert not baited.passed
    assert baited.hallucinations["invented_business_rule"] >= 1


def test_not_determinable_question_requires_acknowledging_it(suite) -> None:
    ex = next(e for e in suite.examples if e.rubric.get("answer_is_not_determinable"))
    guessed = score_example(ex, json.dumps({"answer": {"tier": "GOLD"}}))
    assert not guessed.passed
    assert guessed.hallucinations["unsupported_by_source"] >= 1
    honest = score_example(ex, "This cannot be determined from the source.")
    assert honest.passed


# ---------------------------------------------------------------------------
# scoring determinism + report
# ---------------------------------------------------------------------------


def test_scoring_is_deterministic(suite) -> None:
    ex = suite.examples[0]
    a = score_example(ex, "some answer").to_dict()
    b = score_example(ex, "some answer").to_dict()
    assert a == b


def test_report_generation_is_deterministic(suite) -> None:
    scores = [score_example(e, json.dumps(e.expected_output)) for e in suite.examples]
    meta = {"model": "m", "provider": "p", "mode": "raw", "prompt_version": "pv"}
    r1 = generate_report(suite, scores, meta)
    r2 = generate_report(suite, list(reversed(scores)), meta)
    assert r1.to_summary_json() == r2.to_summary_json()
    assert r1.to_detailed_jsonl() == r2.to_detailed_jsonl()
    json.loads(r1.to_summary_json())
    assert "# Benchmark report" in r1.to_summary_md()


def test_report_records_versions(suite) -> None:
    scores = [score_example(e, "{}") for e in suite.examples]
    r = generate_report(
        suite,
        scores,
        {
            "model": "m",
            "provider": "p",
            "mode": "analysis",
            "prompt_version": "p6-prompt-v1",
        },
    )
    s = r.summary
    assert s["benchmark_version"] == BENCHMARK_VERSION
    assert s["benchmark_content_hash"] == suite.content_hash
    assert s["prompt_version"] == "p6-prompt-v1"
    assert s["analysis_version"] == suite.analysis_version
