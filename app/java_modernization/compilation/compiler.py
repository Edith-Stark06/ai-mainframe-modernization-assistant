"""
#127 — compile a generated Java project in a controlled workspace.

Security / limits:

* the compile command is built by this module — never from model output;
* every project-relative path is validated (no ``..``, no absolute, no
  drive letter, must land under the workspace);
* the compiler runs with a timeout and a bounded output buffer, and the
  process is killed on timeout.

A *compile failure* (bad Java) is a normal
:class:`~app.java_modernization.compilation.models.CompilationResult`
with ``success = False`` — only an unusable workspace / missing JDK
raises.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import time
from pathlib import Path

from app.java_modernization.compilation.models import (
    CompilationResult,
    CompilerDiagnostic,
    DiagnosticSeverity,
    GeneratedFileRecord,
)
from app.java_modernization.errors import CompilationSetupError
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["JavaCompiler", "javac_available"]

_DIAG_RE = re.compile(
    r"^(?P<file>(?:[A-Za-z]:)?[^:\n]+\.java):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?P<sev>error|warning|note):\s*(?P<msg>.*)$"
)
_METHOD_RE = re.compile(
    r"^[ \t]{2,}(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ]+?\s+(\w+)\s*\("
    r"[^;{]*\)\s*\{",
    re.MULTILINE,
)
_UNSAFE = re.compile(r"(^/|^[A-Za-z]:|\.\.[\\/]|[\\/]\.\.$|^\.\.$)")


def javac_available(javac: str = "javac") -> bool:
    return shutil.which(javac) is not None


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _jdk_version(javac: str) -> str:
    try:
        out = subprocess.run(
            [javac, "-version"], capture_output=True, text=True, timeout=10
        )
        return (out.stderr or out.stdout).strip() or "unknown"
    except Exception:  # pragma: no cover
        return "unknown"


def _safe_rel(rel: str) -> str:
    norm = rel.replace("\\", "/")
    if _UNSAFE.search(rel) or _UNSAFE.search(norm) or norm.startswith("/"):
        raise CompilationSetupError(f"unsafe project path rejected: {rel!r}")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise CompilationSetupError(f"path traversal rejected: {rel!r}")
    return "/".join(parts)


class JavaCompiler:
    def __init__(
        self,
        workspace_root: str | Path,
        *,
        javac: str = "javac",
        timeout_s: float = 30.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self._root = Path(workspace_root)
        self._javac = javac
        self._timeout = timeout_s
        self._max_output = max_output_bytes

    def compile(self, project: GeneratedProject) -> CompilationResult:
        if not javac_available(self._javac):
            raise CompilationSetupError(
                f"{self._javac!r} not found on PATH — cannot compile"
            )
        proj_dir = self._root / project.project_id
        src_dir = proj_dir / "src"
        out_dir = proj_dir / "out"
        if proj_dir.exists():
            shutil.rmtree(proj_dir)
        src_dir.mkdir(parents=True)
        out_dir.mkdir(parents=True)

        java_paths: list[Path] = []
        file_records: list[GeneratedFileRecord] = []
        for rel, content in project.files.items():
            safe = _safe_rel(rel)
            target = (proj_dir / safe).resolve()
            if not str(target).startswith(str(proj_dir.resolve())):
                raise CompilationSetupError(f"file escapes workspace: {rel!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            if safe.endswith(".java"):
                java_paths.append(target)
                file_records.append(
                    GeneratedFileRecord(
                        path=safe,
                        sha256=hashlib.sha256(content.encode()).hexdigest(),
                        classes=tuple(
                            re.findall(r"\b(?:class|record|interface)\s+(\w+)", content)
                        ),
                        source_locations=tuple(
                            a.source_locations[0]
                            for a in project.artifacts
                            if a.file_path == safe and a.source_locations
                        )[:1],
                    )
                )

        command = [
            self._javac,
            "-encoding",
            "UTF-8",
            "-d",
            str(out_dir),
            *sorted(str(p) for p in java_paths),
        ]

        started = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(proj_dir),
            )
            raw = (proc.stdout or "") + (proc.stderr or "")
            rc = proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            raw = _as_text(exc.stdout) + _as_text(exc.stderr)
            rc = -1
        duration = round(time.perf_counter() - started, 4)

        truncated = len(raw) > self._max_output
        raw = raw[: self._max_output]

        diagnostics = self._parse(raw, project)
        if timed_out:
            diagnostics = (
                *diagnostics,
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message=f"javac timed out after {self._timeout}s and was terminated",
                    error_code="P9-TIMEOUT",
                ),
            )

        success = (
            rc == 0
            and not timed_out
            and not any(d.severity is DiagnosticSeverity.ERROR for d in diagnostics)
        )
        return CompilationResult(
            success=success,
            diagnostics=diagnostics,
            file_records=tuple(file_records),
            command=tuple(command),
            duration_s=duration,
            timed_out=timed_out,
            output_truncated=truncated,
            jdk_version=_jdk_version(self._javac),
            workspace=str(proj_dir),
            raw_output=raw,
        )

    # -- diagnostic parsing + COBOL mapping --------------------------

    def _parse(
        self, raw: str, project: GeneratedProject
    ) -> tuple[CompilerDiagnostic, ...]:
        method_ranges = self._method_ranges(project)
        out: list[CompilerDiagnostic] = []
        for raw_line in raw.splitlines():
            m = _DIAG_RE.match(raw_line.strip())
            if not m:
                continue
            file_abs = m.group("file")
            rel = self._relativize(file_abs, project)
            line = int(m.group("line"))
            sev = {
                "error": DiagnosticSeverity.ERROR,
                "warning": DiagnosticSeverity.WARNING,
                "note": DiagnosticSeverity.NOTE,
            }[m.group("sev")]
            art = self._artifact_for(rel, line, method_ranges, project)
            out.append(
                CompilerDiagnostic(
                    severity=sev,
                    message=m.group("msg").strip(),
                    file=rel,
                    line=line,
                    column=int(m.group("col")) if m.group("col") else None,
                    cobol_source_mapping=(
                        art.source_locations[0]
                        if art and art.source_locations
                        else None
                    ),
                    business_rule_ids=art.business_rule_ids if art else (),
                    architecture_component_id=(
                        art.architecture_component_id if art else None
                    ),
                )
            )
        return tuple(out)

    @staticmethod
    def _relativize(file_str: str, project: GeneratedProject) -> str:
        name = Path(file_str.replace("\\", "/")).name
        for rel in project.files:
            if rel.endswith("/" + name) or rel == name or rel.endswith(name):
                return rel
        return name

    @staticmethod
    def _method_ranges(
        project: GeneratedProject,
    ) -> dict[str, list[tuple[int, int, str]]]:
        ranges: dict[str, list[tuple[int, int, str]]] = {}
        for rel, content in project.java_files.items():
            lines = content.splitlines()
            spans: list[tuple[int, int, str]] = []
            for mm in _METHOD_RE.finditer(content):
                start = content[: mm.start()].count("\n") + 1
                depth = 0
                end = start
                for i in range(start - 1, len(lines)):
                    depth += lines[i].count("{") - lines[i].count("}")
                    end = i + 1
                    if depth <= 0 and i >= start - 1:
                        break
                spans.append((start, end, mm.group(1)))
            ranges[rel] = spans
        return ranges

    @staticmethod
    def _artifact_for(rel, line, method_ranges, project):  # type: ignore[no-untyped-def]
        for start, end, mname in method_ranges.get(rel, []):
            if start <= line <= end:
                for a in project.artifacts:
                    if a.file_path == rel and a.method_name == mname:
                        return a
        for a in project.artifacts:
            if a.file_path == rel and a.kind == "class":
                return a
        return None
