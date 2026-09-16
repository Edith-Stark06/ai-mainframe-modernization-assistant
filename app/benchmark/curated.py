"""
The curated ``benchmark-v1`` example set (#119).

Each entry pairs one corpus source with one task, a gold answer taken
from the deterministic analysis (or a hand-authored expectation for
adversarial cases), and a hand-authored ``rubric`` that says what a
correct model answer must satisfy.

This module is executed once by ``scripts/benchmark/freeze_benchmark.py``
to write the immutable ``data/benchmark/benchmark-v1/``. It is never
imported by the dataset builder.
"""

from __future__ import annotations

import tempfile
from typing import Any

from app.benchmark.models import BenchmarkExample
from app.dataset.analysis_bundle import build_analysis_bundle
from app.dataset.corpus import load_phase6_corpus
from app.dataset.schema import (
    Difficulty,
    ExampleAnalysis,
    ExampleInput,
    SourceLocation,
    TaskType,
    derive_example_id,
)
from app.dataset.version import BENCHMARK_VERSION

__all__ = ["build_benchmark_examples"]


# (source_id, task, difficulty, trap, rubric-overrides)
_SPEC: tuple[tuple[str, TaskType, Difficulty, str | None, dict[str, Any]], ...] = (
    ("fx_hello_world", TaskType.COBOL_EXPLANATION, Difficulty.EASY, None, {}),
    ("fx_move_display", TaskType.COBOL_TO_JAVA, Difficulty.EASY, None, {}),
    ("fx_arithmetic", TaskType.COBOL_TO_JAVA, Difficulty.EASY, None, {}),
    ("fx_arithmetic", TaskType.COBOL_TO_STRUCTURED, Difficulty.EASY, None, {}),
    ("fx_if_else", TaskType.BUSINESS_RULE_EXTRACTION, Difficulty.MEDIUM, None, {}),
    ("fx_if_else", TaskType.COBOL_TO_JAVA, Difficulty.MEDIUM, None, {}),
    ("fx_call", TaskType.RISK_IDENTIFICATION, Difficulty.MEDIUM, None, {}),
    ("fx_call", TaskType.SOURCE_GROUNDED_QA, Difficulty.MEDIUM, None, {"q": "calls"}),
    ("fx_eligibility", TaskType.BUSINESS_RULE_EXTRACTION, Difficulty.MEDIUM, None, {}),
    (
        "fx_eligibility",
        TaskType.MODERNIZATION_QA,
        Difficulty.MEDIUM,
        None,
        {"q": "rules"},
    ),
    (
        "syn_status_machine",
        TaskType.BUSINESS_RULE_EXTRACTION,
        Difficulty.MEDIUM,
        None,
        {},
    ),
    ("syn_limit_check", TaskType.BUSINESS_RULE_EXTRACTION, Difficulty.MEDIUM, None, {}),
    ("fx_complex_proc", TaskType.RISK_IDENTIFICATION, Difficulty.DIFFICULT, None, {}),
    (
        "fx_complex_proc",
        TaskType.MODERNIZATION_RECOMMENDATION,
        Difficulty.DIFFICULT,
        None,
        {},
    ),
    ("fx_highly_coupled", TaskType.RISK_IDENTIFICATION, Difficulty.DIFFICULT, None, {}),
    (
        "fx_acctbatch",
        TaskType.MODERNIZATION_RECOMMENDATION,
        Difficulty.DIFFICULT,
        None,
        {},
    ),
    (
        "fx_unsupported",
        TaskType.SOURCE_GROUNDED_QA,
        Difficulty.ADVERSARIAL,
        "COMP-3 and GO TO are unsupported by the analyzer; the honest "
        "answer names them, and must not claim the program is fully analysed.",
        {"q": "unsupported"},
    ),
    (
        "fx_file_processing",
        TaskType.RISK_IDENTIFICATION,
        Difficulty.ADVERSARIAL,
        "file I/O verbs are unsupported; risks must reflect the analysis "
        "gap, not invent a working file pipeline.",
        {},
    ),
    (
        "fx_incomplete",
        TaskType.COBOL_EXPLANATION,
        Difficulty.ADVERSARIAL,
        "the parser stops before EOF (a misplaced DATA DIVISION); an "
        "explanation must not describe the unparsed tail as analysed.",
        {},
    ),
    (
        "syn_misleading_names",
        TaskType.MODERNIZATION_QA,
        Difficulty.ADVERSARIAL,
        "WS-FRAUD-SCORE is only a loop counter; the answer must not claim "
        "a fraud-scoring business rule.",
        {"q": "rules"},
    ),
    (
        "syn_misleading_comments",
        TaskType.BUSINESS_RULE_EXTRACTION,
        Difficulty.ADVERSARIAL,
        "a comment claims a 20% VIP discount; the code applies no discount, "
        "so no such rule exists.",
        {},
    ),
    (
        "syn_ambiguous_question",
        TaskType.SOURCE_GROUNDED_QA,
        Difficulty.ADVERSARIAL,
        "the question asks which customer tier gets priority, but the "
        "program has no customer/tier concept — the answer is 'not "
        "determinable from the source'.",
        {"q": "not_determinable"},
    ),
)


