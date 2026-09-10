"""
Run the full deterministic Phase 9-11 modernization pipeline for one
:class:`~app.dataset.analysis_bundle.AnalysisBundle` and collect every
artifact the Phase 12 API layer needs.

Nothing here recomputes or reimplements architecture generation (#125),
Java generation (#126), compilation (#127), behavioral test extraction
(#129), Java test execution (#130), or behavioral comparison (#131) --
it only calls the existing functions and collects their results. This
is the API layer's single point of contact with that pipeline, so the
four new API routes (architecture / java / validation / report) share
one implementation instead of four.

The AI self-repair / quality loop (Phase 11, #128) is deliberately NOT
run here: it requires a configured ``LLMProvider``, and
``app.api.dependencies.ai.get_llm_provider`` -- the repository's own,
pre-existing dependency -- returns ``None`` because no production
provider is configured in this environment. Running it would either
silently do nothing (a provider-less call) or fabricate a repair
history that never happened. Callers report self-repair as
NOT_AVAILABLE with that exact reason instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.behavioral.comparison.models import Phase10Report
from app.behavioral.extraction.extractor import extract_behavioral_tests
from app.behavioral.javatests import JavaTestRunner
from app.behavioral.javatests.models import JavaTestSuiteResult
from app.behavioral.orchestrator import run_behavioral_validation
from app.core.logging import logger
from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.architecture import build_architecture
from app.java_modernization.architecture.models import JavaArchitecture
from app.java_modernization.compilation import JavaCompiler
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.errors import JavaModernizationError
from app.java_modernization.generation import generate_project
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["ModernizationBundle", "build_modernization_bundle"]


@dataclass(frozen=True)
class ModernizationBundle:
    """Every Phase 9-11 artifact reachable for one analysis, or an honest
    reason why a stage did not run. A ``None`` field always means "did
    not run" -- never "ran and found nothing"."""

    analysis: AnalysisBundle
    architecture: JavaArchitecture | None
    architecture_error: str | None
    project: GeneratedProject | None
    generation_error: str | None
    compilation: CompilationResult | None
    compilation_error: str | None
    java_tests: JavaTestSuiteResult | None
    behavioral: Phase10Report | None
    behavioral_error: str | None


def build_modernization_bundle(
    bundle: AnalysisBundle, *, workspace_root: str | Path
) -> ModernizationBundle:
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)

    try:
        architecture = build_architecture(bundle)
    except JavaModernizationError as e:
        return ModernizationBundle(
            bundle, None, str(e), None, None, None, None, None, None, None
        )
    except Exception as e:  # pragma: no cover - defensive, matches sibling routers
        logger.error("Architecture generation failed for {}: {}", bundle.source_id, e)
        return ModernizationBundle(
            bundle,
            None,
            "Architecture generation failed unexpectedly.",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    project: GeneratedProject | None = None
    generation_error: str | None = None
    try:
        project = generate_project(bundle, architecture)
    except JavaModernizationError as e:
        generation_error = str(e)
    except Exception as e:  # pragma: no cover
        logger.error("Java generation failed for {}: {}", bundle.source_id, e)
        generation_error = "Java generation failed unexpectedly."

    if project is None:
        return ModernizationBundle(
            bundle,
            architecture,
            None,
            None,
            generation_error,
            None,
            None,
            None,
            None,
            None,
        )

    compilation: CompilationResult | None = None
    compilation_error: str | None = None
    try:
        compilation = JavaCompiler(root / "compile").compile(project)
    except Exception as e:  # pragma: no cover
        logger.error("Compilation failed for {}: {}", bundle.source_id, e)
        compilation_error = "Compilation could not be started."

    java_tests: JavaTestSuiteResult | None = None
    behavioral: Phase10Report | None = None
    behavioral_error: str | None = None
    try:
        suite = extract_behavioral_tests(bundle)
        if compilation is not None and compilation.success:
            java_tests = JavaTestRunner(root / "compile").run_suite(suite, project)
        behavioral = run_behavioral_validation(
            bundle, architecture, project, workspace_root=root / "compile"
        )
    except Exception as e:  # pragma: no cover
        logger.error("Behavioral validation failed for {}: {}", bundle.source_id, e)
        behavioral_error = "Behavioral validation could not be started."

    return ModernizationBundle(
        analysis=bundle,
        architecture=architecture,
        architecture_error=None,
        project=project,
        generation_error=None,
        compilation=compilation,
        compilation_error=compilation_error,
        java_tests=java_tests,
        behavioral=behavioral,
        behavioral_error=behavioral_error,
    )
