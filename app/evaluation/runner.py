"""
#120 baseline evaluation runner.

``run_evaluation(provider, suite, mode)`` -> (scores, run_meta).

The same benchmark, prompts, metrics and scoring are used for every mode
and provider — only :func:`build_context` differs. Provider failures and
timeouts are recorded as failure cases, never silently dropped. Token /
cost information is taken from ``LLMResponse.usage`` when the provider
supplies it, and reported as ``"unavailable"`` otherwise — never
estimated.
"""

from __future__ import annotations

import time
from typing import Any

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMProviderError
from app.ai.providers.models import LLMRequest
from app.benchmark.models import BenchmarkSuite
from app.benchmark.scoring import ExampleScore, score_example
from app.dataset.version import DATASET_VERSION
from app.evaluation.modes import EvalMode, build_context
from app.evaluation.prompts import PROMPT_VERSION, build_prompt

__all__ = ["run_evaluation"]


def run_evaluation(
    provider: LLMProvider,
    suite: BenchmarkSuite,
    mode: EvalMode,
    *,
    model: str = "",
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout_s: int = 60,
    timestamp: str = "",
) -> tuple[list[ExampleScore], dict[str, Any]]:
    scores: list[ExampleScore] = []
    latencies: list[float] = []
    prompt_tokens = 0
    completion_tokens = 0
    have_tokens = False
    provider_failures = 0
    provider_name = type(provider).__name__

    for ex in sorted(suite.examples, key=lambda e: e.example_id):
        context = build_context(mode, ex)
        prompt = build_prompt(ex, context)
        request = LLMRequest(
            prompt=prompt,
            model=model or None,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        started = time.perf_counter()
        try:
            resp = provider.generate(request)
            output = resp.text
            if resp.usage:
                have_tokens = True
                prompt_tokens += int(resp.usage.get("prompt_tokens", 0) or 0)
                completion_tokens += int(resp.usage.get("completion_tokens", 0) or 0)
        except LLMProviderError as exc:
            provider_failures += 1
            output = ""
            sc = score_example(ex, output)
            sc = ExampleScore(
                example_id=sc.example_id,
                task_type=sc.task_type,
                difficulty=sc.difficulty,
                parsed_ok=False,
                metrics=sc.metrics,
                hallucinations=sc.hallucinations,
                attribution=sc.attribution,
                passed=False,
                notes=[*sc.notes, f"provider_failure: {exc}"],
            )
            scores.append(sc)
            latencies.append(time.perf_counter() - started)
            continue

        latencies.append(time.perf_counter() - started)
        scores.append(score_example(ex, output))

    mean_latency = round(sum(latencies) / len(latencies), 4) if latencies else 0.0

    run_meta: dict[str, Any] = {
        "mode": mode.value,
        "provider": provider_name,
        "model": model or "n/a",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout_s": timeout_s,
        "prompt_version": PROMPT_VERSION,
        "dataset_version": DATASET_VERSION,
        "benchmark_version": suite.benchmark_version,
        "analysis_version": suite.analysis_version,
        "timestamp": timestamp or "n/a",
        "example_count": len(scores),
        "provider_failures": provider_failures,
        "mean_latency_s": mean_latency,
        "total_tokens": (
            prompt_tokens + completion_tokens if have_tokens else "unavailable"
        ),
        "prompt_tokens": prompt_tokens if have_tokens else "unavailable",
        "completion_tokens": completion_tokens if have_tokens else "unavailable",
        "estimated_cost": "unavailable",
    }
    return scores, run_meta
