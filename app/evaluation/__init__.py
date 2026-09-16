"""
Phase 6 — Baseline LLM Evaluation (#120).

Runs the frozen benchmark (#119) against a provider in three modes (raw
/ deterministic-analysis / retrieved-context) with identical prompts,
metrics and scoring, then produces a capability / fine-tuning assessment.

No model training. Unit tests never touch a live provider.
"""

from app.evaluation.capability_analysis import build_capability_analysis
from app.evaluation.modes import EvalMode, build_context
from app.evaluation.providers import (
    RecordingLLMProvider,
    ScriptedLLMProvider,
    build_provider,
    prompt_fingerprint,
)
from app.evaluation.runner import run_evaluation

__all__ = [
    "EvalMode",
    "build_context",
    "build_provider",
    "prompt_fingerprint",
    "ScriptedLLMProvider",
    "RecordingLLMProvider",
    "run_evaluation",
    "build_capability_analysis",
]
