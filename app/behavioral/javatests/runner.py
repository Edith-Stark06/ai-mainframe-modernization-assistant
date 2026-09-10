"""
#130 — compile + execute the generated Java behavior harness.

Reuses the #127 :class:`JavaCompiler` for compilation (same sandboxing:
controlled per-project workspace, path validation, timeout). Execution
of the compiled harness is likewise sandboxed: a fixed ``java`` command
built by this module (never from model output), a timeout, and a
bounded output buffer.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from app.behavioral.extraction.models import BehavioralSuite
from app.behavioral.javatests.generator import HARNESS_SUFFIX, generate_java_tests
from app.behavioral.javatests.models import (
    JavaTestArtifact,
    JavaTestRun,
    JavaTestSuiteResult,
)
from app.java_modernization.compilation.compiler import JavaCompiler, javac_available
from app.java_modernization.compilation.models import DiagnosticSeverity
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["JavaTestRunner", "java_available"]


class JavaTestRunner:
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

    def run_suite(
        self, suite: BehavioralSuite, project: GeneratedProject
    ) -> JavaTestSuiteResult:
        extra_files, artifacts = generate_java_tests(suite, project)
        test_project = project.model_copy(
            update={"files": {**project.files, **extra_files}}
        )
        compilation = self._compiler.compile(test_project)
        if not compilation.success:
            diags = tuple(
                f"{d.severity.value} {d.file}:{d.line}: {d.message}"
                for d in compilation.diagnostics
                if d.severity is DiagnosticSeverity.ERROR
            )
            return JavaTestSuiteResult(
                source_id=project.source_id,
                compiled=False,
                compile_diagnostics=diags,
                artifacts=artifacts,
            )

        out_dir = Path(compilation.workspace) / "out"
        runs = tuple(self._run_one(a, out_dir, project.main_class) for a in artifacts)
        return JavaTestSuiteResult(
            source_id=project.source_id,
            compiled=True,
            artifacts=artifacts,
            runs=runs,
        )

    def _run_one(
        self, artifact: JavaTestArtifact, out_dir: Path, main_class: str
    ) -> JavaTestRun:
        harness_class = f"{main_class}{HARNESS_SUFFIX}"
        # out_dir comes from JavaCompiler.compile(), which already confines
        # the whole project (including this classpath) to its own sandboxed
        # workspace; the java command itself is built entirely here, never
        # from model output.
        command = [self._java, "-cp", str(out_dir), harness_class, *artifact.run_args]

        started = time.perf_counter()
        timed_out = False
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
            timed_out = True
            stdout, stderr, exit_code = "", "", None
        duration = round(time.perf_counter() - started, 4)

        stdout = stdout[: self._max_output]
        stderr = stderr[: self._max_output]

        if timed_out:
            return JavaTestRun(
                test_id=artifact.test_id,
                execution_ok=False,
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                duration_s=duration,
                timed_out=True,
                diagnostics=(f"harness timed out after {self._run_timeout}s",),
            )

        exec_ok = True
        exec_error: str | None = None
        stdout_lines: list[str] = []
        field_values: dict[str, str] = {}
        assertion: bool | None = None
        failed_fields: tuple[str, ...] = ()

        for line in stdout.splitlines():
            if line.startswith("##EXEC## "):
                rest = line[len("##EXEC## ") :]
                exec_ok = "ok=true" in rest
                if "error=" in rest:
                    exec_error = rest.split("error=", 1)[1]
            elif line.startswith("##STDOUT## "):
                stdout_lines.append(line[len("##STDOUT## ") :])
            elif line.startswith("##FIELD## "):
                kv = line[len("##FIELD## ") :]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    field_values[k] = v
            elif line.startswith("##ASSERT## "):
                rest = line[len("##ASSERT## ") :]
                assertion = rest.startswith("PASS")
                if not assertion:
                    failed_fields = tuple(rest.replace("FAIL", "").split())

        diagnostics: tuple[str, ...] = ()
        if not exec_ok:
            diagnostics = (f"harness caught an exception: {exec_error}",)
        elif exit_code not in (0, 1):
            diagnostics = (f"harness exited with unexpected code {exit_code}",)
            exec_ok = False

        return JavaTestRun(
            test_id=artifact.test_id,
            execution_ok=exec_ok,
            assertion_passed=assertion,
            failed_fields=failed_fields,
            stdout_lines=tuple(stdout_lines),
            field_values=field_values,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration,
            timed_out=False,
            diagnostics=diagnostics,
        )


def java_available(java: str = "java") -> bool:
    import shutil

    return shutil.which(java) is not None and javac_available()
