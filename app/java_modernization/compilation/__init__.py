"""#127 — controlled Java compilation + structured diagnostics."""

from __future__ import annotations

from app.java_modernization.compilation.compiler import JavaCompiler, javac_available
from app.java_modernization.compilation.models import (
    CompilationResult,
    CompilerDiagnostic,
    DiagnosticSeverity,
    GeneratedFileRecord,
)

__all__ = [
    "JavaCompiler",
    "javac_available",
    "CompilationResult",
    "CompilerDiagnostic",
    "DiagnosticSeverity",
    "GeneratedFileRecord",
]
