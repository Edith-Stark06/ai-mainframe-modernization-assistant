"""#131 — the language-neutral execution result model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ProgramSpec", "ExecutionResult"]


class ProgramSpec(BaseModel):
    """What to execute and what to observe afterward.

    ``payload`` is executor-specific (COBOL source text for
    :class:`~app.behavioral.execution.cobol_executor.CobolExecutor`, a
    :class:`~app.java_modernization.generation.models.GeneratedProject`
    for :class:`~app.behavioral.execution.java_executor.JavaExecutor`) —
    the :class:`ProgramExecutor` protocol only requires it be *something*
    the concrete executor knows how to run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    source_id: str
    kind: str  # "cobol" | "java"
    payload: Any
    #: COBOL field names whose post-execution value should be observed
    observe_fields: tuple[str, ...] = ()
    observe_stdout: bool = True
    artifact_version: str = ""


class ExecutionResult(BaseModel):
    """A structured, normalized observation of one program run.

    ``executed=False`` means the runtime itself never ran the program
    (unavailable compiler/runtime, sandbox rejection, timeout before any
    output) — this is NOT the same as ``success=False`` with
    ``executed=True`` (the program ran and reported/threw an error).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    executed: bool
    success: bool
    executor_kind: str  # "java_real" | "cobol_real" | "cobol_unavailable" | "scripted"

    outputs: dict[str, str] = Field(default_factory=dict)
    calculated_values: dict[str, str] = Field(default_factory=dict)
    statuses: dict[str, str] = Field(default_factory=dict)
    errors: tuple[str, ...] = ()
    state_changes: dict[str, str] = Field(default_factory=dict)

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_s: float = 0.0

    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
