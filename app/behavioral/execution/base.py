"""#131 — the execution abstraction. No runtime is hard-coded into #131's comparator."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.behavioral.execution.models import ExecutionResult, ProgramSpec

__all__ = ["ProgramExecutor"]


@runtime_checkable
class ProgramExecutor(Protocol):
    def execute(self, spec: ProgramSpec, inputs: dict[str, str]) -> ExecutionResult:
        """Run *spec* with *inputs* (COBOL field name -> value) and return
        a structured, normalized observation. Must never raise for a
        program failure or an unavailable runtime — both are reported as
        fields on :class:`ExecutionResult`."""
        ...
