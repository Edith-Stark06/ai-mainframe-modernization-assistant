"""
#131 — real COBOL execution via GnuCOBOL (``cobc``), when present.

**In this environment `cobc` is NOT on PATH — every call returns
``ExecutionResult(executed=False, executor_kind="cobol_unavailable")``.**
No large runtime is downloaded to make tests pass (per the task's
explicit instruction); the comparator turns that into INCONCLUSIVE, never
PASS or FAIL.

If GnuCOBOL *is* present, this compiles the program with ``cobc -x`` and
runs the executable. Inputs are injected by patching the matching
``VALUE`` clause in ``WORKING-STORAGE SECTION`` (deterministic, regex
based — COBOL fixtures here have no ``ACCEPT`` statements) — a
best-effort mechanism, not a general COBOL input framework. Only stdout
(``DISPLAY``) is observable this way; post-execution field state is
**not** observable from a plain compiled executable, so
``state_changes``/``calculated_values`` come back empty with an explicit
diagnostic rather than a fabricated value — callers relying on field
state alone will correctly get INCONCLUSIVE from the comparator.

This code path is implemented for completeness (per the task's "implement
the execution abstraction" requirement) but is **unverified in this
environment** — say so in any report that uses it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from app.behavioral.execution.models import ExecutionResult, ProgramSpec

__all__ = ["CobolExecutor", "cobol_runtime_available", "cobol_compiler_version"]

_VALUE_RE_TEMPLATE = r"(01\s+{name}\b[^.\n]*?VALUE\s+)('[^']*'|\"[^\"]*\"|-?\d+)"


def cobol_runtime_available(cobc: str = "cobc") -> bool:
    return shutil.which(cobc) is not None


def cobol_compiler_version(cobc: str = "cobc") -> str:
    if not cobol_runtime_available(cobc):
        return "unavailable"
    try:
        out = subprocess.run(
            [cobc, "--version"], capture_output=True, text=True, timeout=10
        )
        return (out.stdout or out.stderr).splitlines()[0].strip() or "unknown"
    except Exception:  # pragma: no cover - defensive
        return "unknown"


class CobolExecutor:
    def __init__(
        self,
        workspace_root: str | Path,
        *,
        cobc: str = "cobc",
        compile_timeout_s: float = 30.0,
        run_timeout_s: float = 10.0,
        max_output_bytes: int = 200_000,
    ) -> None:
        self._root = Path(workspace_root)
        self._cobc = cobc
        self._compile_timeout = compile_timeout_s
        self._run_timeout = run_timeout_s
        self._max_output = max_output_bytes

    def execute(self, spec: ProgramSpec, inputs: dict[str, str]) -> ExecutionResult:
        if spec.kind != "cobol" or not isinstance(spec.payload, str):
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="cobol_unavailable",
                diagnostics=("ProgramSpec.payload is not COBOL source text",),
            )
        if not cobol_runtime_available(self._cobc):
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="cobol_unavailable",
                diagnostics=(
                    f"GnuCOBOL ({self._cobc!r}) not found on PATH — real COBOL "
                    "execution is unavailable in this environment",
                ),
            )

        proj_dir = (
            self._root / f"cobol-{spec.source_id}-{abs(hash(spec.payload)) % 10**8}"
        )
        proj_dir.mkdir(parents=True, exist_ok=True)
        patched = self._patch_values(spec.payload, inputs)
        src_path = proj_dir / f"{spec.source_id}.cbl"
        src_path.write_text(patched, encoding="utf-8", newline="\n")
        exe_path = proj_dir / spec.source_id

        compile_cmd = [self._cobc, "-x", "-o", str(exe_path), str(src_path)]
        try:
            cp = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                timeout=self._compile_timeout,
                cwd=str(proj_dir),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="cobol_real",
                diagnostics=(f"cobc timed out after {self._compile_timeout}s",),
            )
        if cp.returncode != 0:
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="cobol_real",
                diagnostics=(f"cobc compile failed: {(cp.stderr or cp.stdout)[:500]}",),
            )

        started = time.perf_counter()
        try:
            rp = subprocess.run(
                [str(exe_path)],
                capture_output=True,
                text=True,
                timeout=self._run_timeout,
                cwd=str(proj_dir),
            )
            stdout, stderr, exit_code = rp.stdout or "", rp.stderr or "", rp.returncode
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="cobol_real",
                duration_s=round(time.perf_counter() - started, 4),
                diagnostics=(f"COBOL executable timed out after {self._run_timeout}s",),
            )
        duration = round(time.perf_counter() - started, 4)
        stdout, stderr = stdout[: self._max_output], stderr[: self._max_output]

        outputs = {f"stdout[{i}]": line for i, line in enumerate(stdout.splitlines())}
        diagnostics: tuple[str, ...] = ()
        if spec.observe_fields:
            diagnostics = (
                "post-execution COBOL field state is not observable from a "
                "compiled executable without additional instrumentation — "
                f"requested field(s) {list(spec.observe_fields)} were not read back",
            )

        return ExecutionResult(
            executed=True,
            success=(exit_code == 0),
            executor_kind="cobol_real",
            outputs=outputs,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_s=duration,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _patch_values(source: str, inputs: dict[str, str]) -> str:
        patched = source
        for name, value in inputs.items():
            lit = value if value.replace("-", "").isdigit() else f"'{value}'"
            pattern = re.compile(
                _VALUE_RE_TEMPLATE.format(name=re.escape(name)), re.IGNORECASE
            )
            patched = pattern.sub(lambda m: m.group(1) + lit, patched, count=1)
        return patched