def _bundle_for(source_id: str, source: str):
    return build_analysis_bundle(
        source_id, source, tempfile.mkdtemp(prefix="bench-freeze-")
    )


def _analysis_block(bundle) -> ExampleAnalysis:
    return ExampleAnalysis(
        ast=bundle.ast,
        ir=bundle.ir,
        cfg=bundle.cfg,
        dependencies=bundle.dependencies,
        business_rules=bundle.business_rules,
        risks=bundle.risks,
        strategy=bundle.strategy,
        coverage=bundle.coverage,
        confidence=bundle.confidence,
    )


def _call_targets(bundle) -> list[str]:
    return sorted(
        {
            (d.get("target", "") or "").strip("'\"")
            for d in (bundle.dependencies or [])
            if str(d.get("type", "")).upper() == "CALL"
        }
        - {""}
    )


def _unsupported_codes(bundle) -> list[str]:
    cov = bundle.coverage or {}
    return sorted((cov.get("unsupported_syntax") or {}).get("codes", []))


def _required_concepts(bundle) -> list[str]:
    concepts = set(bundle.paragraphs)
    concepts |= set(_call_targets(bundle))
    for r in bundle.business_rules or []:
        for v in r.get("variables", {}).get("conditions", []):
            concepts.add(v)
    return sorted(c for c in concepts if c)


def build_benchmark_examples() -> list[BenchmarkExample]:
    corpus = {r.source_id: r for r in load_phase6_corpus()}
    out: list[BenchmarkExample] = []

    for source_id, task, difficulty, trap, overrides in _SPEC:
        rec = corpus.get(source_id)
        if rec is None:
            continue
        bundle = _bundle_for(source_id, rec.source)
        analysis = _analysis_block(bundle)
        variant = f"{task.value}:{overrides.get('q', '')}"
        eid = derive_example_id(task, source_id, f"bench:{variant}")

        expected, rubric, locs, ctx = _expected_and_rubric(task, bundle, rec, overrides)

        out.append(
            BenchmarkExample(
                example_id=eid,
                benchmark_version=BENCHMARK_VERSION,
                task_type=task,
                difficulty=difficulty,
                never_training=True,
                input=ExampleInput(source=rec.source, source_id=source_id, context=ctx),
                analysis=analysis,
                expected_output=expected,
                source_locations=locs,
                rubric=rubric,
                trap=trap,
            )
        )
    return sorted(out, key=lambda e: e.example_id)


