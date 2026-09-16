"""
#120 baseline LLM evaluation — run the frozen benchmark in all three
modes and produce the comparison + capability analysis.

    python -m scripts.evaluation.run_baseline_eval \
        [--provider heuristic-demo|scripted|langchain|fake] \
        [--model ollama:llama3] [--script PATH] [--out DIR]

Writes ``<out>/<mode>/summary.{json,md}`` + ``detailed.jsonl`` for each
mode, plus ``<out>/comparison.json`` and ``<out>/capability_analysis.json``.

Unit tests never invoke this with a live provider. ``--provider
langchain`` reads its own credentials from the environment; nothing is
committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.benchmark.report import generate_report
from app.benchmark.suite import load_benchmark
from app.dataset.corpus import REPO_ROOT
from app.dataset.version import BENCHMARK_VERSION
from app.evaluation.capability_analysis import build_capability_analysis
from app.evaluation.modes import EvalMode
from app.evaluation.providers import build_provider
from app.evaluation.runner import run_evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default="heuristic-demo",
        choices=["heuristic-demo", "scripted", "langchain", "fake"],
    )
    parser.add_argument("--model", default="")
    parser.add_argument("--script", default="")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--timestamp", default="")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "reports" / "baseline-eval" / BENCHMARK_VERSION),
    )
    args = parser.parse_args(argv)

    suite = load_benchmark(BENCHMARK_VERSION)
    print(
        f"benchmark {suite.benchmark_version} "
        f"({len(suite.examples)} examples, hash {suite.content_hash[:12]})"
    )

    out_root = Path(args.out)
    per_mode_summaries: dict[str, dict] = {}

    for mode in (EvalMode.RAW, EvalMode.ANALYSIS, EvalMode.RETRIEVAL):
        provider = build_provider(
            args.provider,
            model=args.model,
            temperature=args.temperature,
            timeout_s=args.timeout,
            script_path=args.script or None,
        )
        scores, run_meta = run_evaluation(
            provider,
            suite,
            mode,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout,
            timestamp=args.timestamp,
        )
        report = generate_report(suite, scores, run_meta)
        report.write(out_root / mode.value)
        per_mode_summaries[mode.value] = report.summary
        o = report.summary["overall"]
        print(
            f"  {mode.value:9} pass={o['pass_rate']:.3f} "
            f"halluc={o['hallucination_rate']:.3f} "
            f"attr_p={o['attribution_precision']:.3f} "
            f"parse_fail={o['parse_failure_rate']:.3f}"
        )

    comparison = {
        "benchmark_version": suite.benchmark_version,
        "benchmark_content_hash": suite.content_hash,
        "prompt_version": per_mode_summaries["raw"]["prompt_version"],
        "analysis_version": suite.analysis_version,
        "provider": args.provider,
        "model": args.model or "n/a",
        "modes": {
            m: {
                "overall": s["overall"],
                "by_difficulty": s["by_difficulty"],
                "run": {
                    k: s["run"].get(k)
                    for k in (
                        "mean_latency_s",
                        "total_tokens",
                        "estimated_cost",
                        "provider_failures",
                    )
                },
            }
            for m, s in per_mode_summaries.items()
        },
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    cap = build_capability_analysis(
        per_mode_summaries["raw"],
        per_mode_summaries["analysis"],
        per_mode_summaries["retrieval"],
    )
    (out_root / "capability_analysis.json").write_text(
        json.dumps(cap, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_root / "capability_analysis.md").write_text(_cap_md(cap), encoding="utf-8")

    print(f"\n{cap['overall_conclusion']}\n")
    print(f"wrote {out_root}")
    return 0


def _cap_md(cap: dict) -> str:
    lines = [
        "# Capability analysis / fine-tuning assessment (#120)",
        "",
        f"- benchmark: `{cap['benchmark_version']}`  prompt: "
        f"`{cap['prompt_version']}`  analysis: `{cap['analysis_version']}`",
        f"- providers: {cap['providers']}",
        "",
        f"**{cap['overall_conclusion']}**",
        "",
        "| task | raw | analysis | retrieval | lift | failure | cause | "
        "fine-tuning evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in cap["per_task"]:
        lines.append(
            f"| {r['task']} | {r['raw_pass_rate']} | {r['analysis_pass_rate']} | "
            f"{r['retrieval_pass_rate']} | {r['context_lift']} | "
            f"{r['dominant_failure']} | {r['likely_cause']} | "
            f"{r['fine_tuning_evidence']} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
