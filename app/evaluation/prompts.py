"""
Versioned prompt templates for the #120 baseline evaluation.

``PROMPT_VERSION`` (from :mod:`app.dataset.version`) is recorded in every
report so results are reproducible and comparable across runs.

Structured tasks are instructed to answer with a single JSON object; QA
tasks are asked to include a ``citations`` array so source attribution
can be scored.
"""

from __future__ import annotations

from app.benchmark.models import BenchmarkExample
from app.dataset.schema import TaskType
from app.dataset.version import PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "build_prompt"]

_SYSTEM = (
    "You are a COBOL modernization analyst. Answer ONLY from the provided "
    "material. If the material does not support an answer, say so explicitly "
    "rather than guessing. Never invent identifiers, dependencies, business "
    "rules, risks, or source line numbers."
)

_TASK_INSTRUCTIONS = {
    TaskType.COBOL_EXPLANATION: (
        "Explain what this program does: its paragraphs, its data flow, any "
        "external calls, and any construct the analysis could not represent. "
        "Answer in prose."
    ),
    TaskType.BUSINESS_RULE_EXTRACTION: (
        "Extract the business rules. Reply with a JSON object "
        '{"business_rules": [{"condition": "...", "actions": ["..."]}]}. '
        'If there are none, reply {"business_rules": []}.'
    ),
    TaskType.RISK_IDENTIFICATION: (
        "Identify the modernization risks. Reply with a JSON object "
        '{"risks": [{"category": "...", "severity": "LOW|MEDIUM|HIGH|CRITICAL"}]}.'
    ),
    TaskType.MODERNIZATION_RECOMMENDATION: (
        "Recommend a modernization strategy. Reply with a JSON object "
        '{"primary": {"strategy": "REHOST|REFACTOR|REPLATFORM|REWRITE|'
        'STRANGLER_MODERNIZATION|SERVICE_EXTRACTION|PHASED_MIGRATION", '
        '"prerequisites": ["..."]}}.'
    ),
    TaskType.COBOL_TO_STRUCTURED: (
        "Produce a structured representation. Reply with a JSON object "
        '{"ast": {"procedure_division": {"paragraphs": [{"name": "..."}]}}, '
        '"cfg_summary": {...}}.'
    ),
    TaskType.COBOL_TO_JAVA: (
        "Translate this program to Java. Reply with a JSON object "
        '{"java": "<full Java source>"}.'
    ),
    TaskType.MODERNIZATION_QA: (
        "Answer the question. If it asks about business rules, reply "
        '{"answer": {"business_rules": [{"rule_id": "...", "condition": "..."}]}}. '
        'Otherwise answer as JSON with an "answer" field.'
    ),
    TaskType.SOURCE_GROUNDED_QA: (
        "Answer the question ONLY from the source. Reply with a JSON object "
        '{"answer": {...}, "citations": [{"line": <n>, "claim_terms": ["..."]}]}. '
        "If the answer is not determinable from the source, reply "
        '{"answer": {"determinable": false}}.'
    ),
}


def build_prompt(example: BenchmarkExample, context: str) -> str:
    task = example.task_type
    question = example.input.context.get("question")
    q_line = f"\n## Question\n{question}\n" if question else ""
    return (
        f"{_SYSTEM}\n\n"
        f"## Task\n{_TASK_INSTRUCTIONS[task]}\n"
        f"{q_line}\n"
        f"{context}\n"
        f"## Your answer\n"
    )
