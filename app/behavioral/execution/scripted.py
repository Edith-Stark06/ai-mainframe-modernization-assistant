"""
#131 — deterministic scripted executor for unit/integration tests.

Proves the comparator's PASS/FAIL/INCONCLUSIVE logic independently of
any real runtime. Never claims to be ``"cobol_real"`` or ``"java_real"``
— :attr:`ScriptedExecutor.executor_kind` is always ``"scripted"`` so a
downstream report can never mistake a scripted comparison for a real one.
"""

from __future__ import annotations

from app.behavioral.execution.models import ExecutionResult, ProgramSpec

__all__ = ["ScriptedExecutor"]


class ScriptedExecutor:
    """``script[test_id]`` is either a fixed :class:`ExecutionResult`, or a
    callable ``(inputs) -> ExecutionResult`` for input-dependent scripts."""

    def __init__(self, script: dict[str, ExecutionResult | object]) -> None:
        self._script = script

    def execute(self, spec: ProgramSpec, inputs: dict[str, str]) -> ExecutionResult:
        key = spec.source_id
        entry = self._script.get(key)
        if entry is None:
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="scripted",
                diagnostics=(f"no script entry for {key!r}",),
            )
        if callable(entry):
            result = entry(inputs)
        else:
            result = entry
        if not isinstance(result, ExecutionResult):
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="scripted",
                diagnostics=("script entry did not return an ExecutionResult",),
            )
        return result.model_copy(update={"executor_kind": "scripted"})
