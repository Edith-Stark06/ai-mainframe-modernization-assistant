"""
#131 — real Java execution (`javac` + `java`, no fake).

Reuses the exact #130 harness (never a second, independently-derived
notion of "what the Java does") — compiles it once per
:class:`~app.java_modernization.generation.models.GeneratedProject` and
runs it per input set, requesting readback of ``spec.observe_fields``.
Sandboxed via the same #127 :class:`JavaCompiler` + a bounded, timed
``java`` subprocess (see #130's :class:`JavaTestRunner`).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from app.backend.java.naming import to_java_field_name
from app.behavioral.execution.models import ExecutionResult, ProgramSpec
from app.behavioral.javatests.generator import HARNESS_SUFFIX, render_harness
from app.java_modernization.compilation.compiler import JavaCompiler, javac_available
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["JavaExecutor", "java_runtime_available"]


def java_runtime_available(java: str = "java") -> bool:
    import shutil

    return shutil.which(java) is not None and javac_available()


class JavaExecutor:
    def __init__(
        self,
        workspace_root: str | Path,
        *,
        java: str = "java",
        javac: str = "javac",
        compile_timeout_s: float = 30.0,
        run_timeout_s: float = 10.0,
        max_output_bytes: int = 200_000,
    ) -> None:
        self._root = Path(workspace_root)
        self._java = java
        self._compiler = JavaCompiler(
            workspace_root, javac=javac, timeout_s=compile_timeout_s
        )
        self._run_timeout = run_timeout_s
        self._max_output = max_output_bytes
        self._compiled: dict[str, tuple[bool, Path, str]] = {}

    def execute(self, spec: ProgramSpec, inputs: dict[str, str]) -> ExecutionResult:
        if spec.kind != "java" or not isinstance(spec.payload, GeneratedProject):
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="java_real",
                diagnostics=("ProgramSpec.payload is not a GeneratedProject",),
            )
        if not java_runtime_available(self._java):
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="java_real",
                diagnostics=(f"{self._java!r} / javac not found on PATH",),
            )

        project = spec.payload
        ok, out_dir, main_class = self._ensure_compiled(project)
        if not ok:
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="java_real",
                diagnostics=("harness failed to compile — see JavaTestRunner output",),
            )

        args = [f"{to_java_field_name(k)}={v}" for k, v in inputs.items()]
        # keep a java-field-name -> COBOL-name map so the readback below can
        # report observations keyed by the SAME field name #129 used
        java_to_cobol = {to_java_field_name(f): f for f in spec.observe_fields}
        args += [f"expect:{jn}=" for jn in java_to_cobol]
        # a bare "expect:field=" (empty expected value) still triggers a
        # ##FIELD## readback line; it will never satisfy string equality
        # with a real expected value, so it must never be used for PASS —
        # only for observation. The comparator does the actual comparing.
        harness_class = f"{main_class}{HARNESS_SUFFIX}"
        command = [self._java, "-cp", str(out_dir), harness_class, *args]

        started = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._run_timeout,
                cwd=str(out_dir),
            )
            stdout, stderr, exit_code = (
                proc.stdout or "",
                proc.stderr or "",
                proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                executed=False,
                success=False,
                executor_kind="java_real",
                duration_s=round(time.perf_counter() - started, 4),
                diagnostics=(f"java timed out after {self._run_timeout}s",),
            )
        duration = round(time.perf_counter() - started, 4)
        stdout, stderr = stdout[: self._max_output], stderr[: self._max_output]

        exec_ok = True
        stdout_lines: list[str] = []
        fields: dict[str, str] = {}
        for line in stdout.splitlines():
            if line.startswith("##EXEC## "):
                exec_ok = "ok=true" in line
            elif line.startswith("##STDOUT## ") and spec.observe_stdout:
                stdout_lines.append(line[len("##STDOUT## ") :])
            elif line.startswith("##FIELD## ") and "=" in line:
                k, v = line[len("##FIELD## ") :].split("=", 1)
                fields[java_to_cobol.get(k, k)] = v

        outputs: dict[str, str] = {}
        if spec.observe_stdout:
            for i, line in enumerate(stdout_lines):
                outputs[f"stdout[{i}]"] = line
        outputs.update(fields)

        return ExecutionResult(
            executed=True,
            success=exec_ok,
            executor_kind="java_real",
            outputs=outputs,
            state_changes=dict(fields),
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_s=duration,
            diagnostics=() if exec_ok else ("target.run() raised — see stdout",),
        )

    def _ensure_compiled(self, project: GeneratedProject) -> tuple[bool, Path, str]:
        key = project.content_hash()
        if key in self._compiled:
            return self._compiled[key]
        harness_path = f"src/{project.main_class}{HARNESS_SUFFIX}.java"
        test_project = project.model_copy(
            update={
                "files": {
                    **project.files,
                    harness_path: render_harness(project.main_class),
                }
            }
        )
        result = self._compiler.compile(test_project)
        out_dir = Path(result.workspace) / "out"
        entry = (result.success, out_dir, project.main_class)
        self._compiled[key] = entry
        return entry
