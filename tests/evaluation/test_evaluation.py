"""#120 — baseline LLM evaluation tests. Never touches a live provider."""

from __future__ import annotations

import json

import pytest

from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.fake import FakeLLMProvider
from app.ai.providers.models import LLMRequest, LLMResponse
from app.benchmark.suite import load_benchmark
from app.dataset.version import BENCHMARK_VERSION, PROMPT_VERSION
from app.evaluation.capability_analysis import build_capability_analysis
from app.evaluation.modes import EvalMode, build_context
from app.evaluation.prompts import build_prompt
from app.evaluation.providers import (
    RecordingLLMProvider,
    ScriptedLLMProvider,
    build_provider,
    prompt_fingerprint,
)
from app.evaluation.runner import run_evaluation


@pytest.fixture(scope="module")
def suite():
    return load_benchmark(BENCHMARK_VERSION)


# ---------------------------------------------------------------------------
# modes / context
# ---------------------------------------------------------------------------


def test_raw_mode_has_no_analysis(suite) -> None:
    ex = suite.examples[0]
    ctx = build_context(EvalMode.RAW, ex)
    assert "```cobol" in ctx
    assert "Deterministic analysis" not in ctx
    assert "Retrieved deterministic evidence" not in ctx


def test_analysis_mode_includes_full_analysis(suite) -> None:
    ex = next(e for e in suite.examples if e.analysis.business_rules)
    ctx = build_context(EvalMode.ANALYSIS, ex)
    assert "Deterministic analysis" in ctx


def test_retrieval_mode_is_a_subset_of_analysis(suite) -> None:
    ex = next(e for e in suite.examples if e.analysis.risks)
    full = build_context(EvalMode.ANALYSIS, ex)
    retr = build_context(EvalMode.RETRIEVAL, ex)
    # retrieval is smaller than full analysis for a rich example
    assert len(retr) <= len(full)
    assert "Retrieved deterministic evidence" in retr


def test_prompt_records_task_and_question(suite) -> None:
    ex = next(e for e in suite.examples if e.input.context.get("question"))
    p = build_prompt(ex, "CTX")
    assert "## Task" in p
    assert ex.input.context["question"] in p
    assert "CTX" in p


# ---------------------------------------------------------------------------
# provider abstraction
# ---------------------------------------------------------------------------


def test_scripted_provider_replays_and_is_deterministic() -> None:
    req = LLMRequest(prompt="hello", temperature=0.0, max_tokens=10)
    fp = prompt_fingerprint(req)
    p = ScriptedLLMProvider({fp: "world"})
    assert p.generate(req).text == "world"
    assert p.generate(req).text == "world"


def test_scripted_provider_raises_on_missing_prompt() -> None:
    p = ScriptedLLMProvider({})
    with pytest.raises(LLMConfigurationError, match="no response for prompt"):
        p.generate(LLMRequest(prompt="unknown"))


def test_recording_provider_captures_responses() -> None:
    rec = RecordingLLMProvider(FakeLLMProvider(response_text="abc"))
    req = LLMRequest(prompt="p1", temperature=0.0, max_tokens=5)
    rec.generate(req)
    assert rec.recorded[prompt_fingerprint(req)] == "abc"


def test_build_provider_rejects_unknown() -> None:
    with pytest.raises(LLMConfigurationError, match="unknown eval provider"):
        build_provider("gpt-magic")


def test_build_provider_scripted_requires_script() -> None:
    with pytest.raises(LLMConfigurationError, match="requires --script"):
        build_provider("scripted")


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


class _AlwaysFail:
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderUnavailableError("simulated outage")


class _NoUsage:
    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="{}", model="x", usage=None)


def test_runner_records_provider_failures_not_crashes(suite) -> None:
    scores, meta = run_evaluation(_AlwaysFail(), suite, EvalMode.RAW)
    assert len(scores) == len(suite.examples)
    assert meta["provider_failures"] == len(suite.examples)
    assert all(not s.passed for s in scores)
    assert any("provider_failure" in n for s in scores for n in s.notes)


def test_runner_reports_tokens_unavailable_when_provider_omits_them(suite) -> None:
    _, meta = run_evaluation(_NoUsage(), suite, EvalMode.RAW)
    assert meta["total_tokens"] == "unavailable"
    assert meta["estimated_cost"] == "unavailable"


def test_runner_records_versions(suite) -> None:
    _, meta = run_evaluation(_NoUsage(), suite, EvalMode.ANALYSIS, model="m")
    assert meta["prompt_version"] == PROMPT_VERSION
    assert meta["benchmark_version"] == BENCHMARK_VERSION
    assert meta["mode"] == "analysis"


def test_runner_is_deterministic_with_scripted_provider(suite) -> None:
    # build a script covering every raw-mode prompt
    from app.evaluation.demo_model import answer_from_prompt

    script = {}
    for ex in suite.examples:
        req = LLMRequest(
            prompt=build_prompt(ex, build_context(EvalMode.RAW, ex)),
            model=None,
            temperature=0.0,
            max_tokens=2048,
        )
        script[prompt_fingerprint(req)] = answer_from_prompt(req.prompt)
    p = ScriptedLLMProvider(script)
    s1, _ = run_evaluation(p, suite, EvalMode.RAW)
    p2 = ScriptedLLMProvider(script)
    s2, _ = run_evaluation(p2, suite, EvalMode.RAW)
    assert [x.to_dict() for x in s1] == [x.to_dict() for x in s2]


# ---------------------------------------------------------------------------
# three-mode comparison + capability analysis
# ---------------------------------------------------------------------------


def test_three_modes_are_comparable_and_analysis_helps(suite) -> None:
    from app.benchmark.report import generate_report
    from app.evaluation.providers import HeuristicDemoProvider

    summaries = {}
    for mode in (EvalMode.RAW, EvalMode.ANALYSIS, EvalMode.RETRIEVAL):
        scores, meta = run_evaluation(HeuristicDemoProvider(), suite, mode)
        summaries[mode.value] = generate_report(suite, scores, meta).summary

    # same benchmark / same n across modes
    ns = {s["overall"]["n"] for s in summaries.values()}
    assert len(ns) == 1

    # deterministic analysis context must not make things worse
    assert (
        summaries["analysis"]["overall"]["pass_rate"]
        >= summaries["raw"]["overall"]["pass_rate"]
    )
    assert (
        summaries["analysis"]["overall"]["hallucination_rate"]
        <= summaries["raw"]["overall"]["hallucination_rate"]
    )


def test_capability_analysis_is_evidence_driven(suite) -> None:
    from app.benchmark.report import generate_report
    from app.evaluation.providers import HeuristicDemoProvider

    reports = {}
    for mode in (EvalMode.RAW, EvalMode.ANALYSIS, EvalMode.RETRIEVAL):
        scores, meta = run_evaluation(HeuristicDemoProvider(), suite, mode)
        reports[mode.value] = generate_report(suite, scores, meta).summary

    cap = build_capability_analysis(
        reports["raw"], reports["analysis"], reports["retrieval"]
    )
    json.dumps(cap)  # json-safe
    assert cap["per_task"]
    # a task that analysis lifts to high pass must NOT be flagged for fine-tuning
    for row in cap["per_task"]:
        if row["analysis_pass_rate"] >= 0.8 and row["context_lift"] >= 0.2:
            assert "no fine-tuning evidence" in row["fine_tuning_evidence"]
    # the overall conclusion never says "fine-tune because it's an AI project"
    assert "AI project" not in cap["overall_conclusion"]
