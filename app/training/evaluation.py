"""
Post-training evaluation (#121 Part 9).

The fine-tuned checkpoint is scored with the **same** Phase 6 machinery
the #120 baseline uses — same frozen benchmark, same prompts, same
metrics, same scoring. No parallel metric implementation exists here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.providers.base import LLMProvider
from app.benchmark.report import generate_report
from app.benchmark.suite import load_benchmark
from app.dataset.version import BENCHMARK_VERSION
from app.evaluation.modes import EvalMode
from app.evaluation.runner import run_evaluation
from app.training.errors import ComparisonError

__all__ = [
    "EvaluationArtifact",
    "evaluate_model",
    "verify_benchmark_untouched",
]


@dataclass(frozen=True)
class EvaluationArtifact:
    model_label: str
    mode: str
    benchmark_version: str
    benchmark_content_hash: str
    summary: dict[str, Any]
    detailed: list[dict[str, Any]]

    @classmethod
    def from_dir(cls, path: str | Path) -> "EvaluationArtifact":
        """Reconstruct an artifact from a previously written directory."""
        import json

        d = Path(path)
        summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        detailed_path = d / "detailed.jsonl"
        detailed = []
        if detailed_path.exists():
            detailed = [
                json.loads(line)
                for line in detailed_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        run = summary.get("run", {})
        return cls(
            model_label=str(run.get("model", "unknown")),
            mode=str(run.get("mode", "raw")),
            benchmark_version=str(summary.get("benchmark_version", "")),
            benchmark_content_hash=str(summary.get("benchmark_content_hash", "")),
            summary=summary,
            detailed=detailed,
        )

    def write(self, out_dir: str | Path) -> Path:
        import json

        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "summary.json").write_text(
            json.dumps(self.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (d / "detailed.jsonl").write_text(
            "\n".join(
                json.dumps(x, sort_keys=True, separators=(",", ":"))
                for x in self.detailed
            )
            + "\n",
            encoding="utf-8",
        )
        return d


def verify_benchmark_untouched(benchmark_version: str = BENCHMARK_VERSION) -> str:
    """Reload + hash-verify the frozen benchmark. Returns its content hash.

    ``load_benchmark`` raises if the on-disk examples no longer match the
    recorded hash, so a successful return proves the benchmark was not
    modified by anything the pipeline did.
    """
    suite = load_benchmark(benchmark_version)
    return suite.content_hash


def evaluate_model(
    provider: LLMProvider,
    *,
    model_label: str,
    benchmark_version: str = BENCHMARK_VERSION,
    mode: EvalMode = EvalMode.RAW,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout_s: int = 60,
    timestamp: str = "",
) -> EvaluationArtifact:
    suite = load_benchmark(benchmark_version)
    scores, run_meta = run_evaluation(
        provider,
        suite,
        mode,
        model=model_label,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
        timestamp=timestamp,
    )
    report = generate_report(suite, scores, run_meta)
    return EvaluationArtifact(
        model_label=model_label,
        mode=mode.value,
        benchmark_version=suite.benchmark_version,
        benchmark_content_hash=suite.content_hash,
        summary=report.summary,
        detailed=report.detailed,
    )


def require_comparable(a: EvaluationArtifact, b: EvaluationArtifact) -> None:
    """Refuse to compare evaluations run against different benchmarks."""
    if a.benchmark_version != b.benchmark_version:
        raise ComparisonError(
            f"benchmark version mismatch: {a.benchmark_version} vs "
            f"{b.benchmark_version}"
        )
    if a.benchmark_content_hash != b.benchmark_content_hash:
        raise ComparisonError("benchmark content hash mismatch — not comparable")
    if a.mode != b.mode:
        raise ComparisonError(
            f"evaluation mode mismatch: {a.mode} vs {b.mode} — compare like with like"
        )
    a_pv = a.summary.get("prompt_version")
    b_pv = b.summary.get("prompt_version")
    if a_pv != b_pv:
        raise ComparisonError(f"prompt version mismatch: {a_pv} vs {b_pv}")
