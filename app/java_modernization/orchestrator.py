"""
Phase 9 pipeline orchestrator (#125 -> #126 -> #127 -> #128).

    AnalysisBundle
      -> build_architecture        (#125, deterministic, evidence-based)
      -> generate_project          (#126, reuses the existing Java backend)
      -> JavaCompiler.compile       (#127, controlled workspace)
      -> SelfRepairLoop.run         (#128, bounded, grounded — only if a
                                     provider is supplied and it did not compile)

Produces a modernization CANDIDATE. ``semantic_equivalence_verified`` is
always ``False`` — Phase 10 owns behavioral comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.providers.base import LLMProvider
from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.architecture import JavaArchitecture, build_architecture
from app.java_modernization.compilation import (
    CompilationResult,
    JavaCompiler,
    javac_available,
)
from app.java_modernization.generation import GeneratedProject, generate_project
from app.java_modernization.repair import RepairResult, SelfRepairLoop

__all__ = ["Phase9Result", "run_java_modernization"]


@dataclass(frozen=True)
class Phase9Result:
    architecture: JavaArchitecture
    project: GeneratedProject
    initial_compilation: CompilationResult
    repair: RepairResult | None
    final_compilation: CompilationResult
    semantic_equivalence_verified: bool = False

    @property
    def compiles(self) -> bool:
        return self.final_compilation.success

    def to_dict(self) -> dict[str, Any]:
        return {
            "architecture": self.architecture.to_dict(),
            "project": self.project.manifest(),
            "initial_compilation": self.initial_compilation.to_dict(),
            "repair": self.repair.to_dict() if self.repair else None,
            "final_compilation": self.final_compilation.to_dict(),
            "compiles": self.compiles,
            "semantic_equivalence_verified": self.semantic_equivalence_verified,
            "disclaimer": (
                "This is a modernization candidate. A compiling program is NOT "
                "proof that COBOL behavior was preserved (Phase 10)."
            ),
        }


def run_java_modernization(
    bundle: AnalysisBundle,
    *,
    workspace_root: str | Path,
    provider: LLMProvider | None = None,
    max_repair_attempts: int = 3,
    javac: str = "javac",
    compile_timeout_s: float = 30.0,
) -> Phase9Result:
    architecture = build_architecture(bundle)
    project = generate_project(bundle, architecture)

    compiler = JavaCompiler(workspace_root, javac=javac, timeout_s=compile_timeout_s)
    if not javac_available(javac):
        raise RuntimeError(
            f"{javac!r} not available — cannot run Phase 9 compilation/repair"
        )

    initial = compiler.compile(project)
    repair: RepairResult | None = None
    final = initial

    if not initial.success and provider is not None:
        repair = SelfRepairLoop(
            provider, compiler, max_attempts=max_repair_attempts
        ).run(project, bundle, initial_compilation=initial)
        project = project.model_copy(update={"files": repair.final_files})
        final = compiler.compile(project)

    return Phase9Result(
        architecture=architecture,
        project=project,
        initial_compilation=initial,
        repair=repair,
        final_compilation=final,
        semantic_equivalence_verified=False,
    )
