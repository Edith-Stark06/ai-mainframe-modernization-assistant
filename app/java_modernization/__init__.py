"""
Phase 9 — Java modernization pipeline (#125–#128).

    COBOL analysis
      -> #125 architecture (evidence-based, deterministic)
      -> #126 generated Java project (reuses the existing backend)
      -> #127 controlled compilation (structured diagnostics)
      -> #128 bounded, grounded AI self-repair

Produces a modernization **candidate**. Compilation success is not
behavioral equivalence — Phase 10 (#129–#131) owns that.
"""

from __future__ import annotations

from app.java_modernization.architecture import JavaArchitecture, build_architecture
from app.java_modernization.compilation import (
    CompilationResult,
    CompilerDiagnostic,
    JavaCompiler,
    javac_available,
)
from app.java_modernization.errors import (
    ArchitectureError,
    CompilationSetupError,
    GenerationError,
    JavaModernizationError,
    UnsafePatchError,
)
from app.java_modernization.generation import GeneratedProject, generate_project
from app.java_modernization.orchestrator import Phase9Result, run_java_modernization
from app.java_modernization.repair import RepairResult, SelfRepairLoop

__all__ = [
    "build_architecture",
    "JavaArchitecture",
    "generate_project",
    "GeneratedProject",
    "JavaCompiler",
    "javac_available",
    "CompilationResult",
    "CompilerDiagnostic",
    "SelfRepairLoop",
    "RepairResult",
    "run_java_modernization",
    "Phase9Result",
    "JavaModernizationError",
    "ArchitectureError",
    "GenerationError",
    "CompilationSetupError",
    "UnsafePatchError",
]