def _expected_and_rubric(
    task: TaskType, bundle, rec, overrides: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[SourceLocation], dict[str, Any]]:
    if task is TaskType.COBOL_EXPLANATION:
        expected = {
            "paragraphs": bundle.paragraphs,
            "external_calls": _call_targets(bundle),
            "unsupported_constructs": _unsupported_codes(bundle),
        }
        rubric = {
            "required_concepts": _required_concepts(bundle),
            "min_concept_coverage": 0.5,
            "max_invented_identifiers": 0,
            "forbidden_terms": [],
        }
        return expected, rubric, [], {}

    if task is TaskType.BUSINESS_RULE_EXTRACTION:
        rules = bundle.business_rules or []
        expected = {"business_rules": rules}
        rubric = {"min_f1": 0.6 if rules else 1.0}
        if rec.source_id == "syn_misleading_comments":
            rubric["min_f1"] = 1.0  # gold is [] — any invented rule fails
        locs = [
            SourceLocation(line=int(loc["line"]))
            for r in rules
            for loc in r.get("source_locations", [])
            if loc.get("line")
        ]
        return expected, rubric, locs, {}

    if task is TaskType.RISK_IDENTIFICATION:
        risks = bundle.risks or []
        return (
            {"risks": risks},
            {"min_f1": 0.5 if risks else 1.0},
            [],
            {},
        )

    if task is TaskType.MODERNIZATION_RECOMMENDATION:
        strat = bundle.strategy or {"primary": None, "recommendations": []}
        return strat, {"min_prerequisite_recall": 0.3}, [], {}

    if task is TaskType.COBOL_TO_STRUCTURED:
        return (
            {
                "ast": bundle.ast,
                "cfg_summary": bundle.cfg_summary,
                "dependencies": bundle.dependencies or [],
            },
            {"min_f1": 0.8},
            [],
            {},
        )

    if task is TaskType.COBOL_TO_JAVA:
        return (
            {"java": rec.reviewed_java or bundle.java_backend_output},
            {"min_construct_coverage": 0.6},
            [],
            {},
        )

    if task is TaskType.MODERNIZATION_QA:
        which = overrides.get("q")
        if which == "rules":
            rules = bundle.business_rules or []
            expected = {
                "answer": {
                    "business_rules": [
                        {"rule_id": r["rule_id"], "condition": r["condition"]}
                        for r in rules
                    ]
                }
            }
            rubric = {
                "required_concepts": sorted(
                    {
                        v
                        for r in rules
                        for v in r.get("variables", {}).get("conditions", [])
                    }
                ),
                "min_concept_coverage": 0.5 if rules else 1.0,
                "forbidden_terms": (
                    ["FRAUD", "SCORE"]
                    if rec.source_id == "syn_misleading_names"
                    else []
                ),
                "max_invented_identifiers": 0,
            }
            return (
                expected,
                rubric,
                [],
                {"question": "What are the major business rules in this program?"},
            )
        # default QA
        return (
            {"answer": {"external_calls": _call_targets(bundle)}},
            {"required_concepts": _call_targets(bundle), "min_concept_coverage": 1.0},
            [],
            {"question": "What external dependencies does this program have?"},
        )

    if task is TaskType.SOURCE_GROUNDED_QA:
        which = overrides.get("q")
        if which == "calls":
            targets = _call_targets(bundle)
            call_lines = [
                i + 1
                for i, line in enumerate(rec.source.splitlines())
                if "CALL" in line.upper()
            ]
            return (
                {
                    "answer": {"external_calls": targets},
                    "citations": [
                        {"line": ln, "claim_terms": ["CALL"]} for ln in call_lines
                    ],
                },
                {"min_attribution_precision": 0.5},
                [
                    SourceLocation(
                        line=ln, snippet=rec.source.splitlines()[ln - 1].strip()
                    )
                    for ln in call_lines
                ],
                {"question": "Which external programs does this program CALL?"},
            )
        if which == "unsupported":
            codes = _unsupported_codes(bundle)
            return (
                {"answer": {"has_unsupported_syntax": bool(codes), "codes": codes}},
                {"min_attribution_precision": 0.0},
                [],
                {
                    "question": "Does this program use any COBOL construct the "
                    "analyzer does not support? If so, which?"
                },
            )
        if which == "not_determinable":
            return (
                {"answer": {"determinable": False}},
                {"answer_is_not_determinable": True},
                [],
                {
                    "question": "Which customer tier does this program give "
                    "priority to?"
                },
            )
        # fallback: paragraph inventory
        para_upper = {p.upper() for p in bundle.paragraphs}
        para_lines = [
            i + 1
            for i, line in enumerate(rec.source.splitlines())
            if line.strip().rstrip(".").upper() in para_upper
        ]
        return (
            {
                "answer": {"paragraphs": bundle.paragraphs},
                "citations": [{"line": ln, "claim_terms": []} for ln in para_lines],
            },
            {"min_attribution_precision": 0.5},
            [
                SourceLocation(line=ln, snippet=rec.source.splitlines()[ln - 1].strip())
                for ln in para_lines
            ],
            {"question": "What are the paragraph names in this program?"},
        )

    raise ValueError(f"no rubric builder for {task}")
